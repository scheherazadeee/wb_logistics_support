"""
Hyperparameter tuning for LightGBM using Optuna (Bayesian optimization)
"""
import warnings
from typing import Optional
import optuna
import pandas as pd

from src.demand_model.lgbm import LightGBMModel
from src.demand_model.backtest import backtest


def tune_lightgbm(
    features: pd.DataFrame,
    n_trials: int = 50,
    min_train_weeks: int = 60,
    n_splits: int = 12,
    seed: int = 42,
    verbose: bool = True,
) -> dict:
    
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "num_leaves":        trial.suggest_int("num_leaves", 4, 64),
            "min_data_in_leaf":  trial.suggest_int("min_data_in_leaf", 10, 100),
            "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators":      trial.suggest_int("n_estimators", 100, 800),
            "feature_fraction":  trial.suggest_float("feature_fraction", 0.5, 1.0),
            "bagging_fraction":  trial.suggest_float("bagging_fraction", 0.5, 1.0),
        }
        model = LightGBMModel(**params, random_state=seed)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, metrics = backtest(
                model, features,
                min_train_weeks=min_train_weeks,
                n_splits=n_splits,
            )
        return metrics["WAPE"]

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    if verbose:
        def _cb(_study, trial):
            print(f"  trial {trial.number:3d}: WAPE={trial.value:.4f} "
                  f"(best so far {_study.best_value:.4f})", flush=True)
        study.optimize(objective, n_trials=n_trials, callbacks=[_cb])
    else:
        study.optimize(objective, n_trials=n_trials)

    return study.best_params
