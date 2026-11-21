"""Drafts the first email for each qualified company, with guardrails.

Run:  python -m app.writer [n_companies]
"""
import sys

from app.db import get_db
from app.research import llm_json
from app.safety import check_text

WRITE_SYSTEM = """You write the first cold email from Ledgerwise, a US bookkeeping firm that does monthly bookkeeping for e-commerce brands, to the founder or whoever runs finance at one company.
Rules:
- Use ONLY the FACTS provided. Every specific claim about the company must come from a fact. Do not invent anything else (no numbers, no names, no news).
- Never mention any price, fee or cost.
- 60 to 90 words, plain and friendly, no hype, no emojis.
- Greet with "Hi <first name>," if a contact name is given, otherwise "Hi there,".
- Mention one or two facts, say in one line how Ledgerwise helps e-commerce brands with monthly bookkeeping, and offer a short call.
- Sign off as "The Ledgerwise team".
Return JSON: {"subject":"...","body":"...","used_fact_ids":[0,1]}  (ids are the numbers in square brackets)"""

OPT_OUT = '\n\nIf this is not relevant, just reply "stop" and we will not contact you again.'


def draft_email(db, company):
    """Create a draft for one company. Returns the saved message, or None."""
    ev = db.table("evidence").select("*").eq("company_id", company["id"]).execute().data
    usable = [e for e in ev if e.get("quote")]
    usable.sort(key=lambda e: e["kind"] != "trigger")  # trigger facts first
    facts = usable[:6]
    if not facts:
        print("   no evidence, skipped")
        return None
    block = "\n".join(f'[{i}] {e["claim"]} (source quote: "{e["quote"]}")' for i, e in enumerate(facts))
    contact = company.get("contact_name") or "(none)"
    out = llm_json(f"Company: {company['name']}\nContact: {contact}\nFACTS:\n{block}", WRITE_SYSTEM)

    subject, body = (out.get("subject") or "").strip(), (out.get("body") or "").strip()
    if not subject or not body:
        print("   the AI gave no email, skipped")
        return None
    ids = [i for i in out.get("used_fact_ids", []) if isinstance(i, int) and 0 <= i < len(facts)]
    used = [facts[i] for i in ids]
    body += OPT_OUT

    flags = check_text(subject + "\n" + body, " ".join(f["claim"] + " " + f["quote"] for f in used))
    if not used:
        flags.append("BLOCK: the email does not use any sourced fact")
    sources = [{"claim": f["claim"], "quote": f["quote"], "source_url": f["source_url"]} for f in used]

    saved = db.table("messages").insert({
        "company_id": company["id"], "direction": "out", "subject": subject, "body": body,
        "status": "draft", "author": "agent", "needs_human": bool(flags),
        "flags": flags, "sources": sources, "meta": {"kind": "first_email"},
    }).execute().data[0]
    db.table("companies").update({"status": "email_drafted"}).eq("id", company["id"]).execute()
    print("   drafted", "(flags: %s)" % flags if flags else "")
    return saved


def draft_all(limit=None):
    db = get_db()
    rows = db.table("companies").select("*").eq("status", "qualified").execute().data
    rows.sort(key=lambda r: r["score"] or 0, reverse=True)
    for c in rows[:limit]:
        print("Draft:", c["name"])
        try:
            draft_email(db, c)
        except Exception as e:
            print("   skipped:", str(e)[:120])


if __name__ == "__main__":
    draft_all(int(sys.argv[1]) if len(sys.argv) > 1 else None)
