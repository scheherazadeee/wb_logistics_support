import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.cost_model.costs import _acceptance_table
from src.optimization.allocate import optimize_sku_allocation
from src.simulation.stockout import (
    forecast_recent_demand,
    get_current_stock,
    run_simulation,
)
from src.ingestion.wb_reports import get_box_tariffs, parse_tariff_coef

ENGINE = create_engine(os.getenv("DATABASE_URL"))

# Historical snapshot date — queries treat this as "today"
SNAPSHOT = "2024-12-31"

app = FastAPI(title="WB Logistics API", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/static/index.html")


# Warehouse coordinates (WB warehouses, approximate)

WAREHOUSE_COORDS: dict[str, tuple[float, float]] = {
    "Коледино":          (55.27, 37.77),
    "Подольск":          (55.43, 37.55),
    "Краснодар":         (45.04, 38.97),
    "Хабаровск":         (48.48, 135.08),
    "Екатеринбург":      (56.83, 60.60),
    "Казань":            (55.79, 49.12),
    "Новосибирск":       (54.99, 82.90),
    "Санкт-Петербург":   (59.95, 30.32),
    "Электросталь":      (55.79, 38.44),
    "Тула":              (54.19, 37.62),
    "Вёшки":             (55.99, 37.44),
    "Белые Столбы":      (55.38, 37.70),
    "Пушкино":           (56.01, 37.85),
    "Тверь":             (56.86, 35.91),
    "Рязань":            (54.63, 39.73),
    "Уфа":               (54.74, 55.97),
    "Ростов-на-Дону":    (47.22, 39.72),
    "Владивосток":       (43.12, 131.90),
    "Иркутск":           (52.29, 104.30),
    "Омск":              (54.99, 73.37),
    "Волгоград":         (48.71, 44.51),
    "Воронеж":           (51.67, 39.18),
    "Самара":            (53.20, 50.15),
    "Пермь":             (58.01, 56.24),
    "Нижний Новгород":   (56.33, 44.00),
    "Ярославль":         (57.63, 39.87),
    "Барнаул":           (53.35, 83.74),
    "Красноярск":        (56.01, 92.85),
    "Тюмень":            (57.15, 68.97),
    "Челябинск":         (55.15, 61.40),
}


def _resolve_coords(name: str) -> tuple[float | None, float | None]:
    if name in WAREHOUSE_COORDS:
        return WAREHOUSE_COORDS[name]
    name_lower = name.lower()
    for key, coords in WAREHOUSE_COORDS.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return coords
    return None, None


def _status(days: float | None) -> str:
    if days is None:
        return "ok"
    if days < 14:
        return "critical"
    if days < 30:
        return "warning"
    return "ok"


# GET /api/overview

@app.get("/api/overview")
def overview():
    # Portfolio-wide weekly sales (last 12 weeks)
    sales_sql = text("""
        SELECT date_trunc('week', sale_dt)::date AS week,
               SUM(quantity)                      AS units
        FROM realization_report
        WHERE doc_type_name = 'Продажа'
          AND sale_dt >= :snap::date - INTERVAL '84 days'
          AND sale_dt <  :snap::date + INTERVAL '1 day'
        GROUP BY 1 ORDER BY 1
    """)
    sales_df = pd.read_sql(sales_sql, ENGINE, params={"snap": SNAPSHOT})

    # SKU summary: stock + quick days-of-cover estimate
    sku_sql = text("""
        SELECT
            wr.nm_id,
            SUM(wr.quantity)               AS total_stock,
            COUNT(DISTINCT wr.warehouse_name) AS n_warehouses
        FROM warehouse_remains wr
        WHERE wr.nm_id > 0 AND wr.quantity > 0
        GROUP BY wr.nm_id
    """)
    sku_df = pd.read_sql(sku_sql, ENGINE)

    # daily demand per SKU (last 30 days)
    demand_sql = text("""
        SELECT nm_id,
               SUM(quantity)::float / 30 AS daily_demand
        FROM realization_report
        WHERE doc_type_name = 'Продажа'
          AND sale_dt >= :snap::date - INTERVAL '30 days'
          AND sale_dt <  :snap::date + INTERVAL '1 day'
          AND nm_id > 0
        GROUP BY nm_id
    """)
    demand_df = pd.read_sql(demand_sql, ENGINE, params={"snap": SNAPSHOT})
    sku_df = sku_df.merge(demand_df, on="nm_id", how="left")
    sku_df["daily_demand"] = sku_df["daily_demand"].fillna(0)
    sku_df["days_of_cover"] = np.where(
        sku_df["daily_demand"] > 0,
        sku_df["total_stock"] / sku_df["daily_demand"],
        None,
    )

    critical = int((sku_df["days_of_cover"] < 14).sum())
    warning  = int(((sku_df["days_of_cover"] >= 14) & (sku_df["days_of_cover"] < 30)).sum())

    return {
        "total_skus":    int(len(sku_df)),
        "total_units":   int(sku_df["total_stock"].sum()),
        "n_warehouses":  int(sku_df["n_warehouses"].max() if len(sku_df) else 0),
        "critical_count": critical,
        "warning_count":  warning,
        "sales_chart": [
            {"week": str(r["week"]), "units": int(r["units"])}
            for _, r in sales_df.iterrows()
        ],
    }

# GET /api/skus


@app.get("/api/skus")
def skus():
    sql = text("""
        SELECT
            wr.nm_id,
            MAX(rr.sa_name)      AS sa_name,
            MAX(rr.subject_name) AS subject_name,
            MAX(rr.brand_name)   AS brand_name,
            SUM(wr.quantity)     AS total_stock,
            COUNT(DISTINCT wr.warehouse_name) AS n_warehouses
        FROM warehouse_remains wr
        LEFT JOIN realization_report rr ON rr.nm_id = wr.nm_id
        WHERE wr.nm_id > 0 AND wr.quantity > 0
        GROUP BY wr.nm_id
        ORDER BY total_stock DESC
    """)
    df = pd.read_sql(sql, ENGINE)

    demand_sql = text("""
        SELECT nm_id, SUM(quantity)::float / 30 AS daily_demand
        FROM realization_report
        WHERE doc_type_name = 'Продажа'
          AND sale_dt >= :snap::date - INTERVAL '30 days'
          AND sale_dt <  :snap::date + INTERVAL '1 day'
          AND nm_id > 0
        GROUP BY nm_id
    """)
    demand_df = pd.read_sql(demand_sql, ENGINE, params={"snap": SNAPSHOT})
    df = df.merge(demand_df, on="nm_id", how="left")
    df["daily_demand"] = df["daily_demand"].fillna(0)
    df["days_of_cover"] = np.where(
        df["daily_demand"] > 0,
        (df["total_stock"] / df["daily_demand"]).round(0),
        None,
    )

    result = []
    for _, r in df.iterrows():
        doc = float(r["days_of_cover"]) if r["days_of_cover"] is not None and not np.isnan(r["days_of_cover"]) else None
        result.append({
            "nm_id":          int(r["nm_id"]),
            "sa_name":        r["sa_name"] or "—",
            "subject_name":   r["subject_name"] or "—",
            "brand_name":     r["brand_name"] or "—",
            "total_stock":    int(r["total_stock"]),
            "n_warehouses":   int(r["n_warehouses"]),
            "days_of_cover":  int(doc) if doc is not None else None,
            "status":         _status(doc),
        })

    result.sort(key=lambda x: (
        {"critical": 0, "warning": 1, "ok": 2}[x["status"]],
        x["days_of_cover"] if x["days_of_cover"] is not None else 9999,
    ))
    return result


# GET /api/sku/{nm_id}

@app.get("/api/sku/{nm_id}")
def sku_detail(nm_id: int):
    # Info
    info_sql = text("""
        SELECT MAX(sa_name) sa_name, MAX(subject_name) subject_name,
               MAX(brand_name) brand_name
        FROM realization_report WHERE nm_id = :nm_id
    """)
    info_df = pd.read_sql(info_sql, ENGINE, params={"nm_id": nm_id})
    if info_df.empty:
        raise HTTPException(404, "SKU not found")
    info = info_df.iloc[0].fillna("—").to_dict()

    # Current stock
    stock = get_current_stock(nm_id)
    if not stock:
        raise HTTPException(404, "No warehouse_remains for this SKU")

    # Stockout simulation (current state)
    sim = run_simulation(nm_id, n_weeks=12)
    sim_out = []
    for _, r in sim.iterrows():
        sim_out.append({
            "warehouse":          r["warehouse"],
            "initial_stock":      int(r["initial_stock"]),
            "stockout_date":      str(r["stockout_date"]) if r["stockout_date"] else None,
            "days_until_stockout": int(r["days_until_stockout"]) if r["days_until_stockout"] is not None else None,
            "weeks_of_cover":     float(r["weeks_of_cover"]) if r["weeks_of_cover"] is not None else None,
            "status":             _status(r["days_until_stockout"]),
        })

    # Demand history (last 16 weeks)
    hist_sql = text("""
        SELECT date_trunc('week', sale_dt)::date AS week,
               SUM(quantity)                      AS units
        FROM realization_report
        WHERE doc_type_name = 'Продажа'
          AND nm_id = :nm_id
          AND sale_dt >= :snap::date - INTERVAL '112 days'
          AND sale_dt <  :snap::date + INTERVAL '1 day'
        GROUP BY 1 ORDER BY 1
    """)
    hist_df = pd.read_sql(hist_sql, ENGINE, params={"nm_id": nm_id, "snap": SNAPSHOT})

    return {
        "info":   {**info, "nm_id": nm_id},
        "stock":  [{"warehouse": k, "quantity": v} for k, v in stock.items()],
        "simulation": sim_out,
        "demand_history": [
            {"week": str(r["week"]), "units": int(r["units"])}
            for _, r in hist_df.iterrows()
        ],
    }


# POST /api/optimize
class OptimizeRequest(BaseModel):
    nm_id:       int
    total_units: int
    n_weeks:     int = 8


@app.post("/api/optimize")
def optimize(req: OptimizeRequest):
    if req.total_units <= 0:
        raise HTTPException(400, "total_units must be > 0")

    stock = get_current_stock(req.nm_id)
    if not stock:
        raise HTTPException(404, "No warehouse stock data for this SKU")

    warehouses = list(stock.keys())
    forecast = forecast_recent_demand(req.nm_id, warehouses, req.n_weeks)

    # Demand totals for the full horizon
    demand_by_wh = (
        forecast.groupby("warehouse")["demand"].sum().to_dict()
    )

    alloc_df = optimize_sku_allocation(
        nm_id=req.nm_id,
        total_supply=req.total_units,
        demand_per_warehouse=demand_by_wh,
        days_horizon=req.n_weeks * 7,
    )

    proposed = dict(zip(alloc_df["warehouse"], alloc_df["allocated"]))
    proposed = {k: v for k, v in proposed.items() if v > 0}

    sim_proposed = run_simulation(
        req.nm_id,
        allocation=proposed,
        n_weeks=req.n_weeks,
        demand_forecast=forecast,
    )
    sim_current = run_simulation(req.nm_id, n_weeks=req.n_weeks)

    def _sim_rows(sim):
        rows = []
        for _, r in sim.iterrows():
            rows.append({
                "warehouse":           r["warehouse"],
                "initial_stock":       int(r["initial_stock"]),
                "stockout_date":       str(r["stockout_date"]) if r["stockout_date"] else None,
                "days_until_stockout": int(r["days_until_stockout"]) if r["days_until_stockout"] is not None else None,
                "status":              _status(r["days_until_stockout"]),
            })
        return rows

    allocation_out = []
    for _, r in alloc_df.iterrows():
        if r["allocated"] <= 0:
            continue
        # Find proposed stockout
        proposed_row = sim_proposed[sim_proposed["warehouse"] == r["warehouse"]]
        new_days = int(proposed_row["days_until_stockout"].iloc[0]) if not proposed_row.empty and proposed_row["days_until_stockout"].iloc[0] is not None else None
        allocation_out.append({
            "warehouse":           r["warehouse"],
            "allocated":           int(round(r["allocated"])),
            "demand":              round(float(r["demand"]), 1),
            "storage_cost":        round(float(r["storage_cost"]), 0),
            "stockout_cost":       round(float(r["stockout_cost"]), 0),
            "total_cost":          round(float(r["total_cost"]), 0),
            "new_days_until_stockout": new_days,
            "status":              _status(new_days),
        })

    return {
        "allocation":          allocation_out,
        "total_storage_cost":  round(float(alloc_df["storage_cost"].sum()), 0),
        "total_stockout_cost": round(float(alloc_df["stockout_cost"].sum()), 0),
        "total_cost":          round(float(alloc_df["total_cost"].sum()), 0),
        "current_simulation":  _sim_rows(sim_current),
        "proposed_simulation": _sim_rows(sim_proposed),
    }


# GET /api/warehouses

@app.get("/api/warehouses")
def warehouses():
    #Stock per warehouse
    stock_sql = text("""
        WITH sku_cover AS (
            SELECT
                wr.warehouse_name,
                wr.nm_id,
                wr.quantity                                          AS stock,
                COALESCE(d.daily_demand, 0)                         AS daily_demand,
                CASE WHEN COALESCE(d.daily_demand, 0) > 0
                     THEN wr.quantity / d.daily_demand ELSE NULL END AS days_of_cover
            FROM warehouse_remains wr
            LEFT JOIN (
                SELECT office_name AS warehouse, nm_id,
                       SUM(quantity)::float / 30 AS daily_demand
                FROM realization_report
                WHERE doc_type_name = 'Продажа'
                  AND sale_dt >= '2024-12-31'::date - INTERVAL '30 days'
                  AND sale_dt <  '2024-12-31'::date + INTERVAL '1 day'
                  AND nm_id > 0 AND office_name IS NOT NULL
                GROUP BY office_name, nm_id
            ) d ON d.warehouse = wr.warehouse_name AND d.nm_id = wr.nm_id
            WHERE wr.quantity > 0 AND wr.nm_id > 0
        )
        SELECT
            warehouse_name                                                       AS name,
            SUM(stock)                                                           AS total_units,
            COUNT(DISTINCT nm_id)                                                AS sku_count,
            MIN(days_of_cover)                                                   AS min_days_of_cover,
            COUNT(*) FILTER (WHERE days_of_cover IS NOT NULL AND days_of_cover < 14)   AS critical_skus,
            COUNT(*) FILTER (WHERE days_of_cover >= 14 AND days_of_cover < 30)         AS warning_skus
        FROM sku_cover
        GROUP BY warehouse_name
        ORDER BY total_units DESC
    """)
    df = pd.read_sql(stock_sql, ENGINE)

    #Demand concentration by region
    demand_sql = text("""
        SELECT region_name,
               SUM(sale_item_invoice_qty) AS total_qty
        FROM region_sale
        WHERE sale_item_invoice_qty > 0
        GROUP BY region_name
        ORDER BY total_qty DESC
    """)
    demand_df = pd.read_sql(demand_sql, ENGINE)

    #Real tariffs from WB API
    try:
        raw_tariffs = get_box_tariffs()
        tariff_map = {
            t["warehouseName"]: {
                "delivery_coef": parse_tariff_coef(t.get("boxDeliveryCoefExpr", "100")),
                "storage_coef":  parse_tariff_coef(t.get("boxStorageCoefExpr", "100")),
                "delivery_base": t.get("boxDeliveryBase", "—"),
                "storage_base":  t.get("boxStorageBase", "—"),
                "geo":           t.get("geoName", ""),
            }
            for t in raw_tariffs
        }
    except Exception:
        tariff_map = {}

    #Compose warehouse list
    warehouses_out = []
    for _, r in df.iterrows():
        name = r["name"]
        lat, lng = _resolve_coords(name)
        t = tariff_map.get(name, {})
        min_doc = r["min_days_of_cover"]
        min_doc = float(min_doc) if min_doc is not None and not np.isnan(float(min_doc)) else None

        warehouses_out.append({
            "name":             name,
            "lat":              lat,
            "lng":              lng,
            "total_units":      int(r["total_units"]),
            "sku_count":        int(r["sku_count"]),
            "critical_skus":    int(r["critical_skus"]),
            "warning_skus":     int(r["warning_skus"]),
            "min_days_of_cover": round(min_doc, 0) if min_doc else None,
            # real tariffs from WB API
            "delivery_coef":    t.get("delivery_coef"),   # e.g. 1.95
            "storage_coef":     t.get("storage_coef"),    # e.g. 1.45
            "delivery_base":    t.get("delivery_base", "—"),  # e.g. "89,7 ₽"
            "storage_base":     t.get("storage_base", "—"),
            "geo":              t.get("geo", ""),
        })

    #Demand by region
    regions_out = [
        {"region": r["region_name"], "qty": int(r["total_qty"])}
        for _, r in demand_df.iterrows()
        if r["region_name"]
    ]

    return {
        "warehouses": warehouses_out,
        "demand_by_region": regions_out,
    }
