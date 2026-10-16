from __future__ import annotations
import numpy as np
import pandas as pd


def normalize_wind_dataset(
    raw: pd.DataFrame,
    interpretation,
) -> pd.DataFrame:
    """Normalize detected fields to canonical engineering names; preserve UTC semantics."""
    if not interpretation.safe_to_analyze:
        raise ValueError("Dataset interpretation is not safe to analyze.")
    out = pd.DataFrame()
    ts_col = interpretation.timestamp_column
    power_col = interpretation.active_power_column
    if not ts_col or not power_col:
        raise ValueError("Timestamp and active-power columns are required.")

    ts_raw = raw[ts_col]
    # Naive timestamps are assumed UTC for this prototype; report this assumption.
    out["timestamp"] = pd.to_datetime(ts_raw, errors="coerce", utc=True)

    power = pd.to_numeric(raw[power_col], errors="coerce")
    if interpretation.power_unit == "kW":
        power = power / 1000.0
    elif interpretation.power_unit != "MW":
        raise ValueError("Unsupported or ambiguous active-power unit.")
    out["active_power_mw"] = power

    speed_col = interpretation.wind_speed_column
    if speed_col:
        speed = pd.to_numeric(raw[speed_col], errors="coerce")
        unit = interpretation.wind_speed_unit
        if unit == "km/h":
            speed = speed / 3.6
        elif unit == "knots":
            speed = speed * 0.514444
        elif unit == "m/s":
            pass
        else:
            speed = np.nan
        out["wind_speed_mps"] = speed
    else:
        out["wind_speed_mps"] = np.nan

    optional_fields = [
        ("available_power_column", "available_wind_mw"),
        ("grid_export_column", "grid_export_mw"),
        ("curtailment_column", "curtailment_mw"),
    ]
    for attr, canonical in optional_fields:
        col = getattr(interpretation, attr, None)
        if col and col in raw.columns:
            vals = pd.to_numeric(raw[col], errors="coerce")
            h = str(col).lower()
            if "kw" in h and "mw" not in h:
                vals = vals / 1000.0
            out[canonical] = vals

    out["source_row_number"] = np.arange(len(raw)) + 2
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp")
    # Do not silently aggregate duplicates: retain one row per timestamp only after reporting is added.
    out = out.reset_index(drop=True)
    return out
