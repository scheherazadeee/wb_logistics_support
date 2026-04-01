import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from config.celery_config import celery_app

RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
from src.ingestion.wb_reports import (
    get_warehouse_remains_report,
    get_paid_storage_report,
    get_region_sale,
    get_goods_return,
)


@celery_app.task(name="src.ingestion.tasks.generate_warehouse_remains_report")
def generate_warehouse_remains_report(poll_interval: int = 10, max_attempts: int = 30, **params) -> Dict[str, Any]:
    data = get_warehouse_remains_report(poll_interval=poll_interval, max_attempts=max_attempts, **params)
    filename = f"warehouse_remains_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(RAW_DATA_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return {"rows": len(data), "filename": filename}


@celery_app.task(name="src.ingestion.tasks.generate_paid_storage_report")
def generate_paid_storage_report(date_from: str, date_to: str, poll_interval: int = 10, max_attempts: int = 30) -> Dict[str, Any]:
    data = get_paid_storage_report(date_from=date_from, date_to=date_to, poll_interval=poll_interval, max_attempts=max_attempts)
    filename = f"paid_storage_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(RAW_DATA_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return {"rows": len(data), "filename": filename}


@celery_app.task(name="src.ingestion.tasks.generate_region_sale_report")
def generate_region_sale_report(date_from: str, date_to: str, limit: int = 100000, offset: int = 0) -> Dict[str, Any]:
    data = get_region_sale(date_from=date_from, date_to=date_to, limit=limit, offset=offset)
    filename = f"region_sale_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(RAW_DATA_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return {"rows": len(data), "filename": filename}


@celery_app.task(name="src.ingestion.tasks.generate_goods_return_report")
def generate_goods_return_report(date_from: str, date_to: str, limit: int = 100000, offset: int = 0) -> Dict[str, Any]:
    data = get_goods_return(date_from=date_from, date_to=date_to, limit=limit, offset=offset)
    filename = f"goods_return_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(RAW_DATA_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return {"rows": len(data), "filename": filename}
