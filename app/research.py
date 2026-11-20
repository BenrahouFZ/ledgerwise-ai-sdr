"""Research pipeline: find companies, collect sourced evidence, score them.

Run from the project folder:
    python -m app.research discover [n_queries]   find candidate companies from web searches
    python -m app.research enrich [n_companies]   visit websites, collect evidence, score
    python -m app.research status                 count companies by status

Key idea: every fact we store has a QUOTE and a SOURCE URL, and the code checks that the
quote really appears in the source text. This is how we enforce "never claim anything untrue".
"""
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from tavily import TavilyClient

from app import llm
from app.db import get_db

load_dotenv()

CACHE = Path(__file__).resolve().parent.parent / ".cache"
CACHE.mkdir(exist_ok=True)
_tv = None


# ---------------------------------------------------------------- helpers
def tavily() -> TavilyClient:
    global _tv
    if _tv is None:
        _tv = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _tv


def _cache_get(key: str):
    f = CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    return f, (json.loads(f.read_text(encoding="utf-8")) if f.exists() else None)


def cached_search(query: str, **kw) -> dict:
    """Web search with a disk cache, so repeated runs do not spend Tavily credits."""
    f, hit = _cache_get("search|" + query + json.dumps(kw, sort_keys=True))
    if hit is not None:
        return hit
    res = tavily().search(query, **kw)
    f.write_text(json.dumps(res), encoding="utf-8")
    return res


def cached_extract(url: str) -> str:
    """Read a web page as text (cached). Returns '' if the page cannot be read."""
    f, hit = _cache_get("extract|" + url)
    if hit is not None:
        return hit["text"]
    try:
        res = tavily().extract(urls=[url])
        text = (res.get("results") or [{}])[0].get("raw_content") or ""
    except Exception as e:
        print("  extract failed:", str(e)[:80])
        text = ""
    text = text[:6000]
    f.write_text(json.dumps({"text": text}), encoding="utf-8")
    return text


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def quote_in_text(quote: str, text: str) -> bool:
    """Guardrail: the quote must really appear in the source text."""
    q = norm(quote)
    return len(q) >= 8 and q in norm(text)


def find_source(quote: str, sources: list):
    """Return the URL of the first source whose text contains the quote, else None."""
    for url, text in sources:
        if quote_in_text(quote, text):
            return url
    return None


def domain_of(url: str) -> str:
    host = urlparse(url if "//" in url else "//" + url).netloc.lower()
    return host.removeprefix("www.")


def llm_json(prompt: str, system: str, tries: int = 4) -> dict:
    """Ask the LLM for JSON. Waits and retries on errors such as rate limits (429)."""
    for i in range(tries):
        try:
            out = llm.ask_json(prompt, system=system, max_tokens=1500)
            time.sleep(4)  # stay under the free-tier requests per minute
            return out if isinstance(out, dict) else {}
        except Exception as e:
            wait = 20 * (i + 1)
            print(f"  LLM error ({str(e)[:80]}). Retrying in {wait}s")
            time.sleep(wait)
    return {}


# ---------------------------------------------------------------- 1. discover
DISCOVERY_QUERIES = [
    "Shopify brand hiring bookkeeper",
    "DTC brand hiring accounting manager",
    "e-commerce brand hiring controller",
    "Amazon seller brand hiring finance manager",
    "Shopify store hiring head of finance",
    "fast growing e-commerce brand hiring operations manager",
    "DTC brand raises seed funding",
    "e-commerce brand raises Series A",
    "Shopify brand announces funding round",
    "consumer brand secures funding online sales growth",
    "DTC brand launches wholesale expansion",
    "e-commerce brand expands to Amazon",
    "online brand launches in Canada and UK",
    "DTC brand opens first retail store",
    "e-commerce brand signs retail distribution deal",
    "Amazon FBA brand hiring operations manager",
    "direct to consumer brand hiring finance operations",
    "Shopify brand expanding internationally",
]

EXTRACT_SYSTEM = """You help a bookkeeping firm find sales leads. Read the web page text and list the US e-commerce brands (companies that sell their own products online) that it mentions.
For each one, give a short factual claim about why now is a good time to contact them (hiring finance, accounting or operations staff; raised money; or growing into new channels such as wholesale, Amazon, retail stores or new countries) and an EXACT quote copied from the text that supports the claim (max 200 characters).
Rules: use only the text provided. Never guess. Skip agencies, job boards, software vendors, investors and large public companies. If there is nothing, return {"companies": []}.
Return JSON: {"companies":[{"name":"...","trigger_kind":"hiring_finance|raised_money|expanding_channels","claim":"...","quote":"..."}]}"""


def save_candidate(db, name, kind, claim, quote, url):
    found = db.table("companies").select("id").ilike("name", name).execute().data
    if found:
        cid = found[0]["id"]
    else:
        cid = db.table("companies").insert({"name": name, "status": "new"}).execute().data[0]["id"]
    dup = (db.table("evidence").select("id").eq("company_id", cid)
           .eq("source_url", url).eq("quote", quote).execute().data)
    if not dup:
        db.table("evidence").insert({
            "company_id": cid, "kind": "trigger", "trigger_kind": kind,
            "claim": claim, "quote": quote, "source_url": url,
        }).execute()


def discover(max_queries=None):
    db = get_db()
    for q in DISCOVERY_QUERIES[:max_queries]:
        print("Search:", q)
        # time_range keeps results recent; remove it if Tavily ever rejects it
        res = cached_search(q, max_results=8, time_range="year")
        for r in res.get("results", []):
            text = (r.get("title", "") + ". " + r.get("content", ""))
            out = llm_json(f"URL: {r['url']}\n\nTEXT:\n{text}", EXTRACT_SYSTEM)
            for c in out.get("companies", []):
                name = (c.get("name") or "").strip()
                quote = (c.get("quote") or "").strip()
                if not name or not quote_in_text(quote, text):
                    continue  # drop anything whose quote is not really in the page
                print("   +", name)
                save_candidate(db, name, c.get("trigger_kind"), c.get("claim"), quote, r["url"])


# ---------------------------------------------------------------- 2. enrich + qualify
BLOCKED = {"linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "crunchbase.com",
           "wikipedia.org", "amazon.com", "reddit.com", "indeed.com", "glassdoor.com", "youtube.com",
           "tiktok.com", "pitchbook.com", "techcrunch.com", "forbes.com", "bloomberg.com", "zoominfo.com",
           "pinterest.com", "yelp.com", "bbb.org"}

QUALIFY_SYSTEM = """You qualify a company as a sales lead for Ledgerwise, a US bookkeeping firm for e-commerce brands with about $1M to $10M yearly revenue and 5 to 50 employees. The person to contact is the founder, the COO, or whoever runs finance.
Use ONLY the sources provided. For each criterion give value true, false or null (null means not stated in the sources) and an EXACT quote copied from a source (max 200 characters). Never guess.
Return JSON with these keys: description (one sentence about what the company sells), sells_online ({"value":..., "quote":"..."}), us_based (same shape), size_fit (same shape; true if revenue is about $1M to $10M or 5 to 50 employees), channels (list from: shopify, amazon, own site, wholesale, retail), contact ({"name":"...","role":"founder|coo|cfo|finance|other","quote":"..."} or null)."""

TRIGGER_POINTS = {"hiring_finance": 30, "raised_money": 25, "expanding_channels": 20}


def pick_website(name):
    res = cached_search(f"{name} official website", max_results=5)
    for r in res.get("results", []):
        d = domain_of(r["url"])
        if d and not any(d == b or d.endswith("." + b) for b in BLOCKED):
            return r["url"], d
    return None, None


def verified(crit, sources):
    """Return (value, source_url) only if the quote is really in a source; otherwise (None, None)."""
    if not isinstance(crit, dict) or crit.get("value") is None:
        return None, None
    url = find_source(crit.get("quote") or "", sources)
    return (crit["value"], url) if url else (None, None)


def score_company(sells, us, size, contact_ok, triggers):
    """Transparent scoring in code (not by the LLM), so every point is explainable."""
    parts = {}
    parts["sells_online"] = 40 if sells is True else 0
    parts["us_based"] = 10 if us is True else 0
    parts["trigger"] = max([TRIGGER_POINTS.get(t, 10) for t in triggers] or [0])
    parts["size_fit"] = 15 if size is True else (5 if size is None else 0)
    parts["contact_found"] = 5 if contact_ok else 0
    return sum(parts.values()), parts


def enrich_one(db, company):
    cid, name = company["id"], company["name"]
    print("Enrich:", name)
    triggers = db.table("evidence").select("*").eq("company_id", cid).eq("kind", "trigger").execute().data
    sources = [(t["source_url"], t["quote"]) for t in triggers]

    site_url, domain = pick_website(name)
    if site_url:
        text = cached_extract(site_url)
        if text:
            sources.append((site_url, text))
    contact_res = cached_search(f"{name} founder CEO COO", max_results=4)
    for r in contact_res.get("results", []):
        sources.append((r["url"], r.get("title", "") + ". " + r.get("content", "")))

    prompt = "\n\n".join(f"SOURCE {i} ({u}):\n{t}" for i, (u, t) in enumerate(sources))
    out = llm_json(f"Company: {name}\n\n{prompt}", QUALIFY_SYSTEM)

    sells, sells_url = verified(out.get("sells_online"), sources)
    us, us_url = verified(out.get("us_based"), sources)
    size, size_url = verified(out.get("size_fit"), sources)
    contact = out.get("contact") if isinstance(out.get("contact"), dict) else None
    contact_url = find_source(contact.get("quote") or "", sources) if contact else None
    contact_ok = bool(contact and contact.get("name") and contact_url)

    score, parts = score_company(sells, us, size, contact_ok, [t["trigger_kind"] for t in triggers])
    status = "qualified" if (sells is True and score >= 60) else "rejected"

    rows = []
    def add(claim, crit, url):
        rows.append({"company_id": cid, "kind": "fit", "claim": claim,
                     "quote": crit.get("quote"), "source_url": url})
    if sells is True: add("Sells products online", out["sells_online"], sells_url)
    if us is True: add("Based in the US", out["us_based"], us_url)
    if size is True: add("Size matches the target (revenue or team size)", out["size_fit"], size_url)
    if contact_ok:
        rows.append({"company_id": cid, "kind": "fact",
                     "claim": f"Contact: {contact['name']} ({contact.get('role', 'other')})",
                     "quote": contact.get("quote"), "source_url": contact_url})
    if rows:
        db.table("evidence").insert(rows).execute()

    channels = [c for c in (out.get("channels") or []) if isinstance(c, str)]
    db.table("companies").update({
        "website": site_url, "domain": domain, "description": out.get("description"),
        "sales_channels": channels,
        "contact_name": contact["name"] if contact_ok else None,
        "contact_role": contact.get("role") if contact_ok else None,
        "score": score, "score_breakdown": parts, "status": status,
    }).eq("id", cid).execute()
    print(f"   score {score} -> {status}")


def enrich_all(limit=None):
    db = get_db()
    q = db.table("companies").select("*").eq("status", "new").is_("score", "null")
    if limit:
        q = q.limit(limit)
    for c in q.execute().data:
        try:
            enrich_one(db, c)
        except Exception as e:
            print("   skipped:", str(e)[:120])


def status():
    rows = get_db().table("companies").select("status").execute().data
    print(dict(Counter(r["status"] for r in rows)), "total:", len(rows))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    n = int(sys.argv[2]) if len(sys.argv) > 2 else None
    actions = {"discover": lambda: discover(n), "enrich": lambda: enrich_all(n), "status": status}
    actions.get(cmd, lambda: print(__doc__))()
