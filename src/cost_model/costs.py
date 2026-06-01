"""
Cost model for warehouse-distribution optimization.
    1. Storage cost     — actual rubles paid per unit per day, taken from the
                          historical `paid_storage.warehouse_price` series.
    2. Stockout cost    — lost margin per unsold unit. Estimated as the
                          average `ppvz_for_pay` per unit from past sales.
    3. Acceptance proxy — multiplicative penalty for shipping to "expensive"
                          warehouses.
"""
import os
from pathlib import Path
from functools import lru_cache
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
ENGINE = create_engine(os.getenv("DATABASE_URL"))


# storage cost
@lru_cache(maxsize=1)
def _storage_cost_table() -> pd.DataFrame:
    """
    Columns: nm_id, warehouse, rub_per_unit_per_day, warehouse_coef
    """
    sql = text("""
        SELECT
            nm_id,
            warehouse,
            AVG(warehouse_price / NULLIF(barcodes_count, 0))::numeric(10,4)
                AS rub_per_unit_per_day,
            AVG(warehouse_coef)::numeric(10,3) AS warehouse_coef
        FROM paid_storage
        WHERE nm_id > 0 AND barcodes_count > 0 AND warehouse_price > 0
        GROUP BY nm_id, warehouse
    """)
    return pd.read_sql(sql, ENGINE)


def storage_cost_per_unit_per_day(nm_id: int, warehouse: str) -> float:
    """Average historical storage cost for one unit of nm_id at warehouse for one day"""
    t = _storage_cost_table()
    row = t[(t["nm_id"] == nm_id) & (t["warehouse"] == warehouse)]
    if not row.empty:
        return float(row["rub_per_unit_per_day"].iloc[0])
    fallback = t[t["warehouse"] == warehouse]["rub_per_unit_per_day"].mean()
    if pd.notna(fallback):
        return float(fallback)
    return float(t["rub_per_unit_per_day"].mean())


def weekly_storage_cost(nm_id: int, warehouse: str, units: int) -> float:
    """Total storage cost for `units` of nm_id at warehouse over one week"""
    return storage_cost_per_unit_per_day(nm_id, warehouse) * units * 7


# stockout cost
@lru_cache(maxsize=1)
def _stockout_cost_table() -> pd.DataFrame:
    """
    Average payout to the seller per unit sold, by nm_id. This is the lost
    revenue if a unit cannot be sold due to stockout
    Columns: nm_id, rub_per_unit, n_sales
    """
    sql = text("""
        SELECT
            nm_id,
            SUM(ppvz_for_pay) / NULLIF(SUM(quantity), 0) AS rub_per_unit,
            SUM(quantity)::int AS n_sales
        FROM realization_report
        WHERE doc_type_name = 'Продажа' AND nm_id > 0 AND quantity > 0
        GROUP BY nm_id
        HAVING SUM(quantity) > 0
    """)
    return pd.read_sql(sql, ENGINE)


def stockout_cost_per_unit(nm_id: int) -> float:
    """Lost margin per unit that the seller could not ship due to stockout"""
    t = _stockout_cost_table()
    row = t[t["nm_id"] == nm_id]
    if not row.empty:
        return float(row["rub_per_unit"].iloc[0])
    return float(t["rub_per_unit"].mean())


# acceptance proxy
@lru_cache(maxsize=1)
def _acceptance_table() -> pd.DataFrame:
    """
    Per-warehouse acceptance penalty proxy.
    Columns: warehouse, acceptance_coef
    """
    sql = text("""
        SELECT warehouse,
               AVG(warehouse_coef)::numeric(10,3) AS acceptance_coef
        FROM paid_storage
        WHERE warehouse_coef IS NOT NULL
        GROUP BY warehouse
    """)
    return pd.read_sql(sql, ENGINE)


def acceptance_coefficient(warehouse: str) -> float:
    """Multiplicative penalty for shipping to warehouse (1.0 - standard, >1 - expensive)"""
    t = _acceptance_table()
    row = t[t["warehouse"] == warehouse]
    if not row.empty:
        return float(row["acceptance_coef"].iloc[0])
    return float(t["acceptance_coef"].mean())


# aggregate 

def total_cost(
    allocation: pd.DataFrame,
    demand_forecast: pd.DataFrame,
    days_horizon: int = 7,
) -> dict:
    """
    Compute total expected cost of a proposed allocation over the planning horizon.

    Parameters
    ----------
    allocation : DataFrame with columns (nm_id, warehouse, units_stocked)
        How many units of each SKU we plan to keep at each warehouse.
    demand_forecast : DataFrame with columns (nm_id, warehouse, units_expected)
        How many units of each SKU we expect to sell from each warehouse.
    days_horizon : int
        Length of the planning period (default 7)

    Returns dict with keys:
        storage   — total storage cost over the horizon (rub)
        stockout  — total expected stockout cost (rub)
        total     — sum
    """
    merged = allocation.merge(demand_forecast,
                              on=["nm_id", "warehouse"], how="outer").fillna(0)

    storage = 0.0
    stockout = 0.0
    for _, row in merged.iterrows(): # a gnerator to loop through rows
        nm_id = int(row["nm_id"])
        wh = row["warehouse"]
        stock = float(row.get("units_stocked", 0))
        demand = float(row.get("units_expected", 0))

        # storage cost — pay for everything we keep, for the whole horizon
        storage += storage_cost_per_unit_per_day(nm_id, wh) * stock * days_horizon \
                   * acceptance_coefficient(wh)

        # stockout cost — pay margin for demand that exceeds stock
        unmet = max(0.0, demand - stock)
        stockout += stockout_cost_per_unit(nm_id) * unmet

    return {"storage": storage, "stockout": stockout, "total": storage + stockout}
