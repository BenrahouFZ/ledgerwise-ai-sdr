"""Ledgerwise's rules, enforced in CODE (not only in prompts).

1. Never quote a price             -> check_text() blocks prices
2. Never claim untrue things       -> check_text() blocks numbers that are not in the sources
3. Stop means stop, forever        -> is_stop_request(), block_company(), is_blocked()
4. Honest about being a bot        -> is_bot_question() (fixed honest answer in agent.py)
"""
import re

PRICE_NUMBER = re.compile(
    r"[$€£]\s?\d[\d,.]*|\b\d[\d,.]*\s?(usd|dollars?|eur|euros?)\b|\bper (month|year|hour)\b", re.I)
PRICE_WORD = re.compile(r"\b(price|prices|pricing|cost|costs|fee|fees|rate|rates|discount)\b", re.I)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

STOP_WORDS = re.compile(
    r"\b(stop|unsubscribe|remove me|take me off|not interested|no thanks|no thank you|"
    r"do not contact|don't contact|dont contact|leave me alone|opt out)\b", re.I)
BOT_QUESTION = re.compile(
    r"\b(are you (a |an )?(bot|robot|ai|human|real person|automated)|is this (a |an )?(bot|robot|ai|automated)|"
    r"am i (talking|speaking) (to|with) (a |an )?(bot|robot|ai|human|machine))\b", re.I)


def check_text(text: str, allowed_sources_text: str = "") -> list:
    """Return a list of flags. A flag starting with 'BLOCK' means it must not be sent."""
    flags = []
    allowed_low = allowed_sources_text.lower()
    for m in PRICE_NUMBER.finditer(text):
        found = m.group(0).strip().rstrip(".,").lower()
        # An amount copied from the prospect's own sources (for example "raised $3 million") is a fact
        # about them, not a Ledgerwise price. Anything else that looks like a price is blocked.
        if found.startswith("per ") or found not in allowed_low:
            flags.append("BLOCK: contains a price")
            break
    if PRICE_WORD.search(text):
        flags.append("warning: mentions pricing words")
    allowed = set(NUMBER.findall(allowed_sources_text))
    for n in sorted(set(NUMBER.findall(text))):
        if n not in allowed:
            flags.append(f"BLOCK: the number {n} is not in the sources")
    if len(text.split()) > 150:
        flags.append("warning: message is long")
    return flags


def has_block(flags: list) -> bool:
    return any(f.startswith("BLOCK") for f in flags)


def is_stop_request(text: str) -> bool:
    return bool(STOP_WORDS.search(text or ""))


def is_bot_question(text: str) -> bool:
    return bool(BOT_QUESTION.search(text or ""))


def is_blocked(db, company_id: str) -> bool:
    """True if this company said stop. Checked before ANY message is sent."""
    c = db.table("companies").select("status").eq("id", company_id).execute().data
    if c and c[0]["status"] == "do_not_contact":
        return True
    return bool(db.table("do_not_contact").select("id").eq("company_id", company_id).execute().data)


def block_company(db, company_id: str, reason: str):
    db.table("do_not_contact").insert({"company_id": company_id, "reason": reason}).execute()
    db.table("companies").update({"status": "do_not_contact", "needs_human": False}).eq("id", company_id).execute()
