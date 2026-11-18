"""Very simple retrieval: finds the most relevant text chunks by keyword overlap.
Good enough for a small demo. Replace with embeddings (Chroma, pgvector) if the case needs it."""
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def _words(text: str) -> set:
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))


def load_chunks() -> list:
    chunks = []
    for f in DATA.glob("*.md"):
        for part in f.read_text(encoding="utf-8").split("\n\n"):
            if part.strip():
                chunks.append(part.strip())
    return chunks


def search(query: str, k: int = 3) -> list:
    q = _words(query)
    scored = [(len(q & _words(c)), c) for c in load_chunks()]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored[:k] if s > 0]
