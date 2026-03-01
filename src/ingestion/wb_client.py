import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("WB_API_KEY")
BASE_URL_ANALYTICS = "https://seller-analytics-api.wildberries.ru/api/v1"


def fetch_report(endpoint: str, params: dict):
    if not API_KEY:
        raise ValueError("WB_API_KEY is not found in .env")

    headers = {
        "Authorization": API_KEY
    }

    response = requests.get(
        endpoint,
        headers=headers,
        params=params,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()
