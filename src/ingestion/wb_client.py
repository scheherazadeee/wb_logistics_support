import os
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
API_KEY = os.getenv("WB_API_KEY")
BASE_URL_ANALYTICS  = "https://seller-analytics-api.wildberries.ru/api/v1"
BASE_URL_STATISTICS = "https://statistics-api.wildberries.ru/api/v1"
BASE_URL_COMMON     = "https://common-api.wildberries.ru/api/v1"


def fetch_report(endpoint: str, params: dict, retries: int = 5, default_wait: int = 120):
    if not API_KEY:
        raise ValueError("WB_API_KEY is not found in .env")

    headers = {"Authorization": API_KEY}

    for attempt in range(retries):
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=180)
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.SSLError) as e:
            wait = 30 * (attempt + 1)  # 30, 60, 90, 120, 150
            print(f"Network error (attempt {attempt+1}/{retries}): {type(e).__name__}, retrying in {wait}s...")
            time.sleep(wait)
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("X-Ratelimit-Retry") \
                       or response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after else default_wait
            wait += 2
            print(f"Rate limited (attempt {attempt+1}/{retries}), WB asks to wait {wait}s...")
            time.sleep(wait)
            continue

        response.raise_for_status()

        # Proactive throttle: if bucket is almost empty, sleep until refill
        remaining = response.headers.get("X-Ratelimit-Remaining")
        reset = response.headers.get("X-Ratelimit-Reset")
        if remaining is not None and reset is not None:
            try:
                if int(remaining) <= 1:
                    print(f"Bucket almost empty (remaining={remaining}), sleeping {reset}s preemptively...")
                    time.sleep(int(reset) + 2)
            except (ValueError, TypeError):
                pass

        return response.json()

    raise RuntimeError(f"Failed after {retries} retries due to rate limiting")
