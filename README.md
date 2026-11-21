# Ledgerwise AI SDR platform

An AI sales assistant for Ledgerwise, a US bookkeeping firm for e-commerce brands. The agent finds companies,
qualifies them with sources, drafts first emails, answers replies and books calls. The sales team stays in control.

Demo mode: approved emails go to an outbox and nothing is sent to real companies.

## What it does
| Step | How it works | Code |
|---|---|---|
| Research | Web searches for trigger events (hiring finance, funding, new channels), the AI extracts companies. Every fact keeps a quote and a source URL, and the code checks that the quote really is in the page. | `app/research.py` |
| Qualify | The AI rates each criterion with a quote. The score is computed in code from the verified criteria (sells online, US based, trigger, size, contact). | `app/research.py` |
| Write | A short email using only stored, sourced facts. The facts used are saved with the draft. | `app/writer.py` |
| Reply | Rules first, then the AI classifies the reply. Prices, calendar times and confirmations are written by code. Anything unsure goes to a person. | `app/agent.py` |
| Book | Real free slots from the Cal.com API, booking created when the prospect picks one. | `app/cal.py` |
| Sales team UI | Companies with reasons, email review, conversations with take over, calls booked. | `app/static/index.html` |

## The client's rules, enforced in code (`app/safety.py`)
1. Never quote a price: a price pattern blocks any message. Pricing questions get a fixed answer that suggests a call.
2. Never claim anything untrue: facts need a verified quote, and any number in a message must exist in the sources.
3. Stop means stop: stop words add the company to a do-not-contact list, nothing is sent back, and every send path checks that list.
4. Honest about being a bot: a fixed honest answer.
5. Unsure goes to a human: low confidence, answers that break a rule, or topics outside the knowledge file become a draft for a person.

## Run it locally
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then fill in the keys
```
Create the database tables with `schema.sql` in the Supabase SQL editor, then:
```
python -m app.research discover        # find companies
python -m app.research enrich          # collect evidence and score
python -m app.writer                   # draft emails (or use the button in the UI)
uvicorn app.main:app --reload          # open http://127.0.0.1:8000
python -m pytest                       # tests, no internet needed
python -m app.evaluate                 # measure the reply agent (see eval/RESULTS.md)
```

## Deploy (Render)
Create a Web Service from the GitHub repo (`render.yaml` is included), set the environment variables listed in `.env.example`
(set `APP_PASSWORD` so the app asks for a password), and open the URL. The free plan sleeps when idle, so the first load can take about a minute.

## Limits
- Demo mode: no real email is sent, and prospects are simulated with the "simulate reply" box. Bookings use a plus-address of the demo owner's email.
- The free AI tier has rate limits, so the pipeline waits and retries.
- Revenue and team size are rarely public, so size is often "unknown" and scores lower.
