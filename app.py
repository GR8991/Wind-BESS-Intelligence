from __future__ import annotations

import io
import streamlit as st
import pandas as pd
import plotly.express as px

from engines.data_ingestion import load_uploaded_file, normalize_wind_data
from engines.data_validation import validate_wind_data
from engines.wind_signature import summarize_wind, calculate_ramps
from engines.bess_sizing import AnalysisConfig, run_all_studies
from reports.excel_export import build_excel_report

st.set_page_config(page_title="Wind-BESS Sizing Intelligence V1", layout="wide")
st.title("Wind-BESS Independent Sizing Intelligence")
st.caption("Version 1 · Independent wind-data analysis · Decision support, not a final bankable design")

with st.sidebar:
    st.header("Project configuration")
    rated_wind_mw = st.number_input("Wind farm rated capacity (MW)", min_value=0.1, value=100.0, step=1.0)
    poi_limit_mw = st.number_input("POI/export limit (MW; optional constraint)", min_value=0.0, value=100.0, step=1.0)
    ramp_limit_mw_per_min = st.number_input("Ramp limit (MW/min)", min_value=0.01, value=2.0, step=0.1)
    smoothing_minutes = st.number_input("Smoothing window (minutes)", min_value=5, value=60, step=5)
    target_firm_mw = st.number_input("Firm delivery target (MW)", min_value=0.0, value=40.0, step=1.0)
    charge_efficiency = st.slider("Charge efficiency", 0.50, 1.00, 0.95, 0.01)
    discharge_efficiency = st.slider("Discharge efficiency", 0.50, 1.00, 0.95, 0.01)
    min_soc = st.slider("Minimum SOC (%)", 0, 50, 10, 1) / 100
    max_soc = st.slider("Maximum SOC (%)", 50, 100, 90, 1) / 100
    initial_soc = st.slider("Initial SOC (%)", 0, 100, 50, 1) / 100
    if min_soc >= max_soc:
        st.error("Minimum SOC must be below maximum SOC.")

uploaded = st.file_uploader("Upload wind time-series data (CSV or Excel)", type=["csv", "xlsx", "xls"])
st.info("Required: timestamp and active power (MW). Wind speed is recommended and used for wind-signature analysis.")

if uploaded:
    try:
        raw = load_uploaded_file(uploaded)
        st.subheader("Map input columns")
        cols = list(raw.columns)
        c1, c2, c3 = st.columns(3)
        timestamp_col = c1.selectbox("Timestamp column", cols, index=next((i for i,c in enumerate(cols) if "time" in str(c).lower() or "date" in str(c).lower()), 0))
        power_col = c2.selectbox("Active power column (MW)", cols, index=next((i for i,c in enumerate(cols) if "power" in str(c).lower() or str(c).lower() in ["mw","active_power"]), 0))
        speed_candidates = [None] + cols
        speed_col = c3.selectbox("Wind speed column (optional)", speed_candidates, index=next((i+1 for i,c in enumerate(cols) if "wind" in str(c).lower() and "speed" in str(c).lower()), 0))
        data = normalize_wind_data(raw, timestamp_col, power_col, speed_col)
        checks = validate_wind_data(data, rated_wind_mw)
        st.subheader("Data quality")
        st.write(f"Detected interval: **{checks['interval_minutes']:.3g} minutes** · Records: **{len(data):,}**")
        for warning in checks["warnings"]:
            st.warning(warning)
        for note in checks["notes"]:
            st.success(note)
        if not checks["errors"]:
            st.subheader("Wind signature")
            summary = summarize_wind(data, rated_wind_mw)
            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Energy (MWh)", f"{summary['energy_mwh']:,.1f}")
            k2.metric("Mean power (MW)", f"{summary['mean_power_mw']:,.2f}")
            k3.metric("Capacity factor", f"{summary['capacity_factor']:.1%}")
            k4.metric("Max power (MW)", f"{summary['max_power_mw']:,.2f}")
            fig = px.line(data, x="timestamp", y="active_power_mw", title="Measured wind active power")
            st.plotly_chart(fig, use_container_width=True)
            ramps = calculate_ramps(data)
            st.plotly_chart(px.histogram(ramps, x="ramp_mw_per_min", title="Ramp-rate distribution (MW/min)"), use_container_width=True)

            if st.button("Run independent BESS studies", type="primary"):
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
                studies = run_all_studies(data, cfg)
                for name, result in studies.items():
                    st.header(result["title"])
                    m1,m2,m3,m4 = st.columns(4)
                    m1.metric("Estimated PCS power (MW)", f"{result['required_power_mw']:.2f}")
                    m2.metric("Estimated usable energy (MWh)", f"{result['required_usable_energy_mwh']:.2f}")
                    m3.metric("Maximum simulated SOC (MWh)", f"{result['soc_energy_mwh'].max():.2f}")
                    m4.metric("Discharge EFC / data day", f"{result['efc_per_day']:.3f}")
                    st.write(result["interpretation"])
                    chart = result["timeseries"]
                    fig2 = px.line(chart, x="timestamp", y=["active_power_mw","target_power_mw","bess_power_mw"], title=f"{name}: wind, target and battery power")
                    st.plotly_chart(fig2, use_container_width=True)
                    fig3 = px.line(chart, x="timestamp", y="soc_percent", title=f"{name}: SOC trajectory")
                    st.plotly_chart(fig3, use_container_width=True)
                    st.dataframe(result["metrics"], use_container_width=True)
                output = build_excel_report(studies, data, checks)
                st.download_button("Download engineering Excel report", output, file_name="wind_bess_sizing_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            for error in checks["errors"]:
                st.error(error)
    except Exception as exc:
        st.exception(exc)
else:
    st.markdown("### Getting started")
    st.markdown("1. Upload `sample_data/synthetic_wind_15min.csv` to test the workflow.\n2. Map the timestamp, active power, and wind speed columns.\n3. Review data-quality findings.\n4. Run all three sizing studies and export the results.")
    st.markdown("**Interpretation warning:** outputs depend on the selected target and assumptions. Review feasibility, unmet energy, SOC bounds, and data coverage before using results in design.")
