from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import llm, retrieval
from app.db import get_db

app = FastAPI(title="AI Sales Platform Starter")
STATIC = Path(__file__).resolve().parent / "static"


class AskIn(BaseModel):
    question: str


class LeadIn(BaseModel):
    name: str
    company: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.post("/ask")
def ask(body: AskIn):
    """Answer a question using ONLY the company info in /data (simple RAG)."""
    context = retrieval.search(body.question)
    if not context:
        return {"answer": "I do not have that information.", "sources": []}
    prompt = "Company info:\n" + "\n---\n".join(context) + f"\n\nQuestion: {body.question}"
    system = "You are a sales assistant. Answer only from the company info. If unsure, say you do not know."
    try:
        return {"answer": llm.ask(prompt, system=system), "sources": context}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/score-lead")
def score_lead(lead: LeadIn):
    """Score a lead from 0 to 100 and suggest the next action (structured output)."""
    system = (
        "You score sales leads. Return JSON with keys: score (0-100 integer), "
        "reason (one sentence), next_action (one sentence)."
    )
    prompt = f"Name: {lead.name}\nCompany: {lead.company}\nMessage: {lead.message}"
    try:
        return llm.ask_json(prompt, system=system)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/companies")
def list_companies():
    """All companies, best score first."""
    rows = get_db().table("companies").select("*").execute().data
    rows.sort(key=lambda r: (r["score"] if r["score"] is not None else -1), reverse=True)
    return rows


@app.get("/companies/{company_id}")
def company_detail(company_id: str):
    """One company with all its evidence (reason, quote, source link)."""
    db = get_db()
    found = db.table("companies").select("*").eq("id", company_id).execute().data
    if not found:
        raise HTTPException(404, "Company not found")
    evidence = db.table("evidence").select("*").eq("company_id", company_id).execute().data
    return {"company": found[0], "evidence": evidence}
