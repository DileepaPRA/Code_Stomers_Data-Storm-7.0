# 📋 Guidelines — DataStorm 7.0 Team Conventions

> **Team**: Code_Stomers  
> **Competition**: DataStorm v7.0 – Storming Round  
> **Deadline**: May 17, 2026 — 06:00 AM IST  
> **Last updated**: May 15, 2026

---

## 1. Team Workflow

### 1.1 Git Discipline

| Rule | Detail |
|------|--------|
| **Never commit data files** | `.gitignore` already blocks `bronze/`, `silver/`, `gold/`, `*.csv`, `*.parquet`, `*.xlsx` |
| **Commit only code + docs** | `scripts/`, `docs/`, `README.md`, `.gitignore`, and the final `output/` predictions CSV |
| **Commit messages** | Use prefix: `[bronze]`, `[silver]`, `[gold]`, `[poi]`, `[model]`, `[docs]`, `[fix]` |
| **Branch strategy** | Work on `main` directly (3-person team, 36-hour hackathon — branching is overhead) |
| **Pull before push** | Always `git pull` before starting work to avoid conflicts |

### 1.2 Task Division (Suggested)

| Member | Responsibility | Scripts |
|--------|---------------|---------|
| **Member 1** | Data Engineering — DQ checks, Bronze→Silver pipeline | `dq_checks.py`, `01_bronze_ingest.py`, `02_silver_clean.py` |
| **Member 2** | External Data — POI scraping, coordinate fixing | `03_poi_scraping.py` |
| **Member 3** | Modeling — Feature engineering, latent potential model | `04_gold_feature_engineering.py`, `05_latent_potential_model.py` |
| **All** | Report writing, review, final validation | `docs/`, `README.md`, PDF report |

### 1.3 Communication

- Keep this `docs/` folder updated as you discover anomalies or make design choices
- Document every non-obvious decision inline in code comments
- If you find a new data anomaly, add it to Section 5 of this document

---

## 2. Coding Standards

### 2.1 Python Style

```python
# Use descriptive variable names — not 'df' or 'x'
transactions_clean = pd.read_csv(...)  # ✅ Good
df = pd.read_csv(...)                   # ❌ Too generic when multiple DataFrames exist

# Use f-strings for logging
print(f"[SILVER] Removed {n_rejected} records from transactions")

# Every script starts with a docstring block explaining what it does
"""
02_silver_clean.py
==================
Applies DQ checks to all Bronze-layer datasets.
Outputs cleaned CSVs to silver/ and quarantined records to silver/rejected_records/.
"""
```

### 2.2 Script Structure

Every pipeline script should follow this template:

```python
"""
Script description
"""

import pandas as pd
import numpy as np
import sys, os

# Add scripts dir to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import *       # shared paths and constants
from dq_checks import *    # reusable DQ functions (only in silver script)

def main():
    """Main pipeline logic."""
    # 1. Load data
    # 2. Process
    # 3. Save outputs
    # 4. Print summary

if __name__ == "__main__":
    main()
```

### 2.3 Logging & Print Output

Every script should produce clear, structured console output:

```
==============================================================
[SILVER] Processing: transactions_history_final.csv
==============================================================
  Input records: 2,376,389
  [DQ] Duplicate Check on [Outlet_ID, Year, Month, SKU_ID]: 0 duplicates
  [DQ] Null Check on [Outlet_ID, Volume_Liters]: 0 failures
  [DQ] Value Range (Volume_Liters >= 0): 4,753 failures
  ...
==============================================================
  Output: 2,371,536 passed, 4,853 quarantined
==============================================================
```

### 2.4 File I/O

| Convention | Detail |
|------------|--------|
| **Read from** | Previous layer's folder (e.g., Silver reads from Bronze) |
| **Write to** | Current layer's folder |
| **CSV encoding** | `utf-8` always |
| **Index** | Never save DataFrame index (`index=False`) |
| **Float precision** | 2 decimal places for volume/value in final output |

---

## 3. Data Quality Check Conventions

### 3.1 DQ Function Signature

Every DQ check function must follow this interface:

```python
def check_<name>(df, **params) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (passed_df, failed_df).
    failed_df always has a 'DQ_Failure_Reason' column.
    """
```

### 3.2 Quarantine Rules

| Rule | Detail |
|------|--------|
| **Never silently drop rows** | Every removed record must appear in `rejected_records/` with a reason |
| **Append, don't overwrite** | If multiple checks fail the same record, keep the first failure reason |
| **Timestamp** | Every rejected record gets a `DQ_Check_Timestamp` column |
| **Source dataset** | Every rejected record gets a `DQ_Source_Dataset` column |

### 3.3 Known Data Anomalies Discovered

This is a **living section** — update it as you find new issues:

| # | Dataset | Anomaly | Count | Action |
|---|---------|---------|-------|--------|
| 1 | `outlet_master` | Typo: `Bakry` instead of `Bakery` | 395 | Standardize to `Bakery` |
| 2 | `outlet_master` | Typo: `Grocry` instead of `Grocery` | 390 | Standardize to `Grocery` |
| 3 | `outlet_master` | Leading space: ` Eatery` instead of `Eatery` | 200 | Strip whitespace |
| 4 | `outlet_master` | Lowercase: `small` instead of `Small` | 600 | Title-case |
| 5 | `outlet_master` | Null `Outlet_Size` | 196 | Impute using mode of same `Outlet_Type` or quarantine |
| 6 | `outlet_coordinates` | Lat/Lon swapped (lat > 50°) | 200 | Swap the two columns for those rows |
| 7 | `outlet_coordinates` | Zero coordinates (0.0, 0.0) | 40 | Quarantine — cannot fix without external data |
| 8 | `transactions` | Negative `Volume_Liters` (returns/credits) | 4,753 | Quarantine — these are likely credit notes/returns, not real sales |
| 9 | `transactions` | Zero `Volume_Liters` | 100 | Quarantine — ghost/system entries |
| 10 | `transactions` | Extreme outlier volumes (max ~9,400L in a single SKU-month) | TBD | Flag with IQR, review |
| 11 | `transactions` | `Product_Name` column missing (described in spec but absent) | — | Not a failure — proceed without it |
| 12 | `holidays` | 2023 has 176 holidays vs 95/78 for 2024/2025 | — | Likely includes weekends in 2023 — investigate |
| 13 | `seasonality` | `Seasonality_Index` is a string (`Moderate`, `Favorable`, `Un-Favorable`) | — | Encode numerically in Gold layer |

---

## 4. Feature Engineering Conventions

### 4.1 Feature Naming

Use descriptive, prefixed names:

```
txn_total_volume_36m          # Transaction-derived, total volume over 36 months
txn_avg_monthly_volume        # Transaction-derived, average
txn_max_monthly_volume        # Transaction-derived, max observed
txn_months_active             # How many months had transactions
txn_volume_trend_slope        # Linear regression slope of monthly volume
outlet_size_encoded           # Outlet master, encoded
outlet_cooler_count           # Outlet master
geo_poi_schools_1km           # POI count, schools within 1km
geo_poi_hospitals_1km         # POI count
geo_latitude                  # Coordinate
geo_longitude                 # Coordinate
dist_seasonality_jan2026      # Distributor seasonality for prediction month
cal_holidays_jan2026          # Calendar feature, number of holidays
```

### 4.2 Feature Categories

| Category | Prefix | Source |
|----------|--------|--------|
| Transaction history | `txn_` | `transactions_clean.csv` |
| Outlet attributes | `outlet_` | `outlet_master_clean.csv` |
| Geographic / POI | `geo_` | `outlet_coordinates_clean.csv` + `poi_data.csv` |
| Distributor | `dist_` | `seasonality_clean.csv` |
| Calendar | `cal_` | `holidays_clean.csv` |

---

## 5. Deliverable Checklist

### Final Submission (via Google Form by May 17, 06:00 AM)

- [ ] **`Code_Stomers_predictions.csv`** — columns: `Outlet_ID`, `Maximum_Monthly_Liters`
- [ ] **GitHub repo link** (or zipped folder) containing:
  - [ ] `scripts/` — all Python code
  - [ ] `docs/` — architecture, guidelines, solution docs
  - [ ] `README.md` — end-to-end run instructions
  - [ ] `.gitignore`
- [ ] **PDF Report** (max 5 pages incl. cover):
  - [ ] Page 1: Cover page
  - [ ] Page 2: Data Forensics & Hygiene — anomalies found, quarantine setup, DQ checks
  - [ ] Page 3: POI Data Acquisition — Overpass API approach, POI types, mapping to outlets
  - [ ] Page 4: Causal Base Logic — censored demand methodology, math framework
  - [ ] Page 5: GenAI Transparency Log — how/where/why LLMs were used

---

## 6. Evaluation Awareness

These are what judges will look for — keep them visible:

| Criteria | Weight | What Impresses |
|----------|--------|----------------|
| **Data Engineering & Forensics** | 40% | Clean Bronze→Silver→Gold separation; reusable DQ checks; thorough anomaly detection; robust POI scraping; meaningful features |
| **Methodology & Base Math** | 40% | Sound conceptualization of "latent potential"; proper handling of censored data (Tobit, survival analysis, or quantile methods); defensible math |
| **GenAI Utilization** | 20% | Honest documentation of AI usage; evidence of critical evaluation, not blind trust; iterative prompting |

---

## 7. Quick Reference: Common Commands

```bash
# Run the full pipeline
python scripts/01_bronze_ingest.py
python scripts/02_silver_clean.py
python scripts/03_poi_scraping.py
python scripts/04_gold_feature_engineering.py
python scripts/05_latent_potential_model.py

# Check rejected records
python -c "import pandas as pd; print(pd.read_csv('silver/rejected_records/transactions_rejected.csv').shape)"

# Preview final predictions
python -c "import pandas as pd; df=pd.read_csv('output/Code_Stomers_predictions.csv'); print(df.describe())"
```
