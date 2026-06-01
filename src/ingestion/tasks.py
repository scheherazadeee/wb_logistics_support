import json
import time
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
    date_chunks,
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


@celery_app.task(name="src.ingestion.tasks.backfill_paid_storage")
def backfill_paid_storage_task(date_from: str, date_to: str, rate_limit_sleep: int = 65) -> Dict[str, Any]:
    """Backfill paid_storage for a multi-month range. Runs in background — safe to leave overnight."""
    from src.preprocessing.normalize import load_paid_storage

    total_rows = 0
    chunks = list(date_chunks(date_from, date_to))
    for i, (chunk_from, chunk_to) in enumerate(chunks):
        data = get_paid_storage_report(date_from=chunk_from, date_to=chunk_to)
        rows = load_paid_storage(data)
        total_rows += rows
        if i < len(chunks) - 1:
            time.sleep(rate_limit_sleep)
    return {"total_rows": total_rows, "chunks_processed": len(chunks)}


@celery_app.task(name="src.ingestion.tasks.backfill_region_sale")
def backfill_region_sale_task(date_from: str, date_to: str) -> Dict[str, Any]:
    from src.preprocessing.normalize import load_region_sale

    total_rows = 0
    for month_from, month_to in date_chunks(date_from, date_to, chunk_days=31):
        data = get_region_sale(date_from=month_from, date_to=month_to)
        total_rows += load_region_sale(data)
    return {"total_rows": total_rows}


@celery_app.task(name="src.ingestion.tasks.backfill_goods_return")
def backfill_goods_return_task(date_from: str, date_to: str) -> Dict[str, Any]:
    from src.preprocessing.normalize import load_goods_return

    total_rows = 0
    for month_from, month_to in date_chunks(date_from, date_to, chunk_days=31):
        data = get_goods_return(date_from=month_from, date_to=month_to)
        total_rows += load_goods_return(data)
    return {"total_rows": total_rows}
