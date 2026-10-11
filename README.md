# TYLY Weekly Flash

A static sales dashboard built from the TYLY sample extract. Python computes every number; the HTML only displays them.

## Run

```bash
pip install -r requirements.txt
# put the extract at data/raw/TYLY_data_sample.xlsx
python build.py          # writes dist/index.html
```

Open `dist/index.html` in a browser. No server is needed.

## What is on the page

**Sales flash**: net sales for yesterday, week to date (WTD) and period to date (PTD).

- WTD and PTD show YoY. Yesterday shows the value only: with about 35 transactions a day, a single-day YoY is mostly noise.
- LY is matched on fiscal week and weekday (Wed of W30 vs Wed of W30), not on calendar date.
- The reporting date is the last date with TY data, never the system clock.
- PTD starts at W23, the first week in the extract. It is not a full fiscal YTD.
- Each YoY is split into percentage points on a Gen Z × New / Repeat grid. Every number in that grid opens a one-level drill-down by region, store vs online, retail vs outlet, category, product type or product family.

**Customers**: Gen Z new customers and repeat customer share, WTD and PTD.

- When the LY count is under 30, the change is shown as a difference in customers rather than a percentage.
- Share changes are shown in percentage points, with the repeat customer count alongside.

## Structure

```
core/
  periods.py     fiscal calendar: as-of date, WTD and PTD windows aligned to LY
  metrics.py     measures (one function per metric), YoY comparison, contribution and drill-down
build.py         reads the extract, computes everything, checks it, writes dist/index.html
templates/       HTML template; data is injected at build time
dist/            built dashboard
data/            see data/README.md
```

Measures live in `core/metrics.py` as plain functions that take a filtered DataFrame and return one number. The dashboard uses them today; the planned AI brief will call the same functions through its tools, so both always share one definition of each metric.

`build.py` fails if the parts of any split don't add back to their total.

## Not built yet

- Inventory weeks of cover and alert rules
- AI weekly brief with evidence-checked claims
