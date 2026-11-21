"""Calendar tools (Cal.com API v2): find free slots and book a call."""
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api.cal.com/v2"
DISPLAY_TZ = "America/New_York"  # the prospects are in the US


def _headers(version: str) -> dict:
    return {"Authorization": "Bearer " + os.getenv("CALCOM_API_KEY", ""),
            "cal-api-version": version, "Content-Type": "application/json"}


def _event_type_id() -> int:
    return int(os.getenv("CALCOM_EVENT_TYPE_ID", "0"))


def _to_utc_iso(s: str) -> str:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_slot(iso: str) -> str:
    """'2026-11-23T15:00:00Z' -> 'Mon Nov 23, 10:00 AM ET'"""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo(DISPLAY_TZ))
    hour = int(dt.strftime("%I"))
    return dt.strftime("%a %b %d, ") + f"{hour}:" + dt.strftime("%M %p") + " ET"


def get_slots(days: int = 7, n: int = 3) -> list:
    """Return up to n real free slots (UTC ISO strings), on different days when possible."""
    start = datetime.now(timezone.utc).date() + timedelta(days=1)
    r = httpx.get(f"{BASE}/slots", headers=_headers("2024-09-04"), timeout=20, params={
        "eventTypeId": _event_type_id(), "start": start.isoformat(),
        "end": (start + timedelta(days=days)).isoformat(), "timeZone": "UTC"})
    if r.status_code >= 400:
        raise RuntimeError(f"Cal.com slots error {r.status_code}: {r.text[:200]}")
    data = r.json().get("data", {}) or {}
    picked = []
    for day in sorted(data):
        slots = data[day]
        if slots:
            first = slots[len(slots) // 2]  # a middle-of-the-day slot
            picked.append(_to_utc_iso(first["start"] if isinstance(first, dict) else first))
        if len(picked) == n:
            break
    return picked


def slots_message(slots: list) -> str:
    lines = "\n".join(f"{i + 1}) {fmt_slot(s)}" for i, s in enumerate(slots))
    return ("Happy to set that up. Here are a few times that work (Eastern Time):\n"
            f"{lines}\nReply with the number you prefer and the call will be booked.\n\nThe Ledgerwise team")


def confirmation_message(iso: str) -> str:
    return (f"You are booked for {fmt_slot(iso)}. A calendar invitation will arrive shortly.\n\n"
            "The Ledgerwise team")


def demo_email(company_name: str) -> str:
    """No real prospect is contacted. Bookings use a plus-address of the demo owner's own email."""
    base = os.getenv("DEMO_EMAIL", "")
    if "@" not in base:
        raise RuntimeError("DEMO_EMAIL is missing (set it to your own email address)")
    local, domain = base.split("@", 1)
    slug = re.sub(r"[^a-z0-9]", "", company_name.lower())[:20] or "prospect"
    return f"{local}+{slug}@{domain}"


def book(start_iso: str, name: str, email: str) -> dict:
    body = {"start": start_iso, "eventTypeId": _event_type_id(),
            "attendee": {"name": name, "email": email, "timeZone": DISPLAY_TZ}}
    r = httpx.post(f"{BASE}/bookings", headers=_headers("2024-08-13"), json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Cal.com booking error {r.status_code}: {r.text[:200]}")
    d = r.json().get("data", {}) or {}
    return {"uid": d.get("uid"), "start": d.get("start") or start_iso}
