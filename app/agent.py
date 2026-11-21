"""The reply agent. It reads a prospect's reply, decides what to do, and acts with tools.

Order of decisions:
  1. Hard rules in code (no AI): stop requests and "are you a bot?" questions.
  2. The AI classifies the reply (intent) and may draft an answer.
  3. Code maps the intent to an action. Prices, calendar times and confirmations are written by
     code, never invented by the AI. Anything uncertain or risky goes to a human.

Actions: stop, bot_reply, price_reply, offer_slots, book, answer, handoff
"""
from pathlib import Path

from app import cal
from app.db import get_db
from app.research import llm_json
from app.safety import block_company, check_text, has_block, is_blocked, is_bot_question, is_stop_request

KNOWLEDGE_FILE = Path(__file__).resolve().parent.parent / "data" / "ledgerwise.md"
MIN_CONFIDENCE = 0.7

BOT_REPLY = ("Good question. I am an AI assistant working with the Ledgerwise sales team, and a person "
             "on the team can take over this conversation at any time. Would you like to find a time "
             "for a short call?\n\nThe Ledgerwise team")
PRICE_REPLY = ("Pricing depends on your bookkeeping needs, so we go through it on a short call rather than "
               "by email. Would you like me to suggest a few times?\n\nThe Ledgerwise team")

DECIDE_SYSTEM = """You are the reply assistant for Ledgerwise's sales team. A prospect replied to our outreach. Classify their latest reply and, only when it is a question or an objection that you can answer from KNOWLEDGE or FACTS, write a short answer.

Intents:
- question: asks something about Ledgerwise or about their own company
- objection: pushes back (too small, already have someone, bad timing)
- wants_call: wants to talk, see a demo or get times, but has not chosen a time yet
- picks_slot: chooses one of the OFFERED SLOTS (put its number in slot_choice)
- pricing_question: asks about price, cost, quote, fees or budget
- bot_question: asks whether they are talking to a bot, an AI or a person
- not_interested: wants no more contact
- other: anything else, including legal questions, contracts, complaints, compliance, or anything not covered by KNOWLEDGE

Rules for the answer message:
- Use ONLY KNOWLEDGE and FACTS. If the answer is not there, set intent to "other" and explain in handoff_reason. Never guess.
- Never mention a price, fee or any number that is not in KNOWLEDGE or FACTS.
- Never promise results, savings, deadlines or compliance.
- 2 to 4 short sentences, friendly, sign off as "The Ledgerwise team".
- If the prospect asks for a time that is not one of the OFFERED SLOTS, intent is "other".
Return JSON: {"intent":"...","message":"... or null","slot_choice":null,"confidence":0.0,"handoff_reason":null}"""


def knowledge() -> str:
    return KNOWLEDGE_FILE.read_text(encoding="utf-8")


def log_event(db, company_id, kind, detail=""):
    db.table("events").insert({"company_id": company_id, "kind": kind, "detail": detail}).execute()


def facts_text(db, company_id) -> str:
    ev = db.table("evidence").select("*").eq("company_id", company_id).execute().data
    return "\n".join(f'- {e["claim"]} (quote: "{e.get("quote") or ""}")' for e in ev)


def history_text(db, company_id, limit=8) -> str:
    msgs = db.table("messages").select("*").eq("company_id", company_id).execute().data
    msgs = [m for m in msgs if m["status"] in ("sent", "received")]
    msgs.sort(key=lambda m: m["created_at"])
    lines = [("Prospect: " if m["direction"] == "in" else "Ledgerwise: ") + m["body"] for m in msgs[-limit:]]
    return "\n".join(lines)


def offered_slots(db, company_id) -> list:
    """The slots we last offered to this prospect (stored on our last message)."""
    msgs = db.table("messages").select("*").eq("company_id", company_id).eq("direction", "out").execute().data
    msgs.sort(key=lambda m: m["created_at"], reverse=True)
    for m in msgs:
        slots = (m.get("meta") or {}).get("offered_slots")
        if slots and m["status"] == "sent":
            return slots
    return []


# ------------------------------------------------------------------ the decision
def _handoff(reason, message=None, flags=None):
    return {"action": "handoff", "reason": reason, "message": message, "flags": flags or []}


def decide(text: str, history: str, facts: str, offered: list) -> dict:
    """Decide what to do with a reply. No database writes here, so it can be tested and evaluated."""
    if is_stop_request(text):
        return {"action": "stop", "reason": "stop request caught by a rule"}
    if is_bot_question(text):
        return {"action": "bot_reply", "message": BOT_REPLY, "reason": "bot question caught by a rule"}

    slots_txt = "\n".join(f"{i + 1}) {cal.fmt_slot(s)}" for i, s in enumerate(offered)) or "(none offered yet)"
    prompt = (f"KNOWLEDGE:\n{knowledge()}\n\nFACTS ABOUT THIS PROSPECT'S COMPANY:\n{facts or '(none)'}\n\n"
              f"CONVERSATION SO FAR:\n{history or '(none)'}\n\nOFFERED SLOTS:\n{slots_txt}\n\n"
              f"LATEST REPLY FROM THE PROSPECT:\n{text}")
    out = llm_json(prompt, DECIDE_SYSTEM)
    intent = out.get("intent")
    if not intent:
        return _handoff("the AI gave no usable answer")

    if intent == "not_interested":
        return {"action": "stop", "reason": "the AI read this as not interested"}
    if intent == "bot_question":
        return {"action": "bot_reply", "message": BOT_REPLY, "reason": "bot question"}
    if intent == "pricing_question":
        return {"action": "price_reply", "message": PRICE_REPLY, "reason": "pricing question, never answered by AI"}
    if intent == "wants_call":
        return {"action": "offer_slots", "reason": "the prospect wants a call"}
    if intent == "picks_slot":
        choice = out.get("slot_choice")
        if isinstance(choice, int) and 1 <= choice <= len(offered):
            return {"action": "book", "slot_choice": choice, "reason": f"the prospect chose slot {choice}"}
        return _handoff("the prospect chose a time that is not on the offered list")
    if intent in ("question", "objection"):
        msg = (out.get("message") or "").strip()
        try:
            conf = float(out.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if not msg or out.get("handoff_reason") or conf < MIN_CONFIDENCE:
            return _handoff(out.get("handoff_reason") or "the AI is not sure", msg or None)
        flags = check_text(msg, knowledge() + "\n" + facts)
        if has_block(flags):
            return _handoff("the drafted answer broke a rule: " + "; ".join(flags), msg, flags)
        return {"action": "answer", "message": msg, "reason": intent, "flags": flags}
    return _handoff(out.get("handoff_reason") or "needs a human")


# ------------------------------------------------------------------ doing it
def _send(db, company_id, body, meta, flags=None):
    if is_blocked(db, company_id):  # last safety net before ANY message leaves
        raise RuntimeError("company is on the do-not-contact list")
    db.table("messages").insert({
        "company_id": company_id, "direction": "out", "subject": None, "body": body,
        "status": "sent", "author": "agent", "needs_human": False, "flags": flags or [], "meta": meta,
    }).execute()


def _handoff_now(db, company_id, d):
    if d.get("message"):
        db.table("messages").insert({
            "company_id": company_id, "direction": "out", "body": d["message"], "status": "draft",
            "author": "agent", "needs_human": True, "flags": d.get("flags", []),
            "meta": {"kind": "reply_draft", "reason": d["reason"]},
        }).execute()
    db.table("companies").update({"needs_human": True}).eq("id", company_id).execute()
    log_event(db, company_id, "handoff", d["reason"])
    return {"action": "handoff", "detail": "Handed to a human: " + d["reason"]}


def handle_reply(company_id: str, text: str) -> dict:
    """Process one prospect reply end to end (saves everything in the database)."""
    db = get_db()
    found = db.table("companies").select("*").eq("id", company_id).execute().data
    if not found:
        raise ValueError("company not found")
    company = found[0]
    if is_blocked(db, company_id):
        return {"action": "ignored", "detail": "This company is on the do-not-contact list. Nothing was sent."}

    history, facts, offered = history_text(db, company_id), facts_text(db, company_id), offered_slots(db, company_id)
    db.table("messages").insert({
        "company_id": company_id, "direction": "in", "body": text, "status": "received", "author": "prospect",
    }).execute()
    if company["status"] != "booked":
        db.table("companies").update({"status": "replied"}).eq("id", company_id).execute()

    if (company.get("handled_by") or "agent") == "human":
        db.table("companies").update({"needs_human": True}).eq("id", company_id).execute()
        log_event(db, company_id, "reply_while_human", "A person is handling this thread, so the agent stayed quiet.")
        return {"action": "human", "detail": "A person handles this thread. The agent did not reply."}

    d = decide(text, history, facts, offered)
    act = d["action"]

    if act == "stop":
        block_company(db, company_id, d["reason"])
        log_event(db, company_id, "stop", "The prospect asked to stop. Added to the do-not-contact list. Nothing was sent.")
        return {"action": "stop", "detail": "Prospect asked to stop. Added to the do-not-contact list, nothing sent."}

    if act in ("bot_reply", "price_reply", "answer"):
        _send(db, company_id, d["message"], {"kind": "reply", "intent": act}, d.get("flags"))
        log_event(db, company_id, act, d["reason"])
        return {"action": act, "detail": {"bot_reply": "Answered honestly that it is an AI assistant.",
                                         "price_reply": "Did not quote a price, suggested a call.",
                                         "answer": "Answered the question from the sources."}[act]}

    if act == "offer_slots":
        try:
            slots = cal.get_slots()
        except Exception as e:
            return _handoff_now(db, company_id, _handoff(f"calendar error: {e}"))
        if not slots:
            return _handoff_now(db, company_id, _handoff("no free calendar slots found"))
        _send(db, company_id, cal.slots_message(slots), {"kind": "reply", "intent": "offer_slots", "offered_slots": slots})
        log_event(db, company_id, "offer_slots", f"Offered {len(slots)} real free slots.")
        return {"action": "offer_slots", "detail": f"Offered {len(slots)} real free slots from the calendar."}

    if act == "book":
        iso = offered[d["slot_choice"] - 1]
        try:
            booking = cal.book(iso, company.get("contact_name") or company["name"], cal.demo_email(company["name"]))
        except Exception as e:
            return _handoff_now(db, company_id, _handoff(f"booking failed: {e}"))
        db.table("bookings").insert({
            "company_id": company_id, "start_time": iso, "calcom_uid": booking.get("uid"), "status": "booked",
        }).execute()
        db.table("companies").update({"status": "booked", "needs_human": False}).eq("id", company_id).execute()
        _send(db, company_id, cal.confirmation_message(iso), {"kind": "reply", "intent": "booked"})
        log_event(db, company_id, "booked", f"Booked {cal.fmt_slot(iso)}")
        return {"action": "book", "detail": f"Booked the call for {cal.fmt_slot(iso)}."}

    return _handoff_now(db, company_id, d)
