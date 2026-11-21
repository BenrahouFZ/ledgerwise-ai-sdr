"""A tiny in-memory stand-in for the Supabase client, so tests run without internet or keys."""
import itertools
import uuid

import pytest

_clock = itertools.count(1)


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.op, self.payload, self.filters, self.max = "select", None, [], None

    # builders
    def select(self, *_a, **_k): return self
    def eq(self, c, v): self.filters.append(lambda r: r.get(c) == v); return self
    def neq(self, c, v): self.filters.append(lambda r: r.get(c) != v); return self
    def in_(self, c, vals): self.filters.append(lambda r: r.get(c) in vals); return self
    def is_(self, c, v): self.filters.append(lambda r: r.get(c) is None); return self
    def ilike(self, c, v): self.filters.append(lambda r: str(r.get(c, "")).lower() == v.strip("%").lower()); return self
    def limit(self, n): self.max = n; return self
    def order(self, *_a, **_k): return self
    def insert(self, payload): self.op, self.payload = "insert", payload; return self
    def update(self, payload): self.op, self.payload = "update", payload; return self
    def delete(self): self.op = "delete"; return self

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        match = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for it in items:
                row = dict(it)
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", f"2026-11-21T00:00:00.{next(_clock):09d}Z")
                if self.table == "companies":
                    row.setdefault("handled_by", "agent"); row.setdefault("needs_human", False)
                rows.append(row); out.append(dict(row))
            return Result(out)
        if self.op == "update":
            for r in match: r.update(self.payload)
            return Result([dict(r) for r in match])
        if self.op == "delete":
            for r in match: rows.remove(r)
            return Result([])
        out = [dict(r) for r in match]
        return Result(out[: self.max] if self.max else out)


class FakeDB:
    def __init__(self): self.tables = {}
    def table(self, name): return Query(self, name)


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    import app.agent, app.main, app.writer
    for mod in (app.agent, app.main, app.writer):
        monkeypatch.setattr(mod, "get_db", lambda fake=fake: fake)
    return fake


@pytest.fixture
def company(db):
    c = db.table("companies").insert({"name": "Acme Goods", "status": "contacted", "score": 80}).execute().data[0]
    db.table("evidence").insert({"company_id": c["id"], "kind": "trigger", "claim": "Hiring a bookkeeper",
                                 "quote": "We are hiring a bookkeeper", "source_url": "https://example.com/job"}).execute()
    return c
