# Data

Place the provided extract at `data/raw/TYLY_data_sample.xlsx` before running `python build.py`.

The raw file is not committed (see `.gitignore`). The built dashboard in `dist/index.html` contains only aggregated figures, not transaction-level rows.

Grain and known traps found while profiling:

- **Data** sheet: one row per transaction line, FY26 (TY) and FY25 (LY), fiscal weeks W23 to W30. TXN_ID is unique per row.
- **Inventory** sheet: weekly on-hand units per STYLE_GROUP (a periodic snapshot, not a transaction table).
- FY26 W30 is partial: data ends on Wed 2026-08-19, while FY25 W30 is a full week. Week-to-date comparisons therefore match LY on the same fiscal days.
- 3,600 customers for 3,609 lines, so repeat behaviour can't be measured inside the extract; retention uses COHORT_STATUS, which is assigned from the customer's full purchase history.
- COHORT_STATUS describes the transaction, not the customer, so it stays on the fact table.
