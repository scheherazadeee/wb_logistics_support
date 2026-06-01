from dataclasses import dataclass
from typing import Iterable
import numpy as np
import pandas as pd


# mertrics


def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Weighted Absolute Percentage Error - robust to zero actuals"""
    total = np.abs(y_true).sum()
    if total == 0:
        return np.nan
    return float(np.abs(y_true - y_pred).sum() / total)


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error — average error in units"""
    return float(np.abs(y_true - y_pred).mean())


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error — penalises large misses"""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {"WAPE": wape(y_true, y_pred), "MAE": mae(y_true, y_pred), "RMSE": rmse(y_true, y_pred)}


# backtest core


@dataclass
class BacktestSplit:
    test_week: pd.Timestamp
    train_size: int
    test_size: int


def make_splits(
    features: pd.DataFrame,
    min_train_weeks: int = 60,
    n_splits: int = 12,
) -> list[pd.Timestamp]:

    weeks = sorted(pd.to_datetime(features["week"].unique()))
    if len(weeks) <= min_train_weeks + 1:
        raise ValueError(
            f"Not enough history: have {len(weeks)} weeks, need > {min_train_weeks + 1}"
        )
    pool = weeks[min_train_weeks:]
    if n_splits >= len(pool):
        return pool
    step = len(pool) / n_splits
    return [pool[int(i * step)] for i in range(n_splits)]


def backtest(
    model,
    features: pd.DataFrame,
    splits: Iterable[pd.Timestamp] | None = None,
    min_train_weeks: int = 60,
    n_splits: int = 12,
    evaluate_only_in_stock: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """
    Run rolling-window backtest and return per-split results + aggregated metrics.

    Parameters
    model : object with .fit(X, y) and .predict(X)
    features : DataFrame from build_features()
    splits : optional explicit test weeks; if None, generated automatically
    evaluate_only_in_stock : whether to filter test rows by stock availability

    Returns
    per_split : DataFrame with one row per (test_week, nm_id) containing
                target, prediction, error
    overall : dict of aggregated metrics across all splits
    """

    df = features.copy()
    df["week"] = pd.to_datetime(df["week"])
    if splits is None:
        splits = make_splits(df, min_train_weeks, n_splits)

    # Keep nm_id and week — per-SKU models (Holt-Winters etc.) need them
    feature_cols = [c for c in df.columns
                    if c not in {"sa_name", "subject_name", "brand_name",
                                  "target_units", "train_mask"}]

    results = []
    for test_week in splits:
        train = df[(df["week"] < test_week) & df["train_mask"]]
        test = df[df["week"] == test_week]
        if evaluate_only_in_stock:
            test = test[test["train_mask"]]
        if train.empty or test.empty:
            continue

        X_train, y_train = train[feature_cols], train["target_units"]
        X_test, y_test = test[feature_cols], test["target_units"]
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        has_wh = "warehouse" in test.columns
        wh_vals = test["warehouse"].values if has_wh else [None] * len(test)
        for nm_id, wh, target, pred in zip(test["nm_id"].values, wh_vals, y_test.values, y_pred):
            row = {
                "test_week": test_week,
                "nm_id":     nm_id,
                "target":    target,
                "prediction": pred,
                "abs_error": abs(target - pred),
            }
            if has_wh:
                row["warehouse"] = wh
            results.append(row)

    per_split = pd.DataFrame(results)
    if per_split.empty:
        return per_split, {}

    overall = compute_metrics(per_split["target"].values, per_split["prediction"].values)
    return per_split, overall


def compare_models(
    models: dict,
    features: pd.DataFrame,
    **backtest_kwargs,
) -> pd.DataFrame:
    """
    Run backtest for several models on the same splits, return one row per model
    """
    splits = make_splits(
        features,
        min_train_weeks=backtest_kwargs.get("min_train_weeks", 60),
        n_splits=backtest_kwargs.get("n_splits", 12),
    )
    rows = []
    for name, model in models.items():
        _, metrics = backtest(model, features, splits=splits, **{
            k: v for k, v in backtest_kwargs.items()
            if k not in {"min_train_weeks", "n_splits"}
        })
        rows.append({"model": name, **metrics})
    return pd.DataFrame(rows).sort_values("WAPE").reset_index(drop=True)
