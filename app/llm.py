"""Small helper around the AI API. Everything that talks to the AI goes through here.
Set PROVIDER in .env:  gemini (free)  |  groq (free)  |  anthropic (paid)
"""
import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("PROVIDER", "gemini").lower()

# (api key variable, default model, base url for OpenAI-compatible providers)
PROVIDERS = {
    "gemini": ("GEMINI_API_KEY", "gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    "groq": ("GROQ_API_KEY", "llama-3.3-70b-versatile", "https://api.groq.com/openai/v1"),
    "anthropic": ("ANTHROPIC_API_KEY", "claude-sonnet-5-5", None),
}

if PROVIDER not in PROVIDERS:
    raise RuntimeError(f"PROVIDER must be one of {list(PROVIDERS)}")

KEY_VAR, DEFAULT_MODEL, BASE_URL = PROVIDERS[PROVIDER]
MODEL = os.getenv("MODEL") or DEFAULT_MODEL
_client = None


def get_client():
    global _client
    if _client is None:
        key = os.getenv(KEY_VAR)
        if not key or key.startswith("paste-"):
            raise RuntimeError(f"{KEY_VAR} is missing. Put it in the .env file.")
        if PROVIDER == "anthropic":
            from anthropic import Anthropic
            _client = Anthropic(api_key=key)
        else:
            from openai import OpenAI
            _client = OpenAI(api_key=key, base_url=BASE_URL, timeout=30, max_retries=1)
    return _client


def ask(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 1000) -> str:
    """Send a prompt, get plain text back."""
    client = get_client()
    if PROVIDER == "anthropic":
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content or ""


def ask_json(prompt: str, system: str = "", max_tokens: int = 1000) -> dict:
    """Ask the AI to answer with JSON only, then parse it safely."""
    system = (system + "\nReply with ONLY valid JSON. No markdown, no extra text.").strip()
    text = ask(prompt, system=system, max_tokens=max_tokens)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "model did not return valid JSON", "raw": text}
