from config.celery_config import celery_app
import time
from datetime import datetime
from typing import Any, Dict

from config.celery_config import celery_app
from src.ingestion.wb_reports import (
    create_warehouse_remains_task,
    get_warehouse_remains_status,
    download_warehouse_remains,
)

@celery_app.task(name="src.ingestion.tasks.generate_warehouse_remains_report",bind=True)
def generate_warehouse_remains_report(
    self,
    poll_interval: int = 10,
    max_attempts: int = 30,
    **params,
) -> Dict[str, Any]:
    task_id = create_warehouse_remains_task(**params)
    for attempt in range(1, max_attempts + 1):
        time.sleep(poll_interval)
        status = get_warehouse_remains_status(task_id)
        if status == "done":
            break
        if status in ("error", "cancelled"):
            raise RuntimeError(f"WB status={status}")
        self.update_state(
            state="PROGRESS",
            meta={"attempt": attempt, "status": status},
        )
    else:
        raise TimeoutError("Timeout waiting for WB warehouse report")

    data = download_warehouse_remains(task_id)

    filename = f"warehouse_remains_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(filename, "w", encoding="utf-8") as f:
        import json
        json.dump(data, f, ensure_ascii=False)

    return {"task_id": task_id, "rows": len(data), "filename": filename}
