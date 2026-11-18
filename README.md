# AI Sales Platform Starter

Run:  uvicorn app.main:app --reload
Open: http://127.0.0.1:8000        (web page)
Docs: http://127.0.0.1:8000/docs   (try the API)

Check setup: python check_setup.py
Run tests:   pytest

Files:
- app/main.py       API endpoints (/ask, /score-lead, /health)
- app/llm.py        calls the Claude API
- app/retrieval.py  simple search over data/*.md
- data/             fake client info (replace with the case study data)
