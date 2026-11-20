"""Database access. One shared Supabase client for the whole backend."""
import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
_db = None


def get_db():
    global _db
    if _db is None:
        url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is missing in .env")
        _db = create_client(url, key)
    return _db
