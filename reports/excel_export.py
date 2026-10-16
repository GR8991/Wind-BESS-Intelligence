from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pandas as pd


def _excel_safe_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with timezone-aware datetimes made Excel-compatible.

    Timezone-aware timestamps are converted to UTC and made timezone-naive.
    Excel does not store timezone metadata, so UTC is the consistent export basis.
    The caller's original DataFrame is not modified.
    """
    safe = frame.copy()

    for column in safe.columns:
        series = safe[column]

        # Covers pandas datetime64[ns, tz] columns.
        if isinstance(series.dtype, pd.DatetimeTZDtype):
            safe[column] = series.dt.tz_convert("UTC").dt.tz_localize(None)
            continue

        # Also handle object columns containing timezone-aware Timestamp/datetime values.
        if series.dtype == "object":
            def make_excel_safe(value: Any) -> Any:
                if isinstance(value, pd.Timestamp) and value.tzinfo is not None:
                    return value.tz_convert("UTC").tz_localize(None)
                if isinstance(value, datetime) and value.tzinfo is not None:
                    return pd.Timestamp(value).tz_convert("UTC").tz_localize(None).to_pydatetime()
                return value

            safe[column] = series.map(make_excel_safe)

    return safe


def build_excel_report(studies: dict, source_data: pd.DataFrame, validation: dict) -> bytes:
    buffer = io.BytesIO()
    qa_rows = (
        [{"type": "error", "message": x} for x in validation.get("errors", [])]
        + [{"type": "warning", "message": x} for x in validation.get("warnings", [])]
        + [{"type": "note", "message": x} for x in validation.get("notes", [])]
    )
    qa_rows.append({
        "type": "note",
        "message": "Timezone-aware timestamps are exported as timezone-naive UTC values because Excel does not support timezone metadata.",
    })

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _excel_safe_dataframe(source_data).to_excel(writer, sheet_name="Input Data", index=False)
        pd.DataFrame(qa_rows).to_excel(writer, sheet_name="Data QA", index=False)
        for name, result in studies.items():
            safe_name = name[:25]
            _excel_safe_dataframe(result["metrics"]).to_excel(
                writer, sheet_name=f"{safe_name}_Metrics", index=False
            )
            _excel_safe_dataframe(result["timeseries"]).to_excel(
                writer, sheet_name=f"{safe_name}_Dispatch", index=False
            )
    return buffer.getvalue()
