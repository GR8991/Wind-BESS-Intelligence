from __future__ import annotations
import io
import pandas as pd

def build_excel_report(studies: dict, source_data: pd.DataFrame, validation: dict) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        source_data.to_excel(writer, sheet_name="Input Data", index=False)
        pd.DataFrame([{"type": "error", "message": x} for x in validation["errors"]] +
                     [{"type": "warning", "message": x} for x in validation["warnings"]] +
                     [{"type": "note", "message": x} for x in validation["notes"]]).to_excel(writer, sheet_name="Data QA", index=False)
        for name, result in studies.items():
            safe = name[:25]
            result["metrics"].to_excel(writer, sheet_name=f"{safe}_Metrics", index=False)
            result["timeseries"].to_excel(writer, sheet_name=f"{safe}_Dispatch", index=False)
    return buffer.getvalue()
