"""Shows exactly what the agent wrote for chosen eval cases, and why the rule check flagged it.
Read-only: nothing is saved in the database and nothing is booked.

Run:  python debug_case.py 25 27
"""
import json
import sys
from pathlib import Path

from app.agent import decide, knowledge
from app.evaluate import FACTS, HISTORY, OFFERED
from app.safety import PRICE_NUMBER, check_text

cases = json.loads((Path(__file__).parent / "eval" / "replies.json").read_text(encoding="utf-8"))
numbers = [int(a) for a in sys.argv[1:]] or [25, 27]

for n in numbers:
    c = cases[n - 1]
    d = decide(c["text"], HISTORY, FACTS, OFFERED if c.get("offered") else [])
    msg = d.get("message") or ""
    print("=" * 70)
    print(f"Case {n}: {c['text']}")
    print("Expected:", c["expect"], "| Agent did:", d["action"], "| Reason:", d.get("reason"))
    print("\nAGENT MESSAGE:\n" + (msg or "(no message)"))
    print("\nPrice pattern found in the message:", PRICE_NUMBER.search(msg))
    print("Flags, the way the evaluation checks (facts + history only):", check_text(msg, FACTS + " " + HISTORY))
    print("Flags, the way the real agent checks (knowledge file + facts):", check_text(msg, knowledge() + "\n" + FACTS))
