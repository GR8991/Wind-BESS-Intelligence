import pandas as pd
from engines.bess_sizing import AnalysisConfig, run_all_studies

def test_flat_wind_matches_flat_firm_target_without_battery():
    df = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=24, freq="h"),
                       "active_power_mw": [30.0]*24,
                       "wind_speed_mps": [8.0]*24})
    r = run_all_studies(df, AnalysisConfig(rated_wind_mw=30, firm_target_mw=30))["firm_power_delivery"]
    assert r["required_power_mw"] == 0
    assert r["required_usable_energy_mwh"] == 0
