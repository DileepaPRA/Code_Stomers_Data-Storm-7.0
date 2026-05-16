"""
config.py
=========
Shared paths, constants, and parameters for the entire pipeline.
All paths are relative to the project root (one level up from src/).
"""

import os

# ---------------------------------------------------------------------------
# BASE PATHS
# ---------------------------------------------------------------------------
# Project root (one level up from src/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Data directories (Lakehouse layers under data/)
DATA_DIR        = os.path.join(PROJECT_ROOT, "data")
RAW_DIR         = os.path.join(DATA_DIR, "raw")
BRONZE_DIR      = os.path.join(DATA_DIR, "bronze")
SILVER_DIR      = os.path.join(DATA_DIR, "silver")
REJECTED_DIR    = os.path.join(SILVER_DIR, "rejected_records")
GOLD_DIR        = os.path.join(DATA_DIR, "gold")
OUTPUT_DIR      = os.path.join(DATA_DIR, "output")

# Other directories
NOTEBOOKS_DIR   = os.path.join(PROJECT_ROOT, "notebooks")
REPORTS_DIR     = os.path.join(PROJECT_ROOT, "reports")
DOCS_DIR        = os.path.join(PROJECT_ROOT, "docs")

# ---------------------------------------------------------------------------
# FILE NAMES (Bronze layer — exact copies of raw)
# ---------------------------------------------------------------------------
TRANSACTIONS_FILE   = "transactions_history_final.csv"
OUTLET_MASTER_FILE  = "outlet_master.csv"
OUTLET_COORDS_FILE  = "outlet_coordinates.csv"
SEASONALITY_FILE    = "distributor_seasonality_details.csv"
HOLIDAYS_FILE       = "holiday_list.csv"

# ---------------------------------------------------------------------------
# CLEANED FILE NAMES (Silver layer)
# ---------------------------------------------------------------------------
TRANSACTIONS_CLEAN  = "transactions_clean.csv"
OUTLET_MASTER_CLEAN = "outlet_master_clean.csv"
OUTLET_COORDS_CLEAN = "outlet_coordinates_clean.csv"
SEASONALITY_CLEAN   = "seasonality_clean.csv"
HOLIDAYS_CLEAN      = "holidays_clean.csv"

# Rejected
TRANSACTIONS_REJECTED  = "transactions_rejected.csv"
OUTLET_MASTER_REJECTED = "outlet_master_rejected.csv"
OUTLET_COORDS_REJECTED = "outlet_coordinates_rejected.csv"

# ---------------------------------------------------------------------------
# GOLD FILE NAMES
# ---------------------------------------------------------------------------
POI_DATA_FILE        = "poi_data.csv"
EXTERNAL_FEATURES    = "external_features.csv"
OUTLET_FEATURES_FILE = "outlet_features.csv"
MODEL_READY_FILE     = "model_ready.csv"
POTENTIAL_ANALYSIS   = "potential_analysis.csv"

# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------
PREDICTIONS_FILE    = "Code_Stomers_predictions.csv"
TEAM_NAME           = "Code_Stomers"

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
VALID_DISTRIBUTORS = [
    'DIST_W_01', 'DIST_W_02', 'DIST_W_03',
    'DIST_C_01', 'DIST_C_02', 'DIST_C_03',
    'DIST_NW_01', 'DIST_NW_02',
    'DIST_S_01', 'DIST_S_02',
]

DISTRIBUTOR_PROVINCE = {
    'DIST_W_01': 'Western', 'DIST_W_02': 'Western', 'DIST_W_03': 'Western',
    'DIST_C_01': 'Central', 'DIST_C_02': 'Central', 'DIST_C_03': 'Central',
    'DIST_NW_01': 'North-Western', 'DIST_NW_02': 'North-Western',
    'DIST_S_01': 'Southern', 'DIST_S_02': 'Southern',
}

VALID_OUTLET_TYPES = ['Hotel', 'Grocery', 'SMMT', 'Pharmacy', 'Kiosk', 'Bakery', 'Eatery']

OUTLET_TYPE_FIXES = {
    'Bakry': 'Bakery',
    'Grocry': 'Grocery',
    ' Eatery': 'Eatery',
    'Eatery ': 'Eatery',
    ' Eatery ': 'Eatery',
}

OUTLET_SIZE_ORDER = {'Small': 1, 'Medium': 2, 'Large': 3, 'Extra Large': 4}

# Sri Lanka coordinate bounds
SRI_LANKA_LAT_MIN = 5.9
SRI_LANKA_LAT_MAX = 9.9
SRI_LANKA_LON_MIN = 79.4
SRI_LANKA_LON_MAX = 82.0

# Seasonality encoding
SEASONALITY_ENCODING = {
    'Favorable': 1.15,
    'Moderate': 1.0,
    'Un-Favorable': 0.85,
}

# POI scraping config
POI_RADIUS_METERS = 1000
POI_BATCH_SIZE = 50

# Prediction target
TARGET_YEAR = 2026
TARGET_MONTH = 1  # January

# ---------------------------------------------------------------------------
# ENSURE DIRECTORIES EXIST
# ---------------------------------------------------------------------------
for d in [RAW_DIR, BRONZE_DIR, SILVER_DIR, REJECTED_DIR, GOLD_DIR,
          OUTPUT_DIR, NOTEBOOKS_DIR, REPORTS_DIR]:
    os.makedirs(d, exist_ok=True)
