"""
Global gradient-boosting forecast model (LightGBM)
"""
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb


BEST_PARAMS_SHORT = {  # horizons 1-2 weeks
    "num_leaves":       20,
    "min_data_in_leaf": 74,
    "learning_rate":    0.024,
    "n_estimators":     525,
    "feature_fraction": 0.788,
    "bagging_fraction": 0.765,
}
BEST_PARAMS_LONG: dict = {}  # horizon >=4: empty = defaults are best


class LightGBMModel:

    def __init__(
        self,
        n_estimators: int = 500,
        learning_rate: float = 0.05,
        num_leaves: int = 31,
        min_data_in_leaf: int = 20,
        feature_fraction: float = 0.8,
        bagging_fraction: float = 0.8,
        bagging_freq: int = 5,
        random_state: int = 42,
        use_log_target: bool = True,
    ):
        self.params = dict(
            objective="regression_l1",   # L1 loss aligns with MAE / WAPE metrics
            metric="mae",
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            num_leaves=num_leaves,
            min_data_in_leaf=min_data_in_leaf,
            feature_fraction=feature_fraction,
            bagging_fraction=bagging_fraction,
            bagging_freq=bagging_freq,
            random_state=random_state,
            verbosity=-1,
        )
        self.use_log_target = use_log_target
        self.model: lgb.LGBMRegressor | None = None
        self.feature_cols: list[str] | None = None

    def _prepare_X(self, X: pd.DataFrame) -> pd.DataFrame:
        # Drop the week timestamp (can't be a feature) and cast SKU id
    
        df = X.drop(columns=["week"], errors="ignore").copy()
        if "nm_id" in df.columns:
            df["nm_id"] = df["nm_id"].astype("category")
        if "warehouse" in df.columns:
            df["warehouse"] = df["warehouse"].astype("category")
        return df

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LightGBMModel":
        X_prep = self._prepare_X(X)
        self.feature_cols = X_prep.columns.tolist()
        y_train = np.log1p(y.values) if self.use_log_target else y.values

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cat_feats = [c for c in ("nm_id", "warehouse") if c in X_prep.columns]
            self.model = lgb.LGBMRegressor(**self.params)
            self.model.fit(
                X_prep, y_train,
                categorical_feature=cat_feats if cat_feats else "auto",
            )
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X_prep = self._prepare_X(X)
        # Re-order columns to match training (lightgbm is sensitive to order).
        X_prep = X_prep[self.feature_cols]
        raw = self.model.predict(X_prep)
        out = np.expm1(raw) if self.use_log_target else raw
        return np.maximum(0.0, out)

    def feature_importance(self) -> pd.DataFrame:
        #Return feature gain importances sorted descending
        if self.model is None:
            raise RuntimeError("Model is not fitted yet")
        return pd.DataFrame({
            "feature": self.feature_cols,
            "importance": self.model.feature_importances_,
        }).sort_values("importance", ascending=False).reset_index(drop=True)
