import pytest
from fastapi.testclient import TestClient

from app import agent, cal
from app.main import app
from app.safety import check_text, has_block, is_bot_question, is_stop_request

client = TestClient(app)


def no_llm(*a, **k):
    raise AssertionError("the AI must not be called for this reply")


def fake_llm(out):
    return lambda *a, **k: out


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


# ---------------------------------------------------------------- rules in code
def test_price_is_blocked():
    assert has_block(check_text("It costs $300 per month", ""))


def test_amount_from_the_prospects_own_sources_is_not_a_price():
    src = "Acme raised $5 million in a seed round"
    assert not has_block(check_text("Congrats on raising $5 million.", src))
    assert has_block(check_text("Our plan is $5 per month.", src))
    assert has_block(check_text("We charge $50.", src))


def test_unsourced_number_is_blocked_but_sourced_is_ok():
    assert has_block(check_text("You raised 5 million", "You are hiring"))
    assert not has_block(check_text("You raised 5 million", "Acme raised 5 million"))


def test_stop_and_bot_detection():
    for t in ["Please stop", "Unsubscribe", "Not interested, thanks", "do not contact us"]:
        assert is_stop_request(t)
    assert not is_stop_request("Tell me more")
    assert is_bot_question("Am I talking to a bot?") and is_bot_question("are you an AI")


def test_slot_formatting_in_us_eastern_time():
    assert cal.fmt_slot("2026-11-23T15:00:00Z") == "Mon Nov 23, 10:00 AM ET"


# ---------------------------------------------------------------- the decision
def test_stop_and_bot_never_use_the_ai(monkeypatch):
    monkeypatch.setattr(agent, "llm_json", no_llm)
    assert agent.decide("Unsubscribe me", "", "", [])["action"] == "stop"
    assert agent.decide("Am I talking to a bot?", "", "", [])["action"] == "bot_reply"


def test_price_question_gets_fixed_answer_without_numbers(monkeypatch):
    monkeypatch.setattr(agent, "llm_json", fake_llm({"intent": "pricing_question", "message": "It is $300"}))
    d = agent.decide("How much?", "", "", [])
    assert d["action"] == "price_reply" and "$" not in d["message"]


def test_answer_that_quotes_a_price_goes_to_a_human(monkeypatch):
    monkeypatch.setattr(agent, "llm_json", fake_llm(
        {"intent": "question", "message": "We charge $300 per month.", "confidence": 0.95}))
    d = agent.decide("What do you offer?", "", "", [])
    assert d["action"] == "handoff"


def test_low_confidence_goes_to_a_human(monkeypatch):
    monkeypatch.setattr(agent, "llm_json", fake_llm(
        {"intent": "question", "message": "Ledgerwise does monthly bookkeeping.", "confidence": 0.4}))
    assert agent.decide("What do you do?", "", "", [])["action"] == "handoff"


def test_good_answer_is_sent(monkeypatch):
    monkeypatch.setattr(agent, "llm_json", fake_llm(
        {"intent": "question", "message": "Ledgerwise does monthly bookkeeping for e-commerce brands.", "confidence": 0.9}))
    assert agent.decide("What do you do?", "", "", [])["action"] == "answer"


def test_pick_outside_offered_slots_is_handed_off(monkeypatch):
    monkeypatch.setattr(agent, "llm_json", fake_llm({"intent": "picks_slot", "slot_choice": 5}))
    assert agent.decide("5", "", "", ["2026-11-23T15:00:00Z"])["action"] == "handoff"


# ---------------------------------------------------------------- full flows
def test_stop_blocks_everything_afterwards(db, company):
    r = client.post(f"/companies/{company['id']}/simulate-reply", json={"text": "Please stop emailing me"})
    assert r.json()["action"] == "stop"
    assert db.tables["companies"][0]["status"] == "do_not_contact"
    assert not [m for m in db.tables["messages"] if m["direction"] == "out"]  # nothing sent back
    assert client.post(f"/companies/{company['id']}/send", json={"body": "Hello again"}).status_code == 409
    assert client.post(f"/companies/{company['id']}/simulate-reply", json={"text": "hi"}).json()["action"] == "ignored"


def test_call_request_then_booking(db, company, monkeypatch):
    slots = ["2026-11-23T15:00:00Z", "2026-11-24T16:00:00Z", "2026-11-25T15:30:00Z"]
    monkeypatch.setenv("DEMO_EMAIL", "me@example.com")
    monkeypatch.setattr(cal, "get_slots", lambda *a, **k: slots)
    monkeypatch.setattr(cal, "book", lambda iso, name, email: {"uid": "abc123", "start": iso})
    monkeypatch.setattr(agent, "llm_json", fake_llm({"intent": "wants_call"}))
    assert client.post(f"/companies/{company['id']}/simulate-reply", json={"text": "Let's talk"}).json()["action"] == "offer_slots"
    sent = [m for m in db.tables["messages"] if m["direction"] == "out"][-1]
    assert sent["meta"]["offered_slots"] == slots and "Mon Nov 23, 10:00 AM ET" in sent["body"]

    monkeypatch.setattr(agent, "llm_json", fake_llm({"intent": "picks_slot", "slot_choice": 2}))
    assert client.post(f"/companies/{company['id']}/simulate-reply", json={"text": "2 please"}).json()["action"] == "book"
    assert db.tables["bookings"][0]["start_time"] == slots[1]
    assert db.tables["companies"][0]["status"] == "booked"


def test_booking_failure_is_handed_to_a_human(db, company, monkeypatch):
    slots = ["2026-11-23T15:00:00Z"]
    monkeypatch.setenv("DEMO_EMAIL", "me@example.com")
    db.table("messages").insert({"company_id": company["id"], "direction": "out", "body": "slots", "status": "sent",
                                 "meta": {"offered_slots": slots}}).execute()
    def boom(*a, **k): raise RuntimeError("calendar down")
    monkeypatch.setattr(cal, "book", boom)
    monkeypatch.setattr(agent, "llm_json", fake_llm({"intent": "picks_slot", "slot_choice": 1}))
    r = client.post(f"/companies/{company['id']}/simulate-reply", json={"text": "1"}).json()
    assert r["action"] == "handoff" and db.tables["companies"][0]["needs_human"] is True


def test_takeover_makes_the_agent_quiet(db, company, monkeypatch):
    monkeypatch.setattr(agent, "llm_json", no_llm)
    client.post(f"/companies/{company['id']}/takeover")
    r = client.post(f"/companies/{company['id']}/simulate-reply", json={"text": "What do you do?"}).json()
    assert r["action"] == "human"
    assert not [m for m in db.tables["messages"] if m["direction"] == "out"]


def test_first_email_review_rules(db, company):
    m = db.table("messages").insert({
        "company_id": company["id"], "direction": "out", "subject": "Hello", "status": "draft",
        "body": "Hi, we saw you are hiring a bookkeeper.", "meta": {"kind": "first_email"},
        "sources": [{"claim": "Hiring a bookkeeper", "quote": "We are hiring a bookkeeper", "source_url": "u"}]}).execute().data[0]
    bad = client.patch(f"/messages/{m['id']}", json={"subject": "Hello", "body": "It costs $300 per month"})
    assert any(f.startswith("BLOCK") for f in bad.json()["flags"])
    assert client.post(f"/messages/{m['id']}/approve").status_code == 422
    ok = client.patch(f"/messages/{m['id']}", json={"subject": "Hello", "body": "Hi, we saw you are hiring a bookkeeper."})
    assert not any(f.startswith("BLOCK") for f in ok.json()["flags"])
    assert client.post(f"/messages/{m['id']}/approve").json() == {"ok": True}
    assert db.tables["messages"][0]["status"] == "sent"
    assert client.post(f"/messages/{m['id']}/approve").status_code == 400  # cannot send twice


def test_rejecting_a_first_email_lets_the_team_write_a_new_one(db, company):
    db.table("companies").update({"status": "email_drafted"}).eq("id", company["id"]).execute()
    m = db.table("messages").insert({
        "company_id": company["id"], "direction": "out", "subject": "Hello", "status": "draft",
        "body": "Hi there", "meta": {"kind": "first_email"}}).execute().data[0]
    assert client.post(f"/messages/{m['id']}/reject").json() == {"ok": True}
    assert db.tables["companies"][0]["status"] == "qualified"


def test_password_protects_the_app(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    assert client.get("/stats").status_code == 401
    assert client.get("/health").status_code == 200
    import base64
    ok = {"Authorization": "Basic " + base64.b64encode(b"user:secret").decode()}
    assert client.get("/", headers=ok).status_code in (200, 404, 500)  # passes the login (page may not exist in tests)
