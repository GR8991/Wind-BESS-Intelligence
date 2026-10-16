from __future__ import annotations
import numpy as np
import pandas as pd
from engines.data_validation import detect_interval_minutes

def summarize_wind(data: pd.DataFrame, rated_wind_mw: float) -> dict:
    interval_h = detect_interval_minutes(data) / 60.0
    power = data["active_power_mw"].astype(float)
    energy = float((power.clip(lower=0).sum()) * interval_h)
    return {
        "energy_mwh": energy,
        "mean_power_mw": float(power.mean()),
        "max_power_mw": float(power.max()),
        "min_power_mw": float(power.min()),
        "capacity_factor": float(energy / (rated_wind_mw * interval_h * len(data))) if rated_wind_mw > 0 else float("nan"),
        "wind_speed_mean_mps": float(data["wind_speed_mps"].mean()) if data["wind_speed_mps"].notna().any() else float("nan"),
        "wind_speed_p95_mps": float(data["wind_speed_mps"].quantile(0.95)) if data["wind_speed_mps"].notna().any() else float("nan"),
    }

def calculate_ramps(data: pd.DataFrame) -> pd.DataFrame:
    out = data[["timestamp", "active_power_mw"]].copy()
    dt_min = out["timestamp"].diff().dt.total_seconds().div(60)
    dp = out["active_power_mw"].diff()
    out["ramp_mw_per_min"] = dp.div(dt_min.where(dt_min > 0))
    return out.dropna(subset=["ramp_mw_per_min"])
