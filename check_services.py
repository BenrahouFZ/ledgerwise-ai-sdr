import os
import httpx
from dotenv import load_dotenv

load_dotenv()

# 1. Supabase
from supabase import create_client
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
rows = sb.table("companies").select("id").limit(1).execute()
print("Supabase OK, rows:", len(rows.data))

# 2. Tavily
from tavily import TavilyClient
tv = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
res = tv.search("Shopify e-commerce brand hiring accountant", max_results=2)
print("Tavily OK, results:", len(res["results"]))

# 3. Cal.com
r = httpx.get(
    "https://api.cal.com/v2/event-types",
    headers={"Authorization": "Bearer " + os.getenv("CALCOM_API_KEY"),
             "cal-api-version": "2024-06-14"},
    timeout=20,
)
print("Cal.com status:", r.status_code)
print(r.text[:300])