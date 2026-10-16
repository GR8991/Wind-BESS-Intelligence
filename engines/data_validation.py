from __future__ import annotations
import numpy as np
import pandas as pd


def detect_interval_minutes(data: pd.DataFrame) -> float:
    ts = pd.to_datetime(data["timestamp"], errors="coerce", utc=True).dropna().sort_values()
    diffs = ts.diff().dropna().dt.total_seconds().div(60)
    diffs = diffs[diffs > 0]
    return float(diffs.median()) if not diffs.empty else float("nan")


def validate_wind_data(data: pd.DataFrame, rated_wind_mw: float, interval_minutes: float | None = None) -> dict:
    errors, warnings, notes = [], [], []
    if data.empty:
        errors.append("No valid rows remain after timestamp parsing.")
        return {"errors": errors, "warnings": warnings, "notes": notes, "interval_minutes": float("nan"), "safe_to_size": False}
    if "timestamp" not in data or "active_power_mw" not in data:
        errors.append("Normalized dataset must include timestamp and active_power_mw.")
        return {"errors": errors, "warnings": warnings, "notes": notes, "interval_minutes": float("nan"), "safe_to_size": False}
    if data["timestamp"].duplicated().any():
        errors.append("Duplicate timestamps detected. Resolve duplicates before sizing; they are not silently removed.")
    if not data["timestamp"].is_monotonic_increasing:
        errors.append("Timestamps are not in ascending order.")
    if data["active_power_mw"].isna().any():
        errors.append("Active power contains missing or non-numeric values.")
    if (data["active_power_mw"] < -1e-6).any():
        warnings.append("Negative active power exists. Confirm whether values represent net export or auxiliary consumption.")
    if rated_wind_mw <= 0:
        errors.append("Rated wind capacity must be greater than zero.")
    if rated_wind_mw > 0 and (data["active_power_mw"] > rated_wind_mw * 1.05).any():
        errors.append("Active power exceeds 105% of stated wind-farm rating. Check column mapping, units, and rating; sizing has been blocked.")
    interval = interval_minutes if interval_minutes and interval_minutes > 0 else detect_interval_minutes(data)
    if not np.isfinite(interval) or interval <= 0:
        errors.append("Unable to infer a positive sampling interval.")
    else:
        ts = pd.to_datetime(data["timestamp"], utc=True)
        diffs = ts.diff().dropna().dt.total_seconds().div(60)
        irregular = (diffs - interval).abs() > max(interval * 0.05, 1e-6)
        if irregular.any():
            warnings.append(f"Irregular intervals detected: {int(irregular.sum())} differences depart from median interval {interval:g} minutes. No interpolation has been applied.")
        else:
            notes.append(f"Regular sampling detected at approximately {interval:g} minutes.")
    if "wind_speed_mps" in data and data["wind_speed_mps"].notna().any():
        valid_speed = data["wind_speed_mps"].dropna()
        if (valid_speed < 0).any() or (valid_speed.quantile(0.99) > 60):
            warnings.append("Wind-speed values are outside the expected screening range; confirm unit and sensor data.")
    else:
        warnings.append("No normalized wind-speed observations are available. Power-only analysis may proceed if other quality gates pass.")
    if len(data) < 8:
        warnings.append("Very few records are available; statistical characterization may be unreliable.")
    safe_to_size = len(errors) == 0
    return {
        "errors": errors,
        "warnings": warnings,
        "notes": notes,
        "interval_minutes": interval,
        "safe_to_size": safe_to_size,
        "record_count": int(len(data)),
        "start_utc": str(data["timestamp"].min()),
        "end_utc": str(data["timestamp"].max()),
    }
