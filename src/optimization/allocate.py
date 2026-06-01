"""
Warehouse allocation optimizer.
The problem is solved per SKU using PuLP + CBC
"""
from typing import Dict, Optional
import pandas as pd
import pulp

from src.cost_model.costs import (
    storage_cost_per_unit_per_day,
    stockout_cost_per_unit,
    acceptance_coefficient,
)


def optimize_sku_allocation(
    nm_id: int,
    total_supply: int,
    demand_per_warehouse: Dict[str, float],
    days_horizon: int = 7,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Solve allocation LP for one SKU

    Parameters:
    nm_id : int
    total_supply : int
    demand_per_warehouse : dict
    days_horizon : int         

    Returns:
    DataFrame, one row per warehouse:
        warehouse, demand, allocated, expected_unmet,
        storage_cost, stockout_cost, total_cost
    """
    warehouses = list(demand_per_warehouse.keys())
    if not warehouses or total_supply <= 0:
        return pd.DataFrame()

    prob = pulp.LpProblem(f"alloc_{nm_id}", pulp.LpMinimize)

    # Decision variables
    x = pulp.LpVariable.dicts("x", warehouses, lowBound=0)        # units sent to w
    unmet = pulp.LpVariable.dicts("u", warehouses, lowBound=0)    # unmet demand at w

    # Coefficients
    margin = stockout_cost_per_unit(nm_id)
    storage_coef = {
        w: storage_cost_per_unit_per_day(nm_id, w) * acceptance_coefficient(w) * days_horizon
        for w in warehouses
    }

    # Objective
    prob += pulp.lpSum(
        storage_coef[w] * x[w] + margin * unmet[w] for w in warehouses
    )

    # Constraints
    prob += pulp.lpSum(x[w] for w in warehouses) <= total_supply, "supply"
    for w in warehouses:
        prob += unmet[w] >= demand_per_warehouse[w] - x[w], f"unmet_{w}"

    # Solve silently
    solver = pulp.PULP_CBC_CMD(msg=1 if verbose else 0)
    prob.solve(solver)

    rows = []
    for w in warehouses:
        allocated = float(x[w].value() or 0)
        u = float(unmet[w].value() or 0)
        rows.append({
            "nm_id": nm_id,
            "warehouse": w,
            "demand": float(demand_per_warehouse[w]),
            "allocated": round(allocated, 1),
            "expected_unmet": round(u, 1),
            "storage_cost": round(storage_coef[w] * allocated, 1),
            "stockout_cost": round(margin * u, 1),
            "total_cost": round(storage_coef[w] * allocated + margin * u, 1),
        })
    return pd.DataFrame(rows).sort_values("allocated", ascending=False).reset_index(drop=True)


def optimize_portfolio(
    forecast_df: pd.DataFrame,
    supply_per_sku: Dict[int, int],
    days_horizon: int = 7,
) -> pd.DataFrame:
    """
    Parameters:
    forecast_df : DataFrame with columns (nm_id, warehouse, demand)
    supply_per_sku : dict {nm_id: total_units_to_ship}
    days_horizon : int

    Returns:
    DataFrame: one row per (nm_id, warehouse) with allocation and cost breakdown.
    """
    parts = []
    for nm_id, group in forecast_df.groupby("nm_id"):
        supply = supply_per_sku.get(int(nm_id), 0)
        if supply <= 0:
            continue
        demand = dict(zip(group["warehouse"], group["demand"]))
        result = optimize_sku_allocation(int(nm_id), supply, demand, days_horizon)
        if not result.empty:
            parts.append(result)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
