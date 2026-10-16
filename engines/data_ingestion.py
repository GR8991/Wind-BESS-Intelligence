from __future__ import annotations
import pandas as pd

def load_uploaded_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    raise ValueError("Unsupported file type. Upload CSV or Excel.")

def normalize_wind_data(raw: pd.DataFrame, timestamp_col: str, power_col: str, speed_col: str | None = None) -> pd.DataFrame:
    if timestamp_col == power_col:
        raise ValueError("Timestamp and active-power columns must differ.")
    out = pd.DataFrame()
    out["timestamp"] = pd.to_datetime(raw[timestamp_col], errors="coerce", utc=True)
    out["active_power_mw"] = pd.to_numeric(raw[power_col], errors="coerce")
    if speed_col and speed_col in raw.columns:
        out["wind_speed_mps"] = pd.to_numeric(raw[speed_col], errors="coerce")
    else:
        out["wind_speed_mps"] = float("nan")
    out = out.dropna(subset=["timestamp", "active_power_mw"]).sort_values("timestamp")
    out = out.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    return out
