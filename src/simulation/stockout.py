"""
Stockout simulation
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Historical snapshot — treated as "today" throughout all simulations - for validation 
SNAPSHOT_DATE = pd.Timestamp("2024-12-31")

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
ENGINE = create_engine(os.getenv("DATABASE_URL"))


# Current stock

def get_current_stock(nm_id: int) -> Dict[str, int]:
    """
    Excludes summary rows and 'В пути'
    """
    sql = text("""
        SELECT warehouse_name, SUM(quantity) AS quantity
        FROM warehouse_remains
        WHERE nm_id = :nm_id
          AND quantity > 0
          AND warehouse_name NOT ILIKE 'Всего%'
          AND warehouse_name NOT ILIKE 'В пути%'
        GROUP BY warehouse_name
    """)
    df = pd.read_sql(sql, ENGINE, params={"nm_id": nm_id})
    if df.empty:
        return {}
    return dict(zip(df["warehouse_name"], df["quantity"].astype(int)))

# Demand forecast (recent-average mode)

def forecast_recent_demand(
    nm_id: int,
    warehouses: list[str],
    n_weeks: int = 8,
    recent_weeks: int = 4,
) -> pd.DataFrame:
    """
    Estimate future weekly demand per warehouse using the average of the last
    ``recent_weeks`` weeks of realized sales
    """
    snap_week_start = SNAPSHOT_DATE.to_period("W-MON").start_time
    cutoff   = (snap_week_start - pd.Timedelta(weeks=recent_weeks)).date()
    snap_end = (SNAPSHOT_DATE + pd.Timedelta(days=1)).date()

    # Реальное количество понедельничных недель в окне наблюдения.
    # Делим на него, а не только на недели с продажами — иначе
    # для товаров, которые были в стоке часть периода, спрос завышается.
    import math
    total_weeks_in_window = math.ceil(
        ((snap_end - cutoff).days) / 7
    )

    sql = text("""
        SELECT
            office_name                                             AS warehouse,
            SUM(week_units)::float / :total_weeks                  AS avg_weekly_demand
        FROM (
            SELECT
                office_name,
                date_trunc('week', sale_dt)::date    AS wk,
                SUM(quantity)                        AS week_units
            FROM realization_report
            WHERE doc_type_name = 'Продажа'
              AND nm_id = :nm_id
              AND sale_dt >= :cutoff
              AND sale_dt <  :snap_end
              AND office_name IS NOT NULL
            GROUP BY office_name, date_trunc('week', sale_dt)
            HAVING SUM(quantity) > 0
        ) sub
        WHERE office_name = ANY(:warehouses)
        GROUP BY office_name
    """)
    df = pd.read_sql(
        sql, ENGINE,
        params={"nm_id": nm_id, "cutoff": cutoff, "snap_end": snap_end,
                "warehouses": warehouses, "total_weeks": total_weeks_in_window},
    )
    rate = dict(zip(df["warehouse"], df["avg_weekly_demand"].astype(float)))

    today_week = SNAPSHOT_DATE.to_period("W-MON").start_time
    future_weeks = [
        (today_week + pd.Timedelta(weeks=i)).date() for i in range(n_weeks)
    ]

    rows = []
    for wh in warehouses:
        avg = rate.get(wh, 0.0)
        for wk in future_weeks:
            rows.append({"warehouse": wh, "week": wk, "demand": avg})
    return pd.DataFrame(rows)

# Core simulation
def simulate_stockout(
    stock_per_warehouse: Dict[str, float],
    demand_forecast: pd.DataFrame,
) -> pd.DataFrame:
    """
    Week-by-week depletion simulation.

    Parameters
    stock_per_warehouse : {warehouse: units}
        Starting inventory at each warehouse.
    demand_forecast : DataFrame(warehouse, week, demand)
        Forecast demand consumed each week (must cover enough weeks to exhaust stock).

    Returns
    DataFrame with one row per warehouse:
        warehouse, initial_stock, stockout_date, days_until_stockout,
        weeks_of_cover, trajectory (list of end-of-week stock levels)
    """
    today = SNAPSHOT_DATE.normalize()
    demand_forecast = demand_forecast.copy()
    demand_forecast["week"] = pd.to_datetime(demand_forecast["week"])

    results = []
    for warehouse, initial_stock in stock_per_warehouse.items():
        wh_demand = (
            demand_forecast[demand_forecast["warehouse"] == warehouse]
            .sort_values("week")
            .reset_index(drop=True)
        )

        stock = float(initial_stock)
        stockout_date: Optional[pd.Timestamp] = None
        trajectory: list[float] = []
        weeks_covered = 0

        for _, row in wh_demand.iterrows():
            week_start = pd.Timestamp(row["week"])
            demand = max(0.0, float(row["demand"]))

            if stock <= 0:
                trajectory.append(0.0)
                continue

            stock -= demand
            weeks_covered += 1

            if stock <= 0:
                # linear interpolation within the week
                overflow = -stock
                fraction = (1.0 - overflow / demand) if demand > 0 else 0.0
                fraction = max(0.0, min(1.0, fraction))
                stockout_date = week_start + pd.Timedelta(days=round(fraction * 7))
                trajectory.append(0.0)
            else:
                trajectory.append(round(stock, 1))

        if stockout_date is None and stock > 0:
            # stock survives the entire forecast horizon
            days_until = None
            weeks_of_cover = None
        else:
            days_until = int((stockout_date - today).days) if stockout_date else None
            weeks_of_cover = round(weeks_covered - 1 + (
                float(initial_stock) / max(1e-9, float(
                    demand_forecast[demand_forecast["warehouse"] == warehouse]["demand"].mean()
                ))
            ) % 1, 1) if stockout_date else None

        results.append({
            "warehouse": warehouse,
            "initial_stock": int(initial_stock),
            "stockout_date": stockout_date.date() if stockout_date else None,
            "days_until_stockout": days_until,
            "weeks_of_cover": weeks_of_cover,
            "trajectory": trajectory,
        })

    return pd.DataFrame(results).sort_values(
        "days_until_stockout",
        na_position="last",
    ).reset_index(drop=True)

# Main entry point
def run_simulation(
    nm_id: int,
    allocation: Optional[Dict[str, float]] = None,
    n_weeks: int = 12,
    demand_forecast: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Full stockout simulation for one SKU.
    """
    # 1. Stock
    if allocation is not None:
        stock = {wh: float(qty) for wh, qty in allocation.items() if qty > 0}
    else:
        stock = {wh: float(qty) for wh, qty in get_current_stock(nm_id).items()}

    if not stock:
        return pd.DataFrame(columns=[
            "warehouse", "initial_stock", "stockout_date",
            "days_until_stockout", "weeks_of_cover", "trajectory",
        ])

    warehouses = list(stock.keys())

    # 2. Demand forecast
    if demand_forecast is None:
        demand_forecast = forecast_recent_demand(nm_id, warehouses, n_weeks)
    else:
        demand_forecast = demand_forecast[
            demand_forecast["warehouse"].isin(warehouses)
        ].copy()

    # 3. Simulate
    return simulate_stockout(stock, demand_forecast)
