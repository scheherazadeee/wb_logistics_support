import time
from datetime import date, timedelta
from typing import Iterator, List, Dict, Optional, Tuple
from src.ingestion.wb_client import fetch_report, BASE_URL_ANALYTICS, BASE_URL_COMMON

BASE_URL_SUPPLIES = "https://supplies-api.wildberries.ru/api/v1"

# some reports accept only 7 days per request
def date_chunks(date_from: str, date_to: str, chunk_days: int = 7) -> Iterator[Tuple[str, str]]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    current = start
    while current <= end:
        #timedelta is used to be able to add days to the current date
        # otherwise int and datetime are not compatible
        chunk_end = min(current + timedelta(days=chunk_days - 1), end) 
        yield current.isoformat(), chunk_end.isoformat()
        current = chunk_end + timedelta(days=1)


def backfill_paid_storage(date_from: str, date_to: str, rate_limit_sleep: int = 65) -> List[Dict]:
    #Fetch paid_storage for an arbitrary date range, respecting the 7-day chunk limit and 1-req/min rate limit
    all_data = []
    chunks = list(date_chunks(date_from, date_to))
    for i, (chunk_from, chunk_to) in enumerate(chunks):
        data = get_paid_storage_report(date_from=chunk_from, date_to=chunk_to)
        all_data.extend(data)
        print(f"[{i+1}/{len(chunks)}] {chunk_from} → {chunk_to}: {len(data)} rows")
        if i < len(chunks) - 1:
            time.sleep(rate_limit_sleep)
    return all_data


# Warehouses & Acceptance Coefficients

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


# Warehouse Remains 

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


# Region Sale

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


# Goods Return

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


# Paid Storage

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



# тарифы по складам

def get_box_tariffs(tariff_date: Optional[str] = None) -> List[Dict]:
    """
    GET /api/v1/tariffs/box — тарифы на доставку коробов по каждому складу WB.

    Возвращает список складов с полями:
        warehouseName          — название склада
        geoName                — федеральный округ
        boxDeliveryBase        — базовая стоимость доставки (₽/короб)
        boxDeliveryCoefExpr    — коэффициент стоимости в % (100 = стандарт, 195 = дороже)
        boxDeliveryLiter       — стоимость за литр объёма
        boxStorageBase         — базовая стоимость хранения (₽/короб/день)
        boxStorageCoefExpr     — коэффициент хранения в %
        boxStorageLiter        — хранение за литр

    Если дата не указана — берётся сегодня.
    """
    if tariff_date is None:
        from datetime import date as _date
        tariff_date = _date.today().isoformat()
    endpoint = f"{BASE_URL_COMMON}/tariffs/box"
    data = fetch_report(endpoint, params={"date": tariff_date})
    return data.get("response", {}).get("data", {}).get("warehouseList", [])


def parse_tariff_coef(raw: str) -> Optional[float]:
    if not raw or raw.strip() == "-":
        return None
    try:
        return float(raw.replace(",", ".")) / 100.0
    except ValueError:
        return None
