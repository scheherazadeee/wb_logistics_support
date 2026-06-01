"""
Классификация артикулов по плотности и длине истории продаж.
"""
from typing import Literal
import pandas as pd

from src.demand_model.data import get_full_weekly_panel


SkuClass = Literal["MATURE", "SPARSE", "NEW"] # создаёт тип, который может принимать только одно из трёх указанных строковых значений


def classify_skus(
    panel: pd.DataFrame | None = None,
    *, # после * можно передавать только по имени (keyword-only arguments)
    min_weeks_mature: int = 12,
    min_units_per_week: float = 1.0,
) -> pd.DataFrame:
    """
        min_weeks_mature   — минимум недель чтобы НЕ считаться NEW (по умолч. 12 ≈ 3 мес)
        min_units_per_week — средняя плотность для MATURE (по умолч. 1.0) 

    Колонки результата:
        nm_id, subject_name, brand_name, sa_name,
        weeks_history       — сколько недель в panel
        total_units         — все продажи за историю
        avg_units_per_week  — средняя плотность (с учётом нулевых недель)
        zero_week_pct       — доля нулевых недель
        stock_coverage_pct  — доля недель когда был сток
        last_sale_week      — дата последней ненулевой продажи
        weeks_since_sale    — сколько недель назад была последняя продажа
        sku_class           — MATURE | SPARSE | NEW
    """
    if panel is None:
        panel = get_full_weekly_panel()

    today_week = pd.Timestamp.today().to_period("W-MON").start_time.date()

    rows = []
    for nm_id, g in panel.groupby("nm_id"):
        weeks_history = len(g)
        total_units = int(g["units"].sum())
        avg_per_week = g["units"].mean()
        zero_pct = (g["units"] == 0).mean()
        stock_pct = (g["days_in_stock"] > 0).mean()

        non_zero = g[g["units"] > 0]
        last_sale = non_zero["week"].max() if len(non_zero) else None
        weeks_since_sale = (
            (today_week - last_sale).days // 7 if last_sale else weeks_history
        )

        # правила классификации
        if weeks_history < min_weeks_mature:
            cls: SkuClass = "NEW"
        elif avg_per_week < min_units_per_week:
            cls = "SPARSE"
        else:
            cls = "MATURE"

        meta = g[["subject_name", "brand_name", "sa_name"]].iloc[0].to_dict()
        rows.append({
            "nm_id":              nm_id,
            **meta,
            "weeks_history":      weeks_history,
            "total_units":        total_units,
            "avg_units_per_week": round(float(avg_per_week), 2),
            "zero_week_pct":      round(float(zero_pct), 2),
            "stock_coverage_pct": round(float(stock_pct), 2),
            "last_sale_week":     last_sale,
            "weeks_since_sale":   weeks_since_sale,
            "sku_class":          cls,
        })

    return pd.DataFrame(rows).sort_values(
        ["sku_class", "total_units"], ascending=[True, False]
    ).reset_index(drop=True)


def class_summary(classification: pd.DataFrame) -> pd.DataFrame:
    return classification.groupby("sku_class").agg(
        n_skus=("nm_id", "count"),
        median_weeks=("weeks_history", "median"),
        median_units=("total_units", "median"),
        median_avg_per_week=("avg_units_per_week", "median"),
        median_zero_pct=("zero_week_pct", "median"),
        median_stock_pct=("stock_coverage_pct", "median"),
    ).reset_index()
