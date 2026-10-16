# Wind-BESS Independent Sizing Intelligence — Version 1

## Purpose
A modular Streamlit prototype that analyzes wind time-series data and generates separate screening studies for:
1. Ramp-rate control / wind smoothing
2. Wind energy shifting / surplus capture
3. Firm power delivery against a target

This is a technical prototype, not a final design tool. Results require engineering review and project-specific constraints.

## Run in PyCharm (Windows PowerShell)
```powershell
cd path\to\Wind_BESS_Intelligence_V1
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```
If activation is blocked, run:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Run tests
```powershell
python -m pytest -q
```

## Input schema
CSV or Excel with a timestamp column and active power in MW. Wind speed in m/s is optional but recommended. The user maps columns in the UI. Time is parsed as UTC in this prototype; adapt the time-zone policy for the project before operational use.

## Current baseline limitations (must be addressed before design use)
- The three target profiles are initial screening definitions, not a globally optimized dispatch.
- The ramp mode uses a rolling-average target; a true ramp constraint needs a constrained dispatch algorithm and explicit violation accounting.
- Energy shifting uses a constant mean-power target; it is not an economic arbitrage or curtailment optimizer.
- Firm delivery uses a constant user target and may be infeasible when wind energy and storage energy are insufficient.
- The preliminary energy excursion is derived from cumulative requested battery exchange; SOC feasibility and closed-cycle conditions must be made explicit in the next iteration.
- No OEM degradation, thermal, auxiliary load, availability, warranty, or end-of-life model is included.
- Missing intervals are reported, not imputed. Do not interpret the detected median interval as proof that all samples are equally spaced.
- Excel export is implemented. PDF export is planned for the next iteration.
- The current EFC metric is a screening estimate and must be reviewed with the declared energy reference and dispatch convention.

## Engineering verification gates
Do not label a scenario "feasible" until:
1. Battery power limits are enforced.
2. SOC is propagated chronologically and remains within limits.
3. Initial and final SOC policies are declared.
4. Charge/discharge efficiencies and auxiliary consumption are applied consistently.
5. Target residuals, unmet energy, curtailment and losses are reported.
6. Unit tests cover regular and irregular time steps, missing data, sign convention, SOC bounds, power limits, and energy conservation.
7. Results are independently checked against hand calculations or a second implementation.

## Patent workstream
See `patent_workstream/README.md`. The existence of software or ordinary sizing calculations does not establish patentability. Preserve dated technical records, do a prior-art search, and seek patent counsel before public disclosure if patent rights are being considered.
