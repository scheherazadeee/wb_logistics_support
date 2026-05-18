import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def log(msg):
    print(msg, flush=True) # flush=True ensures that the message is printed immediately


def banner(msg):
    log(f"\n{'='*60}\n  {msg}\n{'='*60}")


DATE_FROM = "2024-01-01"
DATE_TO   = "2024-12-31"


def step_warehouses():
    banner("1/5  Warehouses")
    from src.ingestion.wb_reports import get_warehouses
    from src.preprocessing.normalize import load_warehouses
    log("   fetching from WB...")
    data = get_warehouses()
    log(f"   got {len(data)} rows from WB, writing to DB...")
    rows = load_warehouses(data)
    log(f"loaded {rows} warehouses")


def step_region_sale():
    banner("2/5  Region sale (16 months)")
    from src.ingestion.wb_reports import date_chunks, get_region_sale
    from src.preprocessing.normalize import load_region_sale
    chunks = list(date_chunks(DATE_FROM, DATE_TO, chunk_days=31))
    for i, (f, t) in enumerate(chunks, 1):
        try:
            log(f"   [{i}/{len(chunks)}] fetching {f} - {t}...")
            rows = load_region_sale(get_region_sale(f, t))
            log(f"   [{i}/{len(chunks)}] {f} → {t}: {rows} rows")
        except Exception as e:
            log(f"   [{i}/{len(chunks)}] {f} → {t}:  FAILED — {e}")
        time.sleep(12)


def step_goods_return():
    banner("3/5  Goods return (16 months)")
    from src.ingestion.wb_reports import date_chunks, get_goods_return
    from src.preprocessing.normalize import load_goods_return
    chunks = list(date_chunks(DATE_FROM, DATE_TO, chunk_days=31))
    for i, (f, t) in enumerate(chunks, 1):
        try:
            log(f"   [{i}/{len(chunks)}] fetching {f} - {t}...")
            rows = load_goods_return(get_goods_return(f, t))
            log(f"   [{i}/{len(chunks)}] {f} → {t}: {rows} rows")
        except Exception as e:
            log(f"   [{i}/{len(chunks)}] {f} → {t}: FAILED — {e}")
        time.sleep(12)


def step_warehouse_remains():
    banner("4/5  Warehouse remains")
    from src.ingestion.wb_reports import get_warehouse_remains_report
    from src.preprocessing.normalize import load_warehouse_remains
    log("   creating WB task and polling...")
    data = get_warehouse_remains_report(locale="ru", groupByNm=True)
    log(f"   got {len(data)} rows from WB, writing to DB...")
    rows = load_warehouse_remains(data)
    log(f" loaded {rows} warehouse_remains")


def step_paid_storage():
    banner("5/7  Paid storage")
    from src.ingestion.wb_reports import date_chunks, get_paid_storage_report
    from src.preprocessing.normalize import load_paid_storage
    chunks = list(date_chunks(DATE_FROM, DATE_TO, chunk_days=7))
    for i, (f, t) in enumerate(chunks, 1):
        try:
            log(f"   [{i}/{len(chunks)}] {f} - {t}: creating task...")
            data = get_paid_storage_report(f, t, poll_interval=90, max_attempts=40)
            log(f"   [{i}/{len(chunks)}] {f} - {t}: got {len(data)} rows, writing to DB...")
            rows = load_paid_storage(data)
            log(f"   [{i}/{len(chunks)}] {f} - {t}:  {rows} rows")
        except Exception as e:
            log(f"   [{i}/{len(chunks)}] {f} - {t}:  FAILED — {e}")
        time.sleep(120)


def step_supplier_sales():
    banner("6/7  Supplier sales (продажи + возвраты)")
    from src.ingestion.wb_reports import get_supplier_sales
    from src.preprocessing.normalize import load_supplier_sales
    log("   fetching from WB...")
    data = get_supplier_sales(DATE_FROM)
    log(f"   got {len(data)} rows from WB, writing to DB...")
    rows = load_supplier_sales(data)
    log(f" loaded {rows} supplier_sales")


def step_supplier_orders():
    banner("7/8  Supplier orders")
    from src.ingestion.wb_reports import get_supplier_orders
    from src.preprocessing.normalize import load_supplier_orders
    log("   fetching from WB")
    data = get_supplier_orders(DATE_FROM)
    log(f"   got {len(data)} rows from WB, writing to DB...")
    rows = load_supplier_orders(data)
    log(f"    loaded {rows} supplier_orders")


def step_realization_report():
    banner("8/8  Realization report (up to 3 years)")
    from src.ingestion.wb_reports import date_chunks, get_report_detail_by_period
    from src.preprocessing.normalize import load_realization_report
    chunks = list(date_chunks(DATE_FROM, DATE_TO, chunk_days=30))
    for i, (f, t) in enumerate(chunks, 1):
        try:
            log(f"   [{i}/{len(chunks)}] {f} - {t}: fetching...")
            data = get_report_detail_by_period(f, t)
            rows = load_realization_report(data)
            log(f"   [{i}/{len(chunks)}] {f} - {t}:  {rows} rows")
        except Exception as e:
            log(f"   [{i}/{len(chunks)}] {f} - {t}:  FAILED — {e}")
        time.sleep(10)


STEPS = {
    "warehouses":         step_warehouses,
    "region_sale":        step_region_sale,
    "goods_return":       step_goods_return,
    "warehouse_remains":  step_warehouse_remains,
    "paid_storage":       step_paid_storage,
    "supplier_sales":     step_supplier_sales,
    "supplier_orders":    step_supplier_orders,
    "realization_report": step_realization_report,
}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=STEPS.keys(), help="запустить только один шаг") # парсер чтобы запускать только один шаг в случае фейла
    args = parser.parse_args()

    t0 = time.time()
    log(f"START at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        if args.only:
            STEPS[args.only]()
        else:

            step_region_sale()
            step_goods_return()
            step_warehouse_remains()
            step_paid_storage()
            step_supplier_sales()
            step_supplier_orders()
            step_realization_report()
    except KeyboardInterrupt: # catches ctrl+c
        log("\n Остановлено пользователем")
    except Exception as e:
        log(f"\n Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        elapsed = (time.time() - t0) / 60
        banner(f"DONE — {elapsed:.1f} минут")
