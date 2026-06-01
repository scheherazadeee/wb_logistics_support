from typing import List
import pandas as pd
from sqlalchemy import text

from src.demand_model.data import get_full_warehouse_weekly_panel, ENGINE
from src.demand_model.features import build_features
from src.demand_model.lgbm import LightGBMModel, BEST_PARAMS_LONG
from src.optimization.allocate import optimize_sku_allocation
from src.cost_model.costs import (
    storage_cost_per_unit_per_day,
    stockout_cost_per_unit,
    acceptance_coefficient,
)


def get_real_allocation(week: pd.Timestamp) -> pd.DataFrame:
    """Average stock per (nm_id, warehouse) during the given calendar week."""
    sql = text("""
        SELECT nm_id, warehouse,
               AVG(barcodes_count) FILTER (WHERE barcodes_count > 0) AS units
        FROM paid_storage
        WHERE date_trunc('week', date) = :wk
          AND nm_id > 0
        GROUP BY nm_id, warehouse
        HAVING AVG(barcodes_count) FILTER (WHERE barcodes_count > 0) > 0
    """)
    df = pd.read_sql(sql, ENGINE, params={"wk": week.date()})
    df["units"] = df["units"].astype(float)
    return df


def expected_cost(allocation: pd.DataFrame, forecast: pd.DataFrame,
                  days_horizon: int) -> dict:
    merged = allocation.merge(forecast, on=["nm_id", "warehouse"], how="outer")
    merged[["units", "demand"]] = merged[["units", "demand"]].fillna(0.0)

    storage = stockout = 0.0
    for _, r in merged.iterrows():
        nm_id, wh = int(r["nm_id"]), r["warehouse"]
        x, d = float(r["units"]), float(r["demand"])
        storage += (storage_cost_per_unit_per_day(nm_id, wh)
                    * acceptance_coefficient(wh) * days_horizon * x)
        stockout += stockout_cost_per_unit(nm_id) * max(0.0, d - x)
    return {"storage": storage, "stockout": stockout, "total": storage + stockout}


def _build_naive_allocation(forecast: pd.DataFrame, supply_per_sku: dict) -> pd.DataFrame:
    """Naive policy: distribute total supply equally across warehouses with active forecast"""
    rows = []
    for nm_id, g in forecast.groupby("nm_id"):
        active = g[g["demand"] > 0]
        if active.empty:
            continue
        per_wh = supply_per_sku.get(int(nm_id), 0) / len(active)
        for _, r in active.iterrows():
            rows.append({"nm_id": int(nm_id), "warehouse": r["warehouse"], "units": per_wh})
    return pd.DataFrame(rows)


def _build_lp_allocation(forecast: pd.DataFrame, supply_per_sku: dict,
                         days_horizon: int) -> pd.DataFrame:
    """LP policy: per-SKU optimal allocation"""
    rows = []
    for nm_id, g in forecast.groupby("nm_id"):
        supply = supply_per_sku.get(int(nm_id), 0)
        if supply <= 0:
            continue
        demand = dict(zip(g["warehouse"], g["demand"]))
        r = optimize_sku_allocation(int(nm_id), int(supply), demand, days_horizon)
        for _, row in r.iterrows():
            rows.append({"nm_id": int(nm_id), "warehouse": row["warehouse"],
                         "units": row["allocated"]})
    return pd.DataFrame(rows)


def validate_strategies(
    test_weeks: List[pd.Timestamp],
    horizon: int = 4,
) -> pd.DataFrame:
    """
    Compare REAL / LP / NAIVE policies on every test week.
    """
    days_horizon = horizon * 7
    panel = get_full_warehouse_weekly_panel()
    features = build_features(panel, horizon=horizon)
    fcols = [c for c in features.columns
             if c not in {"sa_name", "subject_name", "brand_name",
                          "target_units", "train_mask"}]

    results = []
    for tw in test_weeks:
        train = features[(features["week"] < tw) & features["train_mask"]]
        test = features[features["week"] == tw].copy()
        if train.empty or test.empty:
            continue

        # 1. Train model and forecast
        model = LightGBMModel(**BEST_PARAMS_LONG)
        model.fit(train[fcols], train["target_units"])
        test["demand"] = model.predict(test[fcols])
        forecast = test[["nm_id", "warehouse", "demand"]]

        # 2. Real allocation at week T, supply per SKU = real total
        real = get_real_allocation(tw)
        if real.empty:
            continue
        supply_per_sku = real.groupby("nm_id")["units"].sum().astype(int).to_dict()

        # 3. Three policies, same total supply per SKU
        real_alloc = real.rename(columns={"units": "units"})
        lp_alloc   = _build_lp_allocation(forecast, supply_per_sku, days_horizon)
        naive_alloc = _build_naive_allocation(forecast, supply_per_sku)

        # 4. Costs evaluated against the forecast
        for name, alloc in [("REAL", real_alloc), ("LP", lp_alloc), ("NAIVE", naive_alloc)]:
            c = expected_cost(alloc, forecast, days_horizon)
            results.append({
                "test_week": tw, "strategy": name,
                "storage_rub": c["storage"],
                "stockout_rub": c["stockout"],
                "total_rub": c["total"],
                "supply_total": sum(supply_per_sku.values()),
            })

    return pd.DataFrame(results)
