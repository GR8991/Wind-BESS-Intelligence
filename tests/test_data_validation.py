import pandas as pd
from engines.data_validation import detect_interval_minutes, validate_wind_data

def test_detects_15_minute_interval():
    df = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=8, freq="15min"),
                       "active_power_mw": [1,2,3,4,5,6,7,8],
                       "wind_speed_mps": [5]*8})
    assert detect_interval_minutes(df) == 15.0
    assert not validate_wind_data(df, 10)["errors"]
