from typing import List, Dict
from dotenv import load_dotenv
from src.ingestion.wb_client import fetch_report, BASE_URL_ANALYTICS



def create_warehouse_remains_task(**params) -> str:
    endpoint = f"{BASE_URL_ANALYTICS}/warehouse_remains"
    data = fetch_report(endpoint, params)
    return data["data"]["taskId"]

def get_warehouse_remains_status(task_id: str) -> str:
    endpoint = f"{BASE_URL_ANALYTICS}/warehouse_remains/tasks/{task_id}/status"
    data = fetch_report(endpoint, params={})
    return data["data"]["status"]


def download_warehouse_remains(task_id: str) -> List[Dict]:
    endpoint = f"{BASE_URL_ANALYTICS}/warehouse_remains/tasks/{task_id}/download"
    return fetch_report(endpoint, params={})

    
    
    
