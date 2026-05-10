"""Перезапуск только goods_return"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATE_FROM = "2025-01-01"
DATE_TO   = "2026-04-30"

from src.ingestion.wb_reports import date_chunks, get_goods_return
from src.preprocessing.normalize import load_goods_return

chunks = list(date_chunks(DATE_FROM, DATE_TO, chunk_days=31))
total = 0
for i, (f, t) in enumerate(chunks, 1):
    try:
        print(f"[{i}/{len(chunks)}] {f} → {t}: fetching...", flush=True)
        rows = load_goods_return(get_goods_return(f, t))
        total += rows
        print(f"[{i}/{len(chunks)}] {f} → {t}: ✓ {rows} rows", flush=True)
    except Exception as e:
        print(f"[{i}/{len(chunks)}] {f} → {t}: ✗ FAILED — {e}", flush=True)
    time.sleep(12)

print(f"\nДобавлено всего: {total} строк", flush=True)
