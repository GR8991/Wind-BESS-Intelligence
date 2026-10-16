from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from engines.file_intelligence import read_uploaded_tables, inspect_tables
from engines.time_series_normalizer import normalize_wind_dataset
from engines.data_validation import validate_wind_data
from engines.wind_signature import summarize_wind, calculate_ramps
from engines.bess_sizing import AnalysisConfig, run_all_studies
from reports.excel_export import build_excel_report

st.set_page_config(page_title="Wind-BESS Sizing Intelligence V1.1", layout="wide")
st.title("Wind-BESS Independent Sizing Intelligence")
st.caption("V1.1 · Autonomous dataset interpretation · Engineering decision support, not a final bankable design")

with st.sidebar:
    st.header("Project constraints")
    rated_wind_mw = st.number_input("Wind farm rated capacity (MW)", min_value=0.1, value=100.0, step=1.0)
    poi_limit_mw = st.number_input("POI/export limit (MW; optional)", min_value=0.0, value=100.0, step=1.0)
    ramp_limit_mw_per_min = st.number_input("Ramp limit (MW/min)", min_value=0.01, value=2.0, step=0.1)
    smoothing_minutes = st.number_input("Smoothing window (minutes)", min_value=5, value=60, step=5)
    target_firm_mw = st.number_input("Firm delivery target (MW)", min_value=0.0, value=40.0, step=1.0)
    charge_efficiency = st.slider("Charge efficiency", 0.50, 1.00, 0.95, 0.01)
    discharge_efficiency = st.slider("Discharge efficiency", 0.50, 1.00, 0.95, 0.01)
    min_soc = st.slider("Minimum SOC (%)", 0, 50, 10, 1) / 100
    max_soc = st.slider("Maximum SOC (%)", 50, 100, 90, 1) / 100
    initial_soc = st.slider("Initial SOC (%)", 0, 100, 50, 1) / 100
    st.caption("These are project-level assumptions. The upload parser does not infer the project's rated capacity or POI limit from generation values alone.")

uploaded = st.file_uploader("Upload wind dataset (CSV or Excel; all worksheets inspected)", type=["csv", "xlsx", "xls"])

if uploaded:
    try:
        tables = read_uploaded_tables(uploaded)
        selected_sheet, interpretation = inspect_tables(tables, rated_capacity_mw=float(rated_wind_mw))

        st.subheader("Automatic dataset interpretation")
        if interpretation is None:
            st.error("No non-empty table could be interpreted.")
            st.stop()

        # Show interpretation, confidence and source mapping for auditability.
        a, b, c = st.columns(3)
        a.metric("Selected table", interpretation.selected_sheet or "Unknown")
        b.metric("Detected interval", f"{interpretation.detected_interval_minutes:g} min" if interpretation.detected_interval_minutes else "Unknown")
        c.metric("Interpretation status", "Ready for normalization" if interpretation.safe_to_analyze else "Blocked")

        mapping_df = pd.DataFrame(interpretation.mapping_log)
        st.dataframe(mapping_df, use_container_width=True, hide_index=True)

        for note in interpretation.notes:
            st.success(note)
        for warning in interpretation.warnings:
            st.warning(warning)
        for error in interpretation.errors:
            st.error(error)

        if not interpretation.safe_to_analyze:
            st.error("Sizing is blocked because one or more essential fields or units could not be interpreted safely. Update the source headers to include explicit units (for example, Active Power (MW), Wind Speed (m/s)) and upload again.")
            st.stop()

        raw_selected = tables[selected_sheet]
        normalized = normalize_wind_dataset(raw_selected, interpretation)
        checks = validate_wind_data(normalized, float(rated_wind_mw), interpretation.detected_interval_minutes)

        st.subheader("Normalized engineering data preview")
        st.caption("Internal timestamp standard: UTC. Naive source timestamps are assumed UTC; confirm this assumption when the source represents local time.")
        st.dataframe(normalized.head(10), use_container_width=True, hide_index=True)

        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Valid records", f"{len(normalized):,}")
        q2.metric("Data interval", f"{checks['interval_minutes']:g} min" if pd.notna(checks["interval_minutes"]) else "Unknown")
        q3.metric("Maximum active power", f"{normalized['active_power_mw'].max():,.3f} MW" if len(normalized) else "N/A")
        q4.metric("Wind speed available", "Yes" if normalized["wind_speed_mps"].notna().any() else "No")

        for warning in checks["warnings"]:
            st.warning(warning)
        for error in checks["errors"]:
            st.error(error)
        for note in checks["notes"]:
            st.success(note)

        # Download normalized data and interpretation audit even if sizing is blocked.
        normalized_csv = normalized.copy()
        normalized_csv["timestamp"] = normalized_csv["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        st.download_button(
            "Download normalized data (CSV)",
            normalized_csv.to_csv(index=False).encode("utf-8"),
            file_name="normalized_wind_data.csv",
            mime="text/csv",
        )
        interpretation_json = interpretation.to_dict()
        st.download_button(
            "Download interpretation log (JSON)",
            pd.Series(interpretation_json).to_json(indent=2).encode("utf-8"),
            file_name="dataset_interpretation_log.json",
            mime="application/json",
        )

        if not checks["safe_to_size"]:
            st.error("BESS sizing is blocked. Correct the data-quality errors before running any study.")
            st.stop()

        st.subheader("Wind signature")
        summary = summarize_wind(normalized, float(rated_wind_mw))
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Wind energy (MWh)", f"{summary['energy_mwh']:,.1f}")
        k2.metric("Mean power (MW)", f"{summary['mean_power_mw']:,.2f}")
        k3.metric("Capacity factor", f"{summary['capacity_factor']:.1%}")
        k4.metric("Max power (MW)", f"{summary['max_power_mw']:,.2f}")
        st.plotly_chart(px.line(normalized, x="timestamp", y="active_power_mw", title="Measured wind active power (MW)"), use_container_width=True)
        ramps = calculate_ramps(normalized)
        if not ramps.empty:
            st.plotly_chart(px.histogram(ramps, x="ramp_mw_per_min", title="Ramp-rate distribution (MW/min)"), use_container_width=True)

        if st.button("Run independent BESS studies", type="primary"):
            if min_soc >= max_soc:
                st.error("Minimum SOC must be below maximum SOC.")
                st.stop()
            cfg = AnalysisConfig(
                rated_wind_mw=float(rated_wind_mw),
                poi_limit_mw=float(poi_limit_mw) if poi_limit_mw > 0 else None,
                ramp_limit_mw_per_min=float(ramp_limit_mw_per_min),
                smoothing_minutes=float(smoothing_minutes),
                firm_target_mw=float(target_firm_mw),
                charge_efficiency=float(charge_efficiency),
                discharge_efficiency=float(discharge_efficiency),
                min_soc=float(min_soc),
                max_soc=float(max_soc),
                initial_soc=float(initial_soc),
            )
            studies = run_all_studies(normalized, cfg)
            for name, result in studies.items():
                st.header(result["title"])
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Estimated PCS power (MW)", f"{result['required_power_mw']:.2f}")
                m2.metric("Estimated usable energy (MWh)", f"{result['required_usable_energy_mwh']:.2f}")
                m3.metric("Maximum simulated SOC (MWh)", f"{result['soc_energy_mwh'].max():.2f}")
                m4.metric("Discharge EFC / data day", f"{result['efc_per_day']:.3f}")
                st.warning(result["interpretation"])
                chart = result["timeseries"]
                st.plotly_chart(px.line(chart, x="timestamp", y=["active_power_mw", "target_power_mw", "bess_power_mw"], title=f"{name}: wind, target and battery power"), use_container_width=True)
                st.plotly_chart(px.line(chart, x="timestamp", y="soc_percent", title=f"{name}: preliminary SOC trajectory"), use_container_width=True)
                st.dataframe(result["metrics"], use_container_width=True)
            output = build_excel_report(studies, normalized, checks)
            st.download_button("Download engineering Excel report", output, file_name="wind_bess_sizing_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as exc:
        st.error("The file could not be interpreted safely. No sizing results should be used until this issue is resolved.")
        st.exception(exc)
else:
    st.markdown("### Autonomous workflow")
    st.markdown("Upload a CSV/XLSX file. The application inspects all sheets, infers likely columns and units from explicit evidence, normalizes supported data, validates quality, and blocks unsafe sizing runs. It does not silently guess ambiguous power units.")
