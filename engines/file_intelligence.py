from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import re
import numpy as np
import pandas as pd


@dataclass
class ColumnCandidate:
    column: str
    role: str
    confidence: float
    reason: str


@dataclass
class DatasetInterpretation:
    safe_to_analyze: bool
    selected_sheet: str | None
    timestamp_column: str | None
    active_power_column: str | None
    wind_speed_column: str | None
    available_power_column: str | None
    grid_export_column: str | None
    curtailment_column: str | None
    power_unit: str | None
    wind_speed_unit: str | None
    timestamp_timezone_assumption: str
    detected_interval_minutes: float | None
    confidence: dict[str, float]
    warnings: list[str]
    errors: list[str]
    notes: list[str]
    mapping_log: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _header_score(header: str, role: str) -> tuple[float, str]:
    h = _norm(header)
    tokens = set(h.split())
    if role == "timestamp":
        if tokens & {"timestamp", "datetime", "date", "time", "timeutc", "utc"} or "date time" in h or "time stamp" in h:
            if tokens & {"power", "speed", "price"}:
                return 0.0, "Header includes time-like and non-time measurement terms"
            return 0.92, "Header contains date/time terminology"
    elif role == "active_power":
        strong = ["active power", "activepower", "power mw", "power kw", "wind farm output", "wind power", "generation mw", "p actual", "p actual mw", "real power"]
        if any(x in h for x in strong):
            return 0.96, "Header explicitly indicates active/wind power"
        if "power" in tokens or "generation" in tokens or "output" in tokens:
            return 0.73, "Header suggests power or generation; unit/semantics need checking"
        if "mw" in tokens or "kw" in tokens:
            return 0.48, "Header contains a power unit but role is unclear"
    elif role == "wind_speed":
        if ("wind" in tokens and ("speed" in tokens or "velocity" in tokens)) or "windspeed" in h or "windvelocity" in h:
            return 0.96, "Header explicitly indicates wind speed"
        if "speed" in tokens and not (tokens & {"rotor", "tip", "vehicle"}):
            return 0.55, "Header suggests speed but does not establish that it is wind speed"
    elif role == "available_power":
        if ("available" in tokens and ("power" in tokens or "generation" in tokens)) or "potential generation" in h:
            return 0.94, "Header indicates available/potential generation"
    elif role == "grid_export":
        if ("poi" in tokens or "export" in tokens or "injection" in tokens) and (tokens & {"mw", "power", "grid", "poi", "export", "injection"}):
            return 0.9, "Header indicates grid/POI export"
    elif role == "curtailment":
        if "curtail" in tokens or "curtailment" in tokens:
            return 0.94, "Header indicates curtailment"
    return 0.0, "No strong header evidence"


def _choose_column(df: pd.DataFrame, role: str) -> tuple[str | None, float, str]:
    scored = []
    for col in df.columns:
        score, reason = _header_score(str(col), role)
        if score:
            scored.append((score, str(col), reason))
    scored.sort(reverse=True)
    if not scored:
        return None, 0.0, "No candidate header found"
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.08:
        return None, scored[0][0], f"Ambiguous candidates: {scored[0][1]} and {scored[1][1]}"
    return scored[0][1], scored[0][0], scored[0][2]


def _guess_power_unit(column: str, series: pd.Series, rated_capacity_mw: float | None) -> tuple[str | None, float, str]:
    h = _norm(column)
    if re.search(r"\bkw\b", h) or "kilowatt" in h:
        return "kW", 0.99, "Unit explicitly indicated in column header"
    if re.search(r"\bmw\b", h) or "megawatt" in h:
        return "MW", 0.99, "Unit explicitly indicated in column header"
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return None, 0.0, "No numeric values to infer unit"
    # Magnitude alone cannot distinguish MW from kW reliably. Require explicit unit evidence.
    return None, 0.0, "Power unit is not explicit; refusing to guess from magnitude alone"


def _guess_speed_unit(column: str) -> tuple[str | None, float, str]:
    h = _norm(column)
    if any(x in h for x in ["m s", "mps", "m/s", "meter per second", "metre per second"]):
        return "m/s", 0.99, "Unit explicitly indicated in column header"
    if "km h" in h or "kmh" in h or "km/h" in h:
        return "km/h", 0.99, "Unit explicitly indicated in column header"
    if "knot" in h or re.search(r"\bkt\b", h):
        return "knots", 0.99, "Unit explicitly indicated in column header"
    return None, 0.0, "Wind-speed unit is not explicit; no silent conversion will be applied"


def _infer_interval(ts: pd.Series) -> tuple[float | None, list[str]]:
    warnings = []
    parsed = pd.to_datetime(ts, errors="coerce", utc=True).dropna().sort_values()
    diffs = parsed.diff().dropna().dt.total_seconds().div(60)
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return None, ["Unable to infer sampling interval from timestamps."]
    med = float(diffs.median())
    if not np.isfinite(med) or med <= 0:
        return None, ["Unable to infer a positive sampling interval."]
    if ((diffs - med).abs() > max(0.05 * med, 1e-6)).any():
        warnings.append("Irregular timestamps or missing intervals detected; interval is the median positive difference.")
    return med, warnings


def inspect_tables(tables: dict[str, pd.DataFrame], rated_capacity_mw: float | None = None) -> tuple[str | None, DatasetInterpretation | None]:
    """Inspect tables and choose a likely data sheet without silently resolving unsafe ambiguity."""
    if not tables:
        return None, None
    scored_tables = []
    for name, df in tables.items():
        if df.empty:
            continue
        ts, ts_conf, _ = _choose_column(df, "timestamp")
        power, p_conf, _ = _choose_column(df, "active_power")
        speed, s_conf, _ = _choose_column(df, "wind_speed")
        scored_tables.append((ts_conf + p_conf + 0.35*s_conf, name, df, ts, ts_conf, power, p_conf, speed, s_conf))
    if not scored_tables:
        return None, None
    scored_tables.sort(reverse=True, key=lambda x: x[0])
    best = scored_tables[0]
    if len(scored_tables) > 1 and abs(scored_tables[0][0] - scored_tables[1][0]) < 0.05:
        # Keep deterministic choice but flag ambiguous table in interpretation.
        ambiguous_sheet = True
    else:
        ambiguous_sheet = False
    _, sheet, df, ts_col, ts_conf, power_col, p_conf, speed_col, s_conf = best
    warnings, errors, notes, log = [], [], [], []
    if ambiguous_sheet:
        warnings.append("Multiple workbook sheets look similarly plausible; selected the highest-scoring sheet. Review the interpretation log.")
    if ts_col is None:
        errors.append("Could not confidently identify a timestamp column.")
    if power_col is None:
        errors.append("Could not confidently identify an active-power column.")
    power_unit, power_unit_conf, power_unit_reason = (None, 0.0, "No active-power column")
    if power_col:
        power_unit, power_unit_conf, power_unit_reason = _guess_power_unit(power_col, df[power_col], rated_capacity_mw)
        if power_unit is None:
            errors.append("Active-power unit is ambiguous. Include MW or kW in the header or provide explicit unit metadata.")
    speed_unit, speed_unit_conf, speed_unit_reason = (None, 0.0, "No wind-speed column")
    if speed_col:
        speed_unit, speed_unit_conf, speed_unit_reason = _guess_speed_unit(speed_col)
        if speed_unit is None:
            warnings.append("Wind-speed column detected, but its unit is not explicit. Wind speed will be preserved as unnormalized and excluded from unit-dependent analysis.")
    interval = None
    if ts_col:
        interval, interval_warnings = _infer_interval(df[ts_col])
        warnings.extend(interval_warnings)
    roles = [
        ("timestamp", ts_col, ts_conf, "Timestamp candidate"),
        ("active_power_mw", power_col, p_conf, power_unit_reason),
        ("wind_speed_mps", speed_col, s_conf, speed_unit_reason),
    ]
    for role, col, conf, reason in roles:
        log.append({"role": role, "source_column": col, "confidence": round(float(conf), 3), "reason": reason})
    for role in ("available_power", "grid_export", "curtailment"):
        col, conf, reason = _choose_column(df, role)
        log.append({"role": role, "source_column": col, "confidence": round(float(conf), 3), "reason": reason})
    if ts_col and power_col and power_unit:
        notes.append(f"Selected worksheet/table '{sheet}' with timestamp '{ts_col}' and active power '{power_col}' ({power_unit}).")
    safe = not errors
    interpretation = DatasetInterpretation(
        safe_to_analyze=safe,
        selected_sheet=sheet,
        timestamp_column=ts_col,
        active_power_column=power_col,
        wind_speed_column=speed_col,
        available_power_column=_choose_column(df, "available_power")[0],
        grid_export_column=_choose_column(df, "grid_export")[0],
        curtailment_column=_choose_column(df, "curtailment")[0],
        power_unit=power_unit,
        wind_speed_unit=speed_unit,
        timestamp_timezone_assumption="Timezone-aware values converted to UTC; timezone-naive values assumed UTC and flagged in the report.",
        detected_interval_minutes=interval,
        confidence={"timestamp": ts_conf, "active_power": p_conf, "wind_speed": s_conf, "power_unit": power_unit_conf, "wind_speed_unit": speed_unit_conf},
        warnings=warnings,
        errors=errors,
        notes=notes,
        mapping_log=log,
    )
    return sheet, interpretation


def read_uploaded_tables(uploaded_file) -> dict[str, pd.DataFrame]:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return {"CSV": pd.read_csv(uploaded_file)}
    if name.endswith((".xlsx", ".xls")):
        # Read all sheets; the inspection step selects the most likely data table.
        return pd.read_excel(uploaded_file, sheet_name=None)
    raise ValueError("Unsupported file type. Upload CSV or Excel.")
