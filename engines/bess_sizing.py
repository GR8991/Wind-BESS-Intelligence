from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from engines.data_validation import detect_interval_minutes

@dataclass
class AnalysisConfig:
    rated_wind_mw: float = 100.0
    poi_limit_mw: float | None = None
    ramp_limit_mw_per_min: float = 2.0
    smoothing_minutes: float = 60.0
    firm_target_mw: float = 40.0
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    min_soc: float = 0.10
    max_soc: float = 0.90
    initial_soc: float = 0.50

def _time_step_hours(data):
    return detect_interval_minutes(data) / 60.0

def _target_for_mode(data: pd.DataFrame, cfg: AnalysisConfig, mode: str) -> pd.Series:
    p = data["active_power_mw"].astype(float).clip(lower=0)
    dt_min = detect_interval_minutes(data)
    if mode == "ramp":
        samples = max(1, int(round(cfg.smoothing_minutes / dt_min)))
        target = p.rolling(samples, min_periods=1, center=True).mean()
        if cfg.poi_limit_mw is not None:
            target = target.clip(upper=cfg.poi_limit_mw)
        return target
    if mode == "shifting":
        # Initial screening target: constant mean non-negative wind power.
        # This is a diagnostic target, not an economic dispatch optimum.
        return pd.Series(float(p.mean()), index=data.index)
    if mode == "firm":
        return pd.Series(float(cfg.firm_target_mw), index=data.index)
    raise ValueError(f"Unknown mode: {mode}")

def _dispatch(data: pd.DataFrame, target: pd.Series, cfg: AnalysisConfig) -> dict:
    dt_h = _time_step_hours(data)
    wind = data["active_power_mw"].astype(float).clip(lower=0).to_numpy()
    target_np = target.astype(float).to_numpy()
    # Positive battery power = discharge; negative = charge.
    p_bess = target_np - wind
    # Limit charge to available wind and optional POI cap is applied to target construction.
    p_bess = np.where(p_bess < 0, np.maximum(p_bess, -wind), p_bess)
    # Preliminary sizing is based on observed required power.
    required_power = float(np.max(np.abs(p_bess))) if len(p_bess) else 0.0
    # Energy state is calculated from cumulative energy exchange, then translated to a required
    # usable capacity via the full cumulative excursion. This first-pass calculation is transparent
    # and intentionally does not silently clip SOC to imply feasibility.
    delta_stored = np.where(
        p_bess >= 0,
        -(p_bess * dt_h) / max(cfg.discharge_efficiency, 1e-9),
        (-p_bess * dt_h) * cfg.charge_efficiency,
    )
    cumulative = np.cumsum(delta_stored)
    required_usable = float(max(0.0, cumulative.max() - cumulative.min())) if len(cumulative) else 0.0
    usable_fraction = max(cfg.max_soc - cfg.min_soc, 1e-9)
    nominal_energy = required_usable / usable_fraction if required_usable > 0 else 0.0

    # Re-simulate with an energy capacity based on the required excursion. Initial state is
    # placed at the low-energy end of the cumulative trajectory to avoid artificial clipping.
    if len(cumulative):
        offset = -float(cumulative.min())
        stored = offset + cumulative
        stored = np.insert(stored, 0, offset)[:-1] if len(stored) else np.array([])
    else:
        stored = np.array([])
    soc_pct = np.clip(stored / max(required_usable, 1e-9), 0, 1) * 100 if len(stored) else np.array([])
    timeseries = data[["timestamp", "active_power_mw"]].copy()
    timeseries["target_power_mw"] = target_np
    timeseries["bess_power_mw"] = p_bess
    timeseries["soc_energy_mwh"] = stored
    timeseries["soc_percent"] = soc_pct
    timeseries["interval_hours"] = dt_h
    unmet = target_np - (wind + p_bess)
    discharge_energy = float(np.maximum(p_bess, 0).sum() * dt_h)
    charge_energy = float(np.maximum(-p_bess, 0).sum() * dt_h)
    period_days = max(len(data) * dt_h / 24.0, 1e-9)
    efc_per_day = (discharge_energy / period_days) / max(required_usable, 1e-9) if required_usable > 0 else 0.0
    target_error = (wind + p_bess) - target_np
    metrics = pd.DataFrame([
        {"metric": "Data interval (minutes)", "value": detect_interval_minutes(data)},
        {"metric": "Required PCS power estimate (MW)", "value": required_power},
        {"metric": "Required usable energy excursion (MWh)", "value": required_usable},
        {"metric": "Estimated nominal energy (MWh)", "value": nominal_energy},
        {"metric": "Wind energy (MWh; positive power only)", "value": float(wind.sum() * dt_h)},
        {"metric": "Battery charge energy (MWh; AC-side)", "value": charge_energy},
        {"metric": "Battery discharge energy (MWh; AC-side)", "value": discharge_energy},
        {"metric": "Mean absolute target error (MW)", "value": float(np.mean(np.abs(target_error))) if len(target_error) else 0.0},
        {"metric": "Maximum absolute target error (MW)", "value": float(np.max(np.abs(target_error))) if len(target_error) else 0.0},
        {"metric": "Equivalent full cycles per data-day (discharge basis)", "value": efc_per_day},
    ])
    return {
        "required_power_mw": required_power,
        "required_usable_energy_mwh": required_usable,
        "estimated_nominal_energy_mwh": nominal_energy,
        "soc_energy_mwh": pd.Series(stored),
        "efc_per_day": efc_per_day,
        "timeseries": timeseries,
        "metrics": metrics,
        "interpretation": "Screening estimate only. Review target error and SOC/energy feasibility. This baseline dispatch is not an optimizer and does not yet enforce a PCS rating or a closed daily SOC cycle.",
    }

def run_all_studies(data: pd.DataFrame, cfg: AnalysisConfig) -> dict:
    modes = {
        "ramp_rate_control": ("Ramp-rate control / smoothing", "ramp"),
        "energy_shifting": ("Wind energy shifting / surplus capture", "shifting"),
        "firm_power_delivery": ("Firm power delivery", "firm"),
    }
    results = {}
    for key, (title, mode) in modes.items():
        target = _target_for_mode(data, cfg, mode)
        result = _dispatch(data, target, cfg)
        result["title"] = title
        result["mode"] = mode
        results[key] = result
    return results
