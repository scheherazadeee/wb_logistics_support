import numpy as np
import pandas as pd


class BaselineModel:
    """Base class. Subclasses just override ``feature_col``."""

    feature_col: str = ""
    fallback_col: str = "units_current"  # if feature col = NaN

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "BaselineModel":
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        pred = X[self.feature_col].copy()
        if self.fallback_col and self.fallback_col != self.feature_col:
            pred = pred.fillna(X[self.fallback_col]) # if  fallback_col also NaN, fill woth 0
        return pred.fillna(0).clip(lower=0).values # remove negative values 


class NaiveModel(BaselineModel):
    feature_col = "units_current"
    fallback_col = ""


class SeasonalNaiveModel(BaselineModel):
    feature_col = "lag_52w"
    fallback_col = "units_current"  # fall back to Naive when no 52w history yet


class MA4Model(BaselineModel):
    feature_col = "rolling_mean_4w"
    fallback_col = "units_current"


class MA12Model(BaselineModel):
    feature_col = "rolling_mean_12w"
    fallback_col = "units_current"


BASELINES = {
    "Naive":          NaiveModel(),
    "SeasonalNaive":  SeasonalNaiveModel(),
    "MA4":            MA4Model(),
    "MA12":           MA12Model(),
}
