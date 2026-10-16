
from __future__ import annotations

import io
import pandas as pd


def _excel_safe_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with timezone-aware datetimes converted to naive UTC."""
    out = df.copy()

    for col in out.columns:
        # Standard timezone-aware pandas datetime columns
        if isinstance(out[col].dtype, pd.DatetimeTZDtype):
            out[col] = out[col].dt.tz_convert("UTC").dt.tz_localize(None)

        # Handle object columns containing timezone-aware datetime values
        elif out[col].dtype == "object":
            has_aware_datetime = out[col].map(
                lambda value: isinstance(value, (pd.Timestamp,))
                and value.tzinfo is not None
                and value.utcoffset() is not None
            ).any()

            if has_aware_datetime:
                out[col] = out[col].map(
                    lambda value: (
                        value.tz_convert("UTC").tz_localize(None)
                        if isinstance(value, pd.Timestamp)
                        and value.tzinfo is not None
                        and value.utcoffset() is not None
                        else value
                    )
                )

    return out


def build_excel_report(
    studies: dict,
    source_data: pd.DataFrame,
    validation: dict,
) -> bytes:
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Input data: timestamps are exported as timezone-naive UTC.
        _excel_safe_dataframe(source_data).to_excel(
            writer,
            sheet_name="Input Data",
            index=False,
        )

        validation_rows = (
            [{"type": "error", "message": x} for x in validation["errors"]]
            + [{"type": "warning", "message": x} for x in validation["warnings"]]
            + [{"type": "note", "message": x} for x in validation["notes"]]
        )

        pd.DataFrame(
            validation_rows,
            columns=["type", "message"],
        ).to_excel(
            writer,
            sheet_name="Data QA",
            index=False,
        )

        for name, result in studies.items():
            safe_name = name[:25]

            _excel_safe_dataframe(result["metrics"]).to_excel(
                writer,
                sheet_name=f"{safe_name}_Metrics",
                index=False,
            )

            _excel_safe_dataframe(result["timeseries"]).to_excel(
                writer,
                sheet_name=f"{safe_name}_Dispatch",
                index=False,
            )

    buffer.seek(0)
    return buffer.getvalue()
