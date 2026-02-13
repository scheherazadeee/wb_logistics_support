import os
import requests 
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("WB_API_KEY")

def fetch_report(endpoint: str, params: dict):
    if not API_KEY:
        raise ValueError("WB_API_KEY is not found in .env")
    
    headers = {
        "Authorization": API_KEY
    }

    # GET request for Willdberries
    response = requests.get(
        endpoint,
        headers=headers, #the key for authorization (hidden for safe security)
        params=params  # Parametrs of the requesr (date for example)
    )

    response.raise_for_status() # checking errors
    
    return response.json()
