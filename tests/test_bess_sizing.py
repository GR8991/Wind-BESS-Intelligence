import pandas as pd
from engines.bess_sizing import AnalysisConfig, run_all_studies

def test_returns_three_separate_studies():
    df = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=96, freq="15min"),
                       "active_power_mw": [20 + 10*((i % 24)/23) for i in range(96)],
                       "wind_speed_mps": [7.0]*96})
    results = run_all_studies(df, AnalysisConfig(rated_wind_mw=40, firm_target_mw=25))
    assert set(results) == {"ramp_rate_control", "energy_shifting", "firm_power_delivery"}
    for r in results.values():
        assert r["required_power_mw"] >= 0
        assert r["required_usable_energy_mwh"] >= 0
        assert len(r["timeseries"]) == len(df)
