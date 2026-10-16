# V1.1 — Automatic Wind Dataset Understanding

## Added
- Inspect all Excel worksheets and select the most plausible data sheet.
- Automatic semantic mapping for timestamp, active power, wind speed, available power, grid export, and curtailment.
- Explicit-header unit detection for MW/kW and wind speed m/s, km/h, knots.
- Canonical normalized schema with UTC timestamps.
- Downloadable normalized CSV and interpretation JSON audit log.
- Sizing gate blocks ambiguous power units and power exceeding 105% of configured wind-farm rating.
- Tests for automatic mapping, unit conversion, ambiguous units, and implausible power.

## Limitations
- Rule-based interpretation, not a general-purpose AI model.
- Units are converted only when evidence is explicit in headers.
- Naive timestamps are assumed UTC in this prototype; local-time data needs an explicit timezone policy.
- Unfamiliar schemas may be refused rather than guessed.
- BESS sizing algorithms remain preliminary screening methods, not constraint-verified dispatch optimizers.
