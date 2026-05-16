# 📋 Guidelines — DataStorm 7.0 Team Conventions

> **Team**: Code_Stomers  
> **Competition**: DataStorm v7.0 – Storming Round  
> **Deadline**: May 17, 2026 — 06:00 AM IST  

---

## 1. Team Workflow

### 1.1 Git Discipline

| Rule | Detail |
|------|--------|
| **Never commit data files** | `.gitignore` specifically ignores the `data/raw/`, `data/bronze/`, `data/silver/`, and `data/gold/` directories. Only `data/output/` is allowed. |
| **Commit only code + docs** | `src/`, `docs/`, `notebooks/`, `README.md`, `.gitignore`, `requirements.txt`, and the final `output/` predictions CSV. |
| **Commit messages** | Use prefix: `[bronze]`, `[silver]`, `[gold]`, `[poi]`, `[model]`, `[docs]`, `[fix]` |
| **Branch strategy** | Work on `main` directly (3-person team, short timeframe — branching is overhead). |

### 1.2 Task Division

| Member | Responsibility | Modules |
|--------|---------------|---------|
| **Member 1** | Data Engineering — DQ checks, Bronze→Silver pipeline | `dq_checks.py`, `ingest.py`, `cleaning.py` |
| **Member 2** | External Data — OpenStreetMap POIs, Open-Meteo weather | `external_data.py` |
| **Member 3** | Modeling — Feature engineering, latent potential model | `features.py`, `model.py` |
| **All** | Report writing, review, final validation | `docs/`, `notebooks/`, PDF report |

---

## 2. Coding Standards

### 2.1 Python Style

```python
# Use descriptive variable names
transactions_clean = pd.read_csv(...)  # ✅ Good
df = pd.read_csv(...)                   # ❌ Too generic

# Use f-strings for logging
print(f"[SILVER] Removed {n_rejected} records from transactions")
```

### 2.2 Module Structure

Every pipeline script in `src/` should follow this template:

```python
"""
Module description
"""

import pandas as pd
import numpy as np
import sys, os

# Add src package path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *       # shared paths and constants
from dq_checks import *    # reusable DQ functions

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

Every module should produce structured console output to assist in debugging:

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

---

## 3. Data Quality Check Conventions

### 3.1 DQ Function Signature

Every DQ check function in `src/dq_checks.py` follows this interface:

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
| **Never silently drop rows** | Every removed record must appear in `data/silver/rejected_records/` with a reason. |
| **Append, don't overwrite** | If multiple checks fail the same record, keep the first failure reason. |
| **Source dataset** | Every rejected record gets a `DQ_Source_Dataset` column. |

### 3.3 Known Data Anomalies Discovered

This catalog tracks all identified anomalies and their resolutions:

| # | Dataset | Anomaly | Count | Action Taken |
|---|---------|---------|-------|--------------|
| 1 | `outlet_master` | Typo: `Bakry` instead of `Bakery` | 395 | Standardize to `Bakery` |
| 2 | `outlet_master` | Typo: `Grocry` instead of `Grocery` | 390 | Standardize to `Grocery` |
| 3 | `outlet_master` | Whitespace: ` Eatery ` instead of `Eatery` | 200+ | Strip whitespace / exact matching |
| 4 | `outlet_master` | Lowercase: `small` instead of `Small` | 600 | Title-case |
| 5 | `outlet_master` | Null `Outlet_Size` | 196 | Imputed using mode of same `Outlet_Type` |
| 6 | `outlet_coordinates`| Lat/Lon swapped (lat > 50°) | 200 | Swapped the columns for those specific rows |
| 7 | `outlet_coordinates`| Zero coordinates (0.0, 0.0) | 40 | Quarantined |
| 8 | `transactions` | Negative `Volume_Liters` (returns) | 4,753 | Quarantined (these represent reverse logistics, not demand) |
| 9 | `transactions` | Zero `Volume_Liters` | 100 | Quarantined (ghost entries) |
| 10 | `transactions` | Missing `Product_Name` | — | Documented discrepancy between spec and actual data |
| 11 | `holidays` | 2023 has 176 entries | 93 | Deduplicated identical holiday rows |

---

## 4. Feature Engineering Conventions

### 4.1 Feature Naming

Use descriptive, prefixed names to instantly identify the source:

```
txn_max_monthly_volume        # Transaction-derived
outlet_size_encoded           # Outlet master
geo_poi_schools               # POI count
weather_temp_jan_avg          # Weather API
pop_outlets_1km               # Density proxy
```

### 4.2 Feature Categories

| Category | Prefix | Source |
|----------|--------|--------|
| Transaction history | `txn_` | `transactions_clean.csv` |
| Outlet attributes | `outlet_` | `outlet_master_clean.csv` |
| Geographic / POI | `geo_`, `poi_` | `outlet_coordinates_clean.csv` + OSM API |
| Weather & Climate | `weather_` | Open-Meteo API |
| Population Proxy | `pop_` | Haversine clustering |
| Distributor & Cal | `dist_`, `cal_` | `seasonality_clean.csv`, `holidays_clean.csv` |

---

## 5. Deliverable Checklist

### Final Submission

- [ ] **`Code_Stomers_predictions.csv`** — `Outlet_ID`, `Maximum_Monthly_Liters`
- [ ] **GitHub repo link** (or zipped folder) containing:
  - [ ] `src/` — all Python code
  - [ ] `docs/` — architecture, guidelines, solution docs
  - [ ] `notebooks/` — EDA & Validation notebooks
  - [ ] `README.md` — end-to-end instructions
  - [ ] `.gitignore` & `requirements.txt`
- [ ] **PDF Report** (max 5 pages):
  - [ ] Page 1: Cover page
  - [ ] Page 2: Data Forensics & Hygiene
  - [ ] Page 3: External Data Acquisition
  - [ ] Page 4: Causal Base Logic & Model ensemble
  - [ ] Page 5: GenAI Transparency Log

---

## 6. Evaluation Awareness

| Criteria | Weight | What Impresses |
|----------|--------|----------------|
| **Data Engineering & Forensics** | 40% | Clean Bronze→Silver→Gold separation; reusable DQ checks; thorough anomaly detection; robust POI/Weather scraping. |
| **Methodology & Base Math** | 40% | Sound conceptualization of "latent potential"; proper handling of censored data; defensible math. |
| **GenAI Utilization** | 20% | Honest documentation of AI usage; iterative prompting. |
