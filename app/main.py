import base64
import os
import secrets
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import agent, writer
from app.db import get_db
from app.safety import check_text, has_block, is_blocked

app = FastAPI(title="Ledgerwise AI SDR")
STATIC = Path(__file__).resolve().parent / "static"


# ------------------------------------------------------------ simple login
@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """If APP_PASSWORD is set, the whole app asks for it (username: anything)."""
    password = os.getenv("APP_PASSWORD")
    if password and request.url.path != "/health":
        header = request.headers.get("authorization", "")
        ok = False
        if header.lower().startswith("basic "):
            try:
                given = base64.b64decode(header[6:]).decode().partition(":")[2]
                ok = secrets.compare_digest(given, password)
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Ledgerwise"'})
    return await call_next(request)


class EditIn(BaseModel):
    subject: str | None = None
    body: str


class TextIn(BaseModel):
    text: str


class StatusIn(BaseModel):
    status: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


# ------------------------------------------------------------ helpers
def _one(db, table, row_id, label):
    found = db.table(table).select("*").eq("id", row_id).execute().data
    if not found:
        raise HTTPException(404, f"{label} not found")
    return found[0]


def _sources_text(m) -> str:
    return " ".join((s.get("claim", "") + " " + s.get("quote", "")) for s in (m.get("sources") or []))


def _kind(m) -> str:
    return (m.get("meta") or {}).get("kind", "")


def _flags_for(m, subject, body):
    """First emails must only use sourced facts. Reply drafts only need to avoid prices."""
    text = ((subject or "") + "\n" + body).strip()
    if _kind(m) == "first_email":
        return check_text(text, _sources_text(m))
    return check_text(text, text)  # numbers are allowed, prices are still blocked


# ------------------------------------------------------------ dashboard
@app.get("/stats")
def stats():
    db = get_db()
    comps = db.table("companies").select("id,status,needs_human").execute().data
    msgs = db.table("messages").select("id,company_id,status,direction,meta").execute().data
    inactive = {c["id"] for c in comps if c["status"] in ("rejected", "do_not_contact")}
    return {
        "companies": len(comps),
        "by_status": dict(Counter(c["status"] for c in comps)),
        "emails_to_review": sum(1 for m in msgs if m["direction"] == "out" and m["status"] == "draft"
                                and _kind(m) == "first_email" and m["company_id"] not in inactive),
        "needs_human": sum(1 for c in comps if c.get("needs_human")),
        "bookings": len(db.table("bookings").select("id").execute().data),
    }


# ------------------------------------------------------------ companies
@app.get("/companies")
def list_companies():
    rows = get_db().table("companies").select("*").execute().data
    rows.sort(key=lambda r: (r["score"] if r["score"] is not None else -1), reverse=True)
    return rows


@app.get("/companies/{company_id}")
def company_detail(company_id: str):
    """One company with evidence (reason, quote, source link), conversation, events and bookings."""
    db = get_db()
    company = _one(db, "companies", company_id, "Company")
    def rows(table):
        r = db.table(table).select("*").eq("company_id", company_id).execute().data
        r.sort(key=lambda x: x["created_at"])
        return r
    return {"company": company, "evidence": db.table("evidence").select("*").eq("company_id", company_id).execute().data,
            "messages": rows("messages"), "events": rows("events"), "bookings": rows("bookings")}


@app.post("/companies/{company_id}/status")
def set_status(company_id: str, body: StatusIn):
    """The sales team can disqualify a company or put it back."""
    if body.status not in ("qualified", "rejected"):
        raise HTTPException(400, "Status must be 'qualified' or 'rejected'")
    db = get_db()
    _one(db, "companies", company_id, "Company")
    db.table("companies").update({"status": body.status}).eq("id", company_id).execute()
    return {"ok": True}


@app.post("/companies/{company_id}/draft")
def draft_for_company(company_id: str):
    db = get_db()
    company = _one(db, "companies", company_id, "Company")
    if company["status"] not in ("qualified", "email_drafted"):
        raise HTTPException(400, "Only qualified companies can get a draft")
    if writer.draft_email(db, company) is None:
        raise HTTPException(422, "Could not write an email (no evidence or the AI gave no answer). Try again.")
    return {"ok": True}


# ------------------------------------------------------------ conversation controls
@app.post("/companies/{company_id}/simulate-reply")
def simulate_reply(company_id: str, body: TextIn):
    """DEMO: type what the prospect would reply. The agent handles it exactly as a real reply."""
    if not body.text.strip():
        raise HTTPException(400, "Write a reply first")
    return agent.handle_reply(company_id, body.text.strip())


@app.post("/companies/{company_id}/takeover")
def takeover(company_id: str):
    db = get_db()
    _one(db, "companies", company_id, "Company")
    db.table("companies").update({"handled_by": "human"}).eq("id", company_id).execute()
    agent.log_event(db, company_id, "takeover", "A person took over this thread. The agent will stay quiet.")
    return {"ok": True}


@app.post("/companies/{company_id}/release")
def release(company_id: str):
    db = get_db()
    _one(db, "companies", company_id, "Company")
    db.table("companies").update({"handled_by": "agent"}).eq("id", company_id).execute()
    agent.log_event(db, company_id, "release", "The thread was handed back to the agent.")
    return {"ok": True}


@app.post("/companies/{company_id}/resolve")
def resolve(company_id: str):
    db = get_db()
    _one(db, "companies", company_id, "Company")
    db.table("companies").update({"needs_human": False}).eq("id", company_id).execute()
    return {"ok": True}


@app.post("/companies/{company_id}/send")
def human_send(company_id: str, body: EditIn):
    """A person writes to the prospect. The do-not-contact list is still enforced."""
    db = get_db()
    _one(db, "companies", company_id, "Company")
    if is_blocked(db, company_id):
        raise HTTPException(409, "This company asked us to stop. Nothing was sent.")
    if not body.body.strip():
        raise HTTPException(400, "Write a message first")
    db.table("messages").insert({
        "company_id": company_id, "direction": "out", "subject": body.subject, "body": body.body.strip(),
        "status": "sent", "author": "human", "needs_human": False, "flags": [], "meta": {"kind": "human"},
    }).execute()
    db.table("companies").update({"needs_human": False}).eq("id", company_id).execute()
    return {"ok": True}


# ------------------------------------------------------------ message review
@app.get("/messages")
def list_messages(status: str | None = None, kind: str | None = None):
    db = get_db()
    q = db.table("messages").select("*")
    if status:
        q = q.eq("status", status)
    rows = q.execute().data
    if kind:
        rows = [r for r in rows if _kind(r) == kind]
    names = {c["id"]: c for c in db.table("companies").select("id,name,score").execute().data}
    for r in rows:
        c = names.get(r["company_id"], {})
        r["company_name"], r["company_score"] = c.get("name"), c.get("score")
    rows.sort(key=lambda r: r["created_at"])
    return rows


@app.patch("/messages/{mid}")
def edit_message(mid: str, body: EditIn):
    """A person edits a draft. The guardrails run again on the new text."""
    db = get_db()
    m = _one(db, "messages", mid, "Message")
    if m["status"] != "draft":
        raise HTTPException(400, "Only drafts can be edited")
    flags = _flags_for(m, body.subject, body.body)
    db.table("messages").update({"subject": body.subject, "body": body.body, "flags": flags,
                                 "needs_human": bool(flags), "author": "human"}).eq("id", mid).execute()
    return {"ok": True, "flags": flags}


@app.post("/messages/{mid}/approve")
def approve_message(mid: str):
    """Approve = send. The rules are checked one last time, and a stopped company is never contacted."""
    db = get_db()
    m = _one(db, "messages", mid, "Message")
    if m["direction"] != "out" or m["status"] != "draft":
        raise HTTPException(400, "Only outgoing drafts can be approved")
    if is_blocked(db, m["company_id"]):
        raise HTTPException(409, "This company asked us to stop. Nothing was sent.")
    flags = _flags_for(m, m.get("subject"), m["body"])
    if has_block(flags):
        raise HTTPException(422, {"message": "Blocked by the rules", "flags": flags})
    # Demo mode: "sent" means placed in the outbox. No real email leaves the system.
    db.table("messages").update({"status": "sent", "flags": flags}).eq("id", mid).execute()
    if _kind(m) == "first_email":
        db.table("companies").update({"status": "contacted"}).eq("id", m["company_id"]).execute()
    else:
        db.table("companies").update({"needs_human": False}).eq("id", m["company_id"]).execute()
    return {"ok": True}


@app.post("/messages/{mid}/reject")
def reject_message(mid: str):
    db = get_db()
    m = _one(db, "messages", mid, "Message")
    db.table("messages").update({"status": "rejected"}).eq("id", mid).execute()
    if _kind(m) == "reply_draft":
        db.table("companies").update({"needs_human": False}).eq("id", m["company_id"]).execute()
    elif _kind(m) == "first_email":
        # Back to "qualified" so the team can write a new email (otherwise the company is stuck).
        db.table("companies").update({"status": "qualified"}).eq("id", m["company_id"]).eq("status", "email_drafted").execute()
    return {"ok": True}


# ------------------------------------------------------------ calls
@app.get("/bookings")
def list_bookings():
    db = get_db()
    names = {c["id"]: c["name"] for c in db.table("companies").select("id,name").execute().data}
    rows = db.table("bookings").select("*").execute().data
    for r in rows:
        r["company_name"] = names.get(r["company_id"])
    rows.sort(key=lambda r: r["start_time"])
    return rows
