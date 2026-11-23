# Synthetic offline demo fixtures — NOT GOVERNMENT DATA

All files in this folder are fabricated for deterministic testing. Their names mimic the **roles** of NTD, Census and NOAA records; no value is asserted to be an actual transit, population or weather observation. The prefix `DEMO-` and source vintage `SYNTHETIC-2025` are intentional.

## Files

- `ntd_synthetic.csv`: invented unlinked trips by agency, mode and report year.
- `census_synthetic.csv`: invented population for matching geography/year.
- `noaa_synthetic.csv`: invented temperature/precipitation and observation coverage.
- `geography_crosswalk_synthetic.csv`: **A1 verified** for demo fixture calculations; **A2 deliberately unverified** to test refusal of unsound per-capita comparisons.

## Known facts for offline regression

- A1 Bus trips increased 25% from 1,000,000 in 2022 to 1,250,000 in 2025.
- A1 Bus 2025 per-capita trips: `1_250_000 / 103_000 = 12.13592233…`; only compute because fixture crosswalk `join_verified=true`.
- Combined A1+A2 Bus 2025 trips: 2,050,000.
- NOAA A 2025 has only 350 observed days; a coverage warning must be displayed in relevant annual aggregations.
- A2 `join_verified=false`: **withhold** population-normalized and station-linked interpretation for A2 unless reviewer explicitly supplies validated crosswalk.

## Golden path

Host these local files **inside DataBridge's demo-only import source** and send them through the same adapter → validation → DuckDB → registration → notebook chat path as real Data.gov downloads. Do not build a fake successful-import UI that bypasses import code. Label demo screen “Synthetic fixtures” in offline mode.
