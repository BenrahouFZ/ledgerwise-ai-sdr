from fastapi.testclient import TestClient
from app.main import app
from app import retrieval

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_retrieval_finds_pricing():
    assert any("Pro" in c for c in retrieval.search("How much does the Pro plan cost?"))
