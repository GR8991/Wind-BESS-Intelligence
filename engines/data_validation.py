from __future__ import annotations
import numpy as np
import pandas as pd

def detect_interval_minutes(data: pd.DataFrame) -> float:
    ts = pd.to_datetime(data["timestamp"]).sort_values()
    diffs = ts.diff().dropna().dt.total_seconds().div(60)
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return float("nan")
    # Median is robust to occasional missing intervals; report irregularity separately.
    return float(diffs.median())

def validate_wind_data(data: pd.DataFrame, rated_wind_mw: float) -> dict:
    errors, warnings, notes = [], [], []
    if data.empty:
        errors.append("No valid rows remain after timestamp/power parsing.")
        return {"errors": errors, "warnings": warnings, "notes": notes, "interval_minutes": float("nan")}
    if data["timestamp"].duplicated().any():
        warnings.append("Duplicate timestamps remain; review before engineering use.")
    if not data["timestamp"].is_monotonic_increasing:
        warnings.append("Timestamps are not in ascending order.")
    if data["active_power_mw"].isna().any():
        warnings.append("Active-power data contain missing values.")
    if (data["active_power_mw"] < -1e-6).any():
        warnings.append("Negative active power exists. Confirm whether this is valid net export/auxiliary consumption.")
    if rated_wind_mw <= 0:
        errors.append("Rated wind capacity must be greater than zero.")
    if (data["active_power_mw"] > rated_wind_mw * 1.05).any():
        warnings.append("Power exceeds 105% of stated rated capacity; check units and rating.")
    interval = detect_interval_minutes(data)
    if not np.isfinite(interval):
        errors.append("Unable to infer a positive time interval.")
    else:
        diffs = data["timestamp"].diff().dropna().dt.total_seconds().div(60)
        irregular = (diffs - interval).abs() > max(interval * 0.05, 1e-6)
        if irregular.any():
            warnings.append(f"Time intervals are irregular: {int(irregular.sum())} intervals differ from the median. Missing intervals are not automatically imputed.")
        else:
            notes.append("Timestamps appear regularly spaced.")
        if interval > 60:
            warnings.append("Detected interval is longer than one hour. Ramp analysis may not capture sub-hour events.")
    if data["wind_speed_mps"].notna().sum() == 0:
        warnings.append("No usable wind-speed observations were found; wind-speed-based diagnostics will be limited.")
    else:
        if (data["wind_speed_mps"] < 0).any():
            warnings.append("Negative wind-speed values exist; review units and data quality.")
    return {"errors": errors, "warnings": warnings, "notes": notes, "interval_minutes": interval}
