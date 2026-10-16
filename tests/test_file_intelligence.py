import pandas as pd
from engines.file_intelligence import inspect_tables
from engines.time_series_normalizer import normalize_wind_dataset
from engines.data_validation import validate_wind_data


def test_detects_explicit_mw_and_wind_speed():
    df = pd.DataFrame({
        "Timestamp UTC": pd.date_range("2025-01-01", periods=12, freq="15min"),
        "Active Power (MW)": [10.0 + i for i in range(12)],
        "Wind Speed (m/s)": [6.0 + i * 0.1 for i in range(12)],
    })
    sheet, interp = inspect_tables({"Data": df}, rated_capacity_mw=100)
    assert sheet == "Data"
    assert interp.safe_to_analyze
    assert interp.power_unit == "MW"
    normalized = normalize_wind_dataset(df, interp)
    checks = validate_wind_data(normalized, 100, interp.detected_interval_minutes)
    assert checks["safe_to_size"]
    assert normalized["wind_speed_mps"].notna().all()


def test_blocks_ambiguous_power_unit():
    df = pd.DataFrame({
        "DateTime": pd.date_range("2025-01-01", periods=12, freq="h"),
        "Generation": [100.0] * 12,
    })
    _, interp = inspect_tables({"Data": df}, rated_capacity_mw=100)
    assert not interp.safe_to_analyze
    assert any("unit" in error.lower() for error in interp.errors)


def test_converts_kw_to_mw():
    df = pd.DataFrame({
        "Timestamp": pd.date_range("2025-01-01", periods=12, freq="h"),
        "Wind Farm Output (kW)": [25000.0] * 12,
        "Wind Speed (m/s)": [8.0] * 12,
    })
    _, interp = inspect_tables({"Data": df}, rated_capacity_mw=100)
    assert interp.safe_to_analyze
    normalized = normalize_wind_dataset(df, interp)
    assert abs(normalized["active_power_mw"].iloc[0] - 25.0) < 1e-9


def test_rating_gate_blocks_implausible_power():
    df = pd.DataFrame({
        "Timestamp": pd.date_range("2025-01-01", periods=12, freq="h"),
        "Active Power (MW)": [1.89e12] * 12,
        "Wind Speed (m/s)": [8.0] * 12,
    })
    _, interp = inspect_tables({"Data": df}, rated_capacity_mw=100)
    normalized = normalize_wind_dataset(df, interp)
    checks = validate_wind_data(normalized, 100, interp.detected_interval_minutes)
    assert not checks["safe_to_size"]
    assert any("exceeds" in error.lower() for error in checks["errors"])
