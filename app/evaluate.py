"""Measures how well the reply agent decides. Nothing is written to the database and nothing is booked.

Run:  python -m app.evaluate
It reads eval/replies.json (test replies with the acceptable actions) and writes eval/RESULTS.md.
Two numbers matter: how often the action is right, and how many RULE VIOLATIONS happen (must be 0).
"""
import json
from pathlib import Path

from app import cal
from app.agent import decide
from app.safety import PRICE_NUMBER, check_text, has_block

ROOT = Path(__file__).resolve().parent.parent
FACTS = '- Hired a part-time bookkeeper (quote: "We are hiring a part-time bookkeeper")'
HISTORY = ("Ledgerwise: Hi there, we noticed you are hiring a part-time bookkeeper. Ledgerwise does monthly "
           "bookkeeping for e-commerce brands. Would you like a short call?")
OFFERED = ["2026-11-23T15:00:00Z", "2026-11-24T16:00:00Z", "2026-11-25T15:30:00Z"]


def run():
    cases = json.loads((ROOT / "eval" / "replies.json").read_text(encoding="utf-8"))
    rows, correct, violations = [], 0, 0
    for i, c in enumerate(cases, 1):
        offered = OFFERED if c.get("offered") else []
        d = decide(c["text"], HISTORY, FACTS, offered)
        ok = d["action"] in c["expect"]
        msg = d.get("message") or ""
        # A rule violation = an automatic message that quotes a price or breaks a sourcing rule.
        auto = d["action"] in ("answer", "bot_reply", "price_reply")
        bad = bool(auto and (PRICE_NUMBER.search(msg) or has_block(check_text(msg, FACTS + " " + HISTORY))))
        stop_missed = c["expect"] == ["stop"] and d["action"] != "stop"
        violations += int(bad or stop_missed)
        correct += int(ok)
        rows.append((i, c["text"], "/".join(c["expect"]), d["action"], ok, bad or stop_missed))
        print(f"{i:>2}. {'OK ' if ok else 'MISS'} expected {'/'.join(c['expect']):<14} got {d['action']:<12} {c['text'][:60]}")
    n = len(cases)
    summary = (f"Correct action: {correct}/{n} ({100 * correct // n}%). "
               f"Rule violations (price quoted, unsourced claim, missed stop): {violations}.")
    print("\n" + summary)
    lines = ["# Reply agent evaluation", "", summary, "",
             "| # | Prospect reply | Expected | Agent did | Right | Rule broken |", "|---|---|---|---|---|---|"]
    for i, t, e, g, ok, bad in rows:
        lines.append(f"| {i} | {t} | {e} | {g} | {'yes' if ok else 'NO'} | {'YES' if bad else 'no'} |")
    (ROOT / "eval" / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()
