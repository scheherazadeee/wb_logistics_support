"""
Holt-Winters (triple exponential smoothing) forecasting model.

Decomposes each series into level + trend + seasonal components and updates
each via exponential smoothing

"""
import warnings
from typing import Optional
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from src.demand_model.data import get_full_weekly_panel


class HoltWintersModel:

    def __init__(
        self,
        panel: Optional[pd.DataFrame] = None,
        season_length: int = 52,
        trend: Optional[str] = "add",
        seasonal: Optional[str] = "add",
        damped_trend: bool = True,
        min_weeks_seasonal: int = 104,   # 2 full cycles required by statsmodels
        min_weeks_trend: int = 12,
        horizon: int = 1,
    ):
        self.panel = panel if panel is not None else get_full_weekly_panel()
        self.panel = self.panel.copy()
        self.panel["week"] = pd.to_datetime(self.panel["week"])
        self.season_length = season_length
        self.trend = trend
        self.seasonal = seasonal
        self.damped_trend = damped_trend
        self.min_weeks_seasonal = min_weeks_seasonal
        self.min_weeks_trend = min_weeks_trend
        self.horizon = horizon
        self._latest_train_week: Optional[pd.Timestamp] = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "HoltWintersModel":
        # запоминает, до какой недели можно использовать данные для обучения
        self._latest_train_week = pd.to_datetime(X["week"].max())
        return self

    def _forecast_one(self, series: np.ndarray) -> float:
        series = series.astype(float)
        if len(series) == 0:
            return 0.0
        last = float(series[-1])

        # Tier 1: full Holt-Winters with seasonality (needs 2 full cycles)
        if len(series) >= self.min_weeks_seasonal:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = ExponentialSmoothing(
                        series,
                        trend=self.trend,
                        seasonal=self.seasonal,
                        seasonal_periods=self.season_length,
                        damped_trend=self.damped_trend,
                        initialization_method="estimated",
                    ).fit()
                return max(0.0, float(model.forecast(self.horizon)[-1]))
            except Exception:
                pass

        # Tier 2: Holt (level + trend, no seasonality)
        if len(series) >= self.min_weeks_trend:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = ExponentialSmoothing(
                        series,
                        trend=self.trend,
                        seasonal=None,
                        damped_trend=self.damped_trend,
                        initialization_method="estimated",
                    ).fit()
                return max(0.0, float(model.forecast(self.horizon)[-1]))
            except Exception:
                pass

        # Tier 3: Naive fallback (same value regardless of horizon)
        return last

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        # Each test row corresponds to "we are at week T, predict T+1".
        weeks = pd.to_datetime(X["week"])
        nm_ids = X["nm_id"].values
        preds = np.zeros(len(X), dtype=float)

        for i, (nm_id, week_t) in enumerate(zip(nm_ids, weeks)):
            sub = self.panel[
                (self.panel["nm_id"] == nm_id) & (self.panel["week"] <= week_t)
            ].sort_values("week")
            series = sub["units"].to_numpy()
            preds[i] = self._forecast_one(series)

        return preds
