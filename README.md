# Data Storm 7.0 — Team CodeStormers

## 🎯 Challenge: Maximum Monthly Purchase Potential (Jan 2026)

Estimating the **latent maximum monthly volume potential** (in liters) for ~20,000 traditional trade outlets across 4 provinces in Sri Lanka, for January 2026.

---

## 📁 Repository Structure

```
data storm/
├── datastorm-7-0-rotaract/          # Raw datasets (source)
│   ├── transactions_history_final.csv
│   ├── outlet_master.csv
│   ├── outlet_coordinates.csv
│   ├── distributor_seasonality_details.csv
│   ├── holiday_list.csv
│   └── 1. dataset_description.xlsx
│
├── Lakehouse/
│   ├── bronze/                      # Raw data (as-is ingestion)
│   ├── silver/                      # Cleaned & validated data
│   │   └── quarantined/             # Records that failed DQ checks
│   ├── gold/                        # Enriched features & predictions
│   │   ├── poi_features.csv         # POI scraped data
│   │   ├── outlet_enriched_features.csv
│   │   └── predictions_detailed.csv
│   └── scripts/
│       ├── 01_bronze_ingestion.py   # Bronze layer ingestion
│       ├── 02_silver_cleaning.py    # Silver layer DQ & cleaning
│       ├── 03_poi_scraping.py       # POI scraping (Overpass API)
│       ├── 04_gold_potential.py     # Gold layer potential estimation
│       ├── data_quality.py          # Reusable DQ library
│       └── run_pipeline.py          # Master pipeline orchestrator
│
├── CodeStormers_predictions.csv     # ⭐ Final submission
├── README.md                        # This file
└── requirements.txt
```

---

## 🚀 How to Run

### Prerequisites
```bash
pip install -r requirements.txt
```

### Run Full Pipeline
```bash
cd Lakehouse/scripts
python run_pipeline.py
```

Or run individual steps:
```bash
python 01_bronze_ingestion.py    # Ingest raw data
python 02_silver_cleaning.py     # Clean & validate
python 03_poi_scraping.py        # Scrape POI data
python 04_gold_potential.py      # Estimate potential
```

---

## 🏗️ Architecture: Lakehouse Pipeline

### Bronze (Raw Ingestion)
- Copies all flat files as-is with zero transformations
- Adds ingestion manifest with timestamps and file metadata

### Silver (Cleaned)
- **Reusable DQ Functions** (`data_quality.py`):
  - `check_duplicates()` — Primary key duplicate detection
  - `check_nulls()` — Mandatory field null/empty validation
  - `check_referential_integrity()` — Foreign key validation across datasets
  - `check_value_range()` — Numeric boundary enforcement
  - `check_format()` — Data type and pattern validation (dates, IDs, regex)
  - `check_outliers_iqr()` — Statistical outlier detection (IQR method)
  - `run_quality_pipeline()` — Composable pipeline runner
- **Quarantine Policy**: Failed records are **never deleted** — they're saved to `silver/quarantined/` with documented failure reasons
- **Data Corrections**: Typo fixes (e.g., "Grocry" → "Grocery"), case normalization, type casting

### Gold (Enriched)
- POI features from OpenStreetMap Overpass API
- Peer group benchmarks
- Outlet-level engineered features
- Final potential predictions

---

## 🧠 Methodology: Left-Censored Demand Uncapping

### The Core Insight
Historical sales represent **min(true_demand, supply_constraints)**. They are *left-censored* — we observe what outlets *did sell*, not what they *could sell*.

### Mathematical Framework

For each outlet *i*:

```
Potential_i = Base_Potential × Seasonality × POI_Uplift × Growth × Cooler_Effect

Where:
  Base_Potential = max(Own_P95, Peer_P90 × 0.8, Historical_Max)
  
  If constrained:
    Base_Potential *= Uncap_Factor (1.10 – 1.30)
```

### Components:

1. **Peer Benchmarking**: Group outlets by (Type, Size, Region). An outlet's potential should be at least as high as its peers' P90 — if it isn't, it's likely constrained.

2. **Constraint Detection**: Outlets with low coefficient of variation (CV < 0.15) and frequent near-max values are flagged as supply-constrained. These receive an uncapping multiplier of 1.10–1.30 based on how far they fall below peer benchmarks.

3. **Seasonality Adjustment**: Distributor-specific January multipliers derived from historical Seasonality_Index patterns.

4. **POI-Based Demand Uplift**: Proximity to schools, hospitals, and bus stops correlates with foot traffic. A composite accessibility score drives a multiplicative uplift (up to 25%).

5. **Growth Trend**: Positive YoY volume trajectory is captured as a growth factor (capped at 15%).

6. **Cooler Effect**: Each cooler adds ~3% potential (capped at 15%), reflecting cold beverage availability.

---

## 📍 POI Scraping

- **API**: OpenStreetMap Overpass API
- **Categories**: Schools, Hospitals/Clinics, Bus Stops/Stations
- **Radii**: 500m, 1km, 2km
- **Features**: Count at each radius, nearest distance, composite accessibility score
- **Caching**: Results cached to `gold/_poi_raw_cache.json` to avoid re-scraping

---

## 📊 Evaluation Focus

| Category | Weight | Our Approach |
|----------|--------|-------------|
| Data Engineering & Forensics | 40% | Full Lakehouse pipeline, reusable DQ library, quarantine system |
| Methodology & Base Math | 40% | Left-censored uncapping with peer benchmarks, constraint detection |
| GenAI Utilization | 20% | AI-assisted pipeline design, code generation, report drafting |

---

## 👥 Team CodeStormers

Data Storm 7.0 — OCTAVE by John Keells Group
