
import pandas as pd
import numpy as np
import holidays

from src.demand_model.data import get_full_weekly_panel


def _holiday_features(weeks: pd.Series) -> pd.DataFrame:
    """
    Calendar-holiday features for each week (Monday-aligned).

    Returns columns:
        is_holiday_week        — at least one RU public holiday in the week
        days_to_next_holiday   — distance from week start to nearest upcoming holiday
        n_holidays_in_week     — count of holidays in this week (proxy for "long weekend")
    """
    weeks = pd.to_datetime(weeks)
    years = sorted({w.year for w in weeks} | {w.year + 1 for w in weeks})
    ru_holidays = holidays.country_holidays("RU", years=years)
    holiday_dates = pd.to_datetime(sorted(ru_holidays.keys()))

    out = pd.DataFrame(index=weeks.index)
    n_in_week = []
    days_to_next = []
    for w in weeks:
        week_end = w + pd.Timedelta(days=6)
        in_week = ((holiday_dates >= w) & (holiday_dates <= week_end)).sum()
        future = holiday_dates[holiday_dates >= w]
        n_in_week.append(int(in_week))
        days_to_next.append(int((future[0] - w).days) if len(future) else 365)
    out["n_holidays_in_week"] = n_in_week
    out["days_to_next_holiday"] = days_to_next
    out["is_holiday_week"] = (out["n_holidays_in_week"] > 0).astype(int)
    return out


def build_features(
    panel: pd.DataFrame | None = None,
    horizon: int = 1,
) -> pd.DataFrame:
    """
    DataFrame with one row per (nm_id, week). Columns:
        Identifiers: nm_id, week, sa_name, subject_name, brand_name
        Lag features: lag_1w, lag_2w, lag_4w, lag_52w
        Rolling features: rolling_mean_4w, rolling_mean_12w, rolling_std_4w
        Calendar features: week_of_year, month, is_pre_8march, is_pre_ny
        Stock features: days_in_stock_lag_1w, weeks_stockout_last_4w
        Price features: price_lag_1w, price_4w_mean, price_change_vs_4w
        SKU attributes: weeks_since_first_sale, lifetime_units_so_far
        Target: target_units (units sold ``horizon`` weeks ahead)
        Mask: train_mask (True if row is safe to use in training)
    """
    if panel is None:
        panel = get_full_weekly_panel()

    # Auto-detect granularity: with warehouse column - group by (nm_id, warehouse),
    # otherwise the classic per-SKU panel.
    group_cols = ["nm_id", "warehouse"] if "warehouse" in panel.columns else ["nm_id"]
    df = panel.sort_values(group_cols + ["week"]).copy()
    df["week"] = pd.to_datetime(df["week"])
    g = df.groupby(group_cols, sort=False)

    # текущая неделя — известна в момент прогноза, нужна для Naive baseline
    df["units_current"] = df["units"]

    # старые продажи
    for lag in [1, 2, 4, 52]:
        df[f"lag_{lag}w"] = g["units"].shift(lag)

    # helper: group keys to use for any per-series operation (handles both panels)
    group_keys = [df[c] for c in group_cols]

    # скользящая статистика
    units_shifted = g["units"].shift(1) # не берем текущую неделю
    df["rolling_mean_4w"] = units_shifted.groupby(group_keys).transform(
        lambda s: s.rolling(4, min_periods=1).mean()
    )
    df["rolling_mean_12w"] = units_shifted.groupby(group_keys).transform(
        lambda s: s.rolling(12, min_periods=1).mean()
    )
    df["rolling_std_4w"] = units_shifted.groupby(group_keys).transform(
        lambda s: s.rolling(4, min_periods=2).std()
    )

   
    df["week_of_year"] = df["week"].dt.isocalendar().week.astype(int)
    df["month"] = df["week"].dt.month.astype(int)
    df["year"] = df["week"].dt.year.astype(int)
    df["is_pre_8march"] = df["week_of_year"].between(7, 9).astype(int) # недели до 8 марта
    df["is_pre_ny"] = df["week_of_year"].between(49, 52).astype(int) # до НГ

    # holidays
    hf = _holiday_features(df["week"])
    df["is_holiday_week"] = hf["is_holiday_week"].values
    df["n_holidays_in_week"] = hf["n_holidays_in_week"].values
    df["days_to_next_holiday"] = hf["days_to_next_holiday"].values

    # проверяем сток
    df["days_in_stock_lag_1w"] = g["days_in_stock"].shift(1)
    stockout_shifted = (g["days_in_stock"].shift(1) == 0).astype(int)
    df["weeks_stockout_last_4w"] = stockout_shifted.groupby(group_keys).transform(
        lambda s: s.rolling(4, min_periods=1).sum()
    )

    # цены
    df["price_lag_1w"] = g["avg_price"].shift(1)
    df["price_4w_mean"] = g["avg_price"].shift(1).groupby(group_keys).transform(
        lambda s: s.rolling(4, min_periods=1).mean()
    )
    df["price_change_vs_4w"] = df["price_lag_1w"] / df["price_4w_mean"]

    # лайфтайм артикула
    first_week = g["week"].transform("min")
    df["weeks_since_first_sale"] = ((df["week"] - first_week).dt.days // 7).astype(int)
    df["lifetime_units_so_far"] = g["units"].transform(lambda s: s.shift(1).cumsum())

    for level_col, prefix in [("subject_name", "subject")]:
        weekly_level = (
            df.groupby([level_col, "week"], as_index=False)["units"].sum()
            .rename(columns={"units": f"{prefix}_units_total"})
        )
        # 1-week lag and 4-week rolling mean on the level series
        weekly_level = weekly_level.sort_values([level_col, "week"])
        weekly_level[f"{prefix}_lag_1w"] = (
            weekly_level.groupby(level_col)[f"{prefix}_units_total"].shift(1)
        )
        weekly_level[f"{prefix}_rolling_mean_4w"] = (
            weekly_level.groupby(level_col)[f"{prefix}_units_total"]
            .shift(1).groupby(weekly_level[level_col])
            .transform(lambda s: s.rolling(4, min_periods=1).mean())
        )
        # year-ago value — captures the level's own seasonality
        weekly_level[f"{prefix}_lag_52w"] = (
            weekly_level.groupby(level_col)[f"{prefix}_units_total"].shift(52)
        )
        df = df.merge(
            weekly_level[[level_col, "week",
                          f"{prefix}_lag_1w",
                          f"{prefix}_rolling_mean_4w",
                          f"{prefix}_lag_52w"]],
            on=[level_col, "week"], how="left",
        )

    # таргет - продажи за horison недель  вперед
    df["target_units"] = g["units"].shift(-horizon)

    # пропускаем стокаут - маска
    target_stock = g["days_in_stock"].shift(-horizon)
    df["train_mask"] = df["target_units"].notna() & (target_stock > 0)

    keep = [
        "nm_id", "week", "sa_name", "subject_name", "brand_name",
    ]
    if "warehouse" in df.columns:
        keep.append("warehouse")
    keep += [
        "units_current",
        "lag_1w", "lag_2w", "lag_4w", "lag_52w",
        "rolling_mean_4w", "rolling_mean_12w", "rolling_std_4w",
        "week_of_year", "month", "year", "is_pre_8march", "is_pre_ny",
        "is_holiday_week", "n_holidays_in_week", "days_to_next_holiday",
        "days_in_stock_lag_1w", "weeks_stockout_last_4w",
        "price_lag_1w", "price_4w_mean", "price_change_vs_4w",
        "weeks_since_first_sale", "lifetime_units_so_far",
        "subject_lag_1w", "subject_rolling_mean_4w", "subject_lag_52w",
        "target_units", "train_mask",
    ]
    return df[keep].reset_index(drop=True)
