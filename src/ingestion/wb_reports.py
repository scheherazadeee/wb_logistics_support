import time
from typing import List, Dict, Optional
from src.ingestion.wb_client import fetch_report, BASE_URL_ANALYTICS

BASE_URL_SUPPLIES = "https://supplies-api.wildberries.ru/api/v1"


# --- Warehouses & Acceptance Coefficients ---

def get_warehouses() -> List[Dict]:
    endpoint = f"{BASE_URL_SUPPLIES}/warehouses"
    return fetch_report(endpoint, params={})


def get_coefficients(date_from: str, date_to: Optional[str] = None,
                     limit: int = 100000) -> List[Dict]:
    endpoint = f"{BASE_URL_SUPPLIES}/acceptance/coefficients"
    params = {"dateFrom": date_from, "limit": limit}
    if date_to:
        params["dateTo"] = date_to
    return fetch_report(endpoint, params)


# --- Warehouse Remains ---

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


def get_warehouse_remains_report(
    poll_interval: int = 10,
    max_attempts: int = 30,
    **params,
) -> List[Dict]:
    task_id = create_warehouse_remains_task(**params)
    print(f"Создан отчёт, taskId = {task_id}")

    for _ in range(max_attempts):
        time.sleep(poll_interval)
        status = get_warehouse_remains_status(task_id)
        if status == "done":
            break
        if status in ("error", "cancelled"):
            raise RuntimeError(f"WB warehouse_remains status={status}")
    else:
        raise TimeoutError("Превышено время ожидания готовности отчёта")

    return download_warehouse_remains(task_id)


# --- Region Sale ---

def get_region_sale(date_from: str, date_to: str,
                    limit: int = 100000, offset: int = 0) -> List[Dict]:
    endpoint = f"{BASE_URL_ANALYTICS}/analytics/region-sale"
    params = {
        "dateFrom": date_from,
        "dateTo": date_to,
        "limit": limit,
        "offset": offset,
    }
    return fetch_report(endpoint, params)["report"]


# --- Goods Return ---

def get_goods_return(date_from: str, date_to: str,
                     limit: int = 100000, offset: int = 0) -> List[Dict]:
    endpoint = f"{BASE_URL_ANALYTICS}/analytics/goods-return"
    params = {
        "dateFrom": date_from,
        "dateTo": date_to,
        "limit": limit,
        "offset": offset,
    }
    return fetch_report(endpoint, params)["report"]


# --- Paid Storage ---

def create_paid_storage_task(date_from: str, date_to: str) -> str:
    # WB API allows max 7 days per request for paid_storage
    endpoint = f"{BASE_URL_ANALYTICS}/paid_storage"
    params = {"dateFrom": date_from, "dateTo": date_to}
    data = fetch_report(endpoint, params)
    return data["data"]["taskId"]


def get_paid_storage_status(task_id: str) -> str:
    endpoint = f"{BASE_URL_ANALYTICS}/paid_storage/tasks/{task_id}/status"
    data = fetch_report(endpoint, params={})
    return data["data"]["status"]


def download_paid_storage(task_id: str) -> List[Dict]:
    endpoint = f"{BASE_URL_ANALYTICS}/paid_storage/tasks/{task_id}/download"
    return fetch_report(endpoint, params={})


def get_paid_storage_report(
    date_from: str,
    date_to: str,
    poll_interval: int = 10,
    max_attempts: int = 30,
) -> List[Dict]:
    task_id = create_paid_storage_task(date_from, date_to)
    print(f"Создан отчёт, taskId = {task_id}")

    for _ in range(max_attempts):
        time.sleep(poll_interval)
        status = get_paid_storage_status(task_id)
        if status == "done":
            break
        if status in ("error", "cancelled"):
            raise RuntimeError(f"WB paid_storage status={status}")
    else:
        raise TimeoutError("Превышено время ожидания готовности отчёта")

    return download_paid_storage(task_id)

