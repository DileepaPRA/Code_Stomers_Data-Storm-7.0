"""
=============================================================================
SILVER LAYER - Data Cleaning & Quality Enforcement
=============================================================================
Team: CodeStormers | Data Storm 7.0
Purpose: Apply all DE checks and data cleaning logic to produce sanitized
         datasets. Records failing checks are quarantined into
         silver/quarantined/ with documented failure reasons.
=============================================================================
"""

import pandas as pd
import numpy as np
import os
import json
import sys

# Add scripts to path
sys.path.insert(0, os.path.dirname(__file__))
from data_quality import (
    check_duplicates, check_nulls, check_referential_integrity,
    check_value_range, check_format, check_outliers_iqr,
    run_quality_pipeline
)

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.join(os.path.dirname(__file__), '..')
BRONZE_DIR     = os.path.join(BASE_DIR, 'bronze')
SILVER_DIR     = os.path.join(BASE_DIR, 'silver')
QUARANTINE_DIR = os.path.join(SILVER_DIR, 'quarantined')

os.makedirs(SILVER_DIR, exist_ok=True)
os.makedirs(QUARANTINE_DIR, exist_ok=True)


def save_results(clean_df, quarantined_df, dataset_name, reports):
    """Save clean data to silver, quarantined to silver/quarantined."""
    clean_path = os.path.join(SILVER_DIR, f'{dataset_name}_clean.csv')
    clean_df.to_csv(clean_path, index=False)
    print(f"  💾 Clean data saved: {clean_path} ({len(clean_df):,} rows)")

    if len(quarantined_df) > 0:
        q_path = os.path.join(QUARANTINE_DIR, f'{dataset_name}_quarantined.csv')
        quarantined_df.to_csv(q_path, index=False)
        print(f"  🔒 Quarantined saved: {q_path} ({len(quarantined_df):,} rows)")

    report_path = os.path.join(SILVER_DIR, f'{dataset_name}_dq_report.json')
    with open(report_path, 'w') as f:
        json.dump(reports, f, indent=2, default=str)
    print(f"  📋 DQ report saved: {report_path}")


# ═══════════════════════════════════════════════════════════════════════════
# 1. TRANSACTIONS HISTORY
# ═══════════════════════════════════════════════════════════════════════════
def clean_transactions():
    """Clean transactions_history_final.csv"""
    print("\n" + "▓" * 60)
    print("  CLEANING: transactions_history_final")
    print("▓" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, 'transactions_history_final.csv'))
    print(f"  Raw shape: {df.shape}")

    # Define quality checks pipeline
    checks = [
        {
            'function': check_nulls,
            'params': {
                'mandatory_cols': ['Outlet_ID', 'Year', 'Month', 'Distributor_ID',
                                   'SKU_ID', 'Volume_Liters', 'Total_Bill_Value'],
                'check_name': 'txn_null_check'
            }
        },
        {
            'function': check_format,
            'params': {
                'col': 'Outlet_ID',
                'expected_type': 'id',
                'pattern': r'^OUT_\d{5}$',
                'check_name': 'txn_outlet_id_format'
            }
        },
        {
            'function': check_format,
            'params': {
                'col': 'Distributor_ID',
                'expected_type': 'id',
                'pattern': r'^DIST_(W|C|NW|S)_\d{2}$',
                'check_name': 'txn_distributor_id_format'
            }
        },
        {
            'function': check_format,
            'params': {
                'col': 'SKU_ID',
                'expected_type': 'id',
                'pattern': r'^SKU_\d{2}$',
                'check_name': 'txn_sku_id_format'
            }
        },
        {
            'function': check_value_range,
            'params': {
                'col': 'Volume_Liters',
                'min_val': 0.0,
                'max_val': None,
                'check_name': 'txn_volume_non_negative'
            }
        },
        {
            'function': check_value_range,
            'params': {
                'col': 'Total_Bill_Value',
                'min_val': 0.0,
                'max_val': None,
                'check_name': 'txn_bill_non_negative'
            }
        },
        {
            'function': check_value_range,
            'params': {
                'col': 'Year',
                'min_val': 2020,
                'max_val': 2026,
                'check_name': 'txn_year_range'
            }
        },
        {
            'function': check_value_range,
            'params': {
                'col': 'Month',
                'min_val': 1,
                'max_val': 12,
                'check_name': 'txn_month_range'
            }
        },
        {
            'function': check_duplicates,
            'params': {
                'primary_key_cols': ['Outlet_ID', 'Year', 'Month', 'Distributor_ID', 'SKU_ID'],
                'check_name': 'txn_duplicate_check'
            }
        },
        {
            'function': check_outliers_iqr,
            'params': {
                'col': 'Volume_Liters',
                'iqr_factor': 3.0,
                'check_name': 'txn_volume_extreme_outlier'
            }
        },
    ]

    clean_df, quarantined_df, reports = run_quality_pipeline(df, checks, 'transactions')

    # Post-clean type casting
    clean_df['Year'] = clean_df['Year'].astype(int)
    clean_df['Month'] = clean_df['Month'].astype(int)

    save_results(clean_df, quarantined_df, 'transactions', reports)
    return clean_df


# ═══════════════════════════════════════════════════════════════════════════
# 2. OUTLET MASTER
# ═══════════════════════════════════════════════════════════════════════════
def clean_outlet_master():
    """Clean outlet_master.csv"""
    print("\n" + "▓" * 60)
    print("  CLEANING: outlet_master")
    print("▓" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, 'outlet_master.csv'))
    print(f"  Raw shape: {df.shape}")

    checks = [
        {
            'function': check_nulls,
            'params': {
                'mandatory_cols': ['Outlet_ID', 'Outlet_Size', 'Outlet_Type'],
                'check_name': 'outlet_null_check'
            }
        },
        {
            'function': check_duplicates,
            'params': {
                'primary_key_cols': ['Outlet_ID'],
                'check_name': 'outlet_duplicate_check'
            }
        },
        {
            'function': check_format,
            'params': {
                'col': 'Outlet_ID',
                'expected_type': 'id',
                'pattern': r'^OUT_\d{5}$',
                'check_name': 'outlet_id_format'
            }
        },
    ]

    clean_df, quarantined_df, reports = run_quality_pipeline(df, checks, 'outlet_master')

    # Standardize Outlet_Type (fix typos like 'Grocry' → 'Grocery')
    type_corrections = {
        'Grocry': 'Grocery',
        'grocry': 'Grocery',
        'grocery': 'Grocery',
        'hotel': 'Hotel',
        'pharmacy': 'Pharmacy',
        'Restraurant': 'Restaurant',
        'restraurant': 'Restaurant',
        'restaurant': 'Restaurant',
        'Kade': 'Kade',
        'kade': 'Kade',
        'Eatery': 'Eatery',
        'eatery': 'Eatery',
    }
    clean_df['Outlet_Type_Original'] = clean_df['Outlet_Type']
    clean_df['Outlet_Type'] = clean_df['Outlet_Type'].replace(type_corrections)

    # Standardize Outlet_Size
    size_corrections = {
        'small': 'Small',
        'medium': 'Medium',
        'large': 'Large',
        'SMALL': 'Small',
        'MEDIUM': 'Medium',
        'LARGE': 'Large',
    }
    clean_df['Outlet_Size'] = clean_df['Outlet_Size'].replace(size_corrections)

    # Ensure Cooler_Count is non-negative integer
    clean_df['Cooler_Count'] = pd.to_numeric(clean_df['Cooler_Count'], errors='coerce').fillna(0).astype(int)
    clean_df['Cooler_Count'] = clean_df['Cooler_Count'].clip(lower=0)

    save_results(clean_df, quarantined_df, 'outlet_master', reports)
    return clean_df


# ═══════════════════════════════════════════════════════════════════════════
# 3. OUTLET COORDINATES
# ═══════════════════════════════════════════════════════════════════════════
def clean_outlet_coordinates():
    """Clean outlet_coordinates.csv"""
    print("\n" + "▓" * 60)
    print("  CLEANING: outlet_coordinates")
    print("▓" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, 'outlet_coordinates.csv'))
    print(f"  Raw shape: {df.shape}")

    checks = [
        {
            'function': check_nulls,
            'params': {
                'mandatory_cols': ['Outlet_ID', 'Latitude', 'Longitude'],
                'check_name': 'coords_null_check'
            }
        },
        {
            'function': check_duplicates,
            'params': {
                'primary_key_cols': ['Outlet_ID'],
                'check_name': 'coords_duplicate_check'
            }
        },
        {
            'function': check_format,
            'params': {
                'col': 'Outlet_ID',
                'expected_type': 'id',
                'pattern': r'^OUT_\d{5}$',
                'check_name': 'coords_outlet_id_format'
            }
        },
        # Sri Lanka bounding box: Lat 5.9–9.9, Lon 79.5–81.9
        {
            'function': check_value_range,
            'params': {
                'col': 'Latitude',
                'min_val': 5.5,
                'max_val': 10.0,
                'check_name': 'coords_latitude_sri_lanka'
            }
        },
        {
            'function': check_value_range,
            'params': {
                'col': 'Longitude',
                'min_val': 79.0,
                'max_val': 82.0,
                'check_name': 'coords_longitude_sri_lanka'
            }
        },
    ]

    clean_df, quarantined_df, reports = run_quality_pipeline(df, checks, 'outlet_coordinates')
    save_results(clean_df, quarantined_df, 'outlet_coordinates', reports)
    return clean_df


# ═══════════════════════════════════════════════════════════════════════════
# 4. DISTRIBUTOR SEASONALITY
# ═══════════════════════════════════════════════════════════════════════════
def clean_seasonality():
    """Clean distributor_seasonality_details.csv"""
    print("\n" + "▓" * 60)
    print("  CLEANING: distributor_seasonality_details")
    print("▓" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, 'distributor_seasonality_details.csv'))
    print(f"  Raw shape: {df.shape}")

    checks = [
        {
            'function': check_nulls,
            'params': {
                'mandatory_cols': ['Distributor_ID', 'Year', 'Month', 'Seasonality_Index'],
                'check_name': 'season_null_check'
            }
        },
        {
            'function': check_format,
            'params': {
                'col': 'Distributor_ID',
                'expected_type': 'id',
                'pattern': r'^DIST_(W|C|NW|S)_\d{2}$',
                'check_name': 'season_distributor_id_format'
            }
        },
        {
            'function': check_duplicates,
            'params': {
                'primary_key_cols': ['Distributor_ID', 'Year', 'Month'],
                'check_name': 'season_duplicate_check'
            }
        },
        {
            'function': check_value_range,
            'params': {
                'col': 'Month',
                'min_val': 1,
                'max_val': 12,
                'check_name': 'season_month_range'
            }
        },
    ]

    clean_df, quarantined_df, reports = run_quality_pipeline(df, checks, 'seasonality')

    # Standardize Seasonality_Index values
    seasonality_map = {
        'Favorable': 'Favorable',
        'favorable': 'Favorable',
        'Moderate': 'Moderate',
        'moderate': 'Moderate',
        'Un-Favorable': 'Un-Favorable',
        'un-favorable': 'Un-Favorable',
        'Unfavorable': 'Un-Favorable',
        'unfavorable': 'Un-Favorable',
    }
    clean_df['Seasonality_Index'] = clean_df['Seasonality_Index'].replace(seasonality_map)

    save_results(clean_df, quarantined_df, 'seasonality', reports)
    return clean_df


# ═══════════════════════════════════════════════════════════════════════════
# 5. HOLIDAY LIST
# ═══════════════════════════════════════════════════════════════════════════
def clean_holidays():
    """Clean holiday_list.csv"""
    print("\n" + "▓" * 60)
    print("  CLEANING: holiday_list")
    print("▓" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, 'holiday_list.csv'))
    print(f"  Raw shape: {df.shape}")

    checks = [
        {
            'function': check_nulls,
            'params': {
                'mandatory_cols': ['Date', 'Holiday_Name', 'Holiday_Type'],
                'check_name': 'holiday_null_check'
            }
        },
        {
            'function': check_format,
            'params': {
                'col': 'Date',
                'expected_type': 'date',
                'check_name': 'holiday_date_format'
            }
        },
        {
            'function': check_duplicates,
            'params': {
                'primary_key_cols': ['Date', 'Holiday_Name'],
                'check_name': 'holiday_duplicate_check'
            }
        },
    ]

    clean_df, quarantined_df, reports = run_quality_pipeline(df, checks, 'holidays')

    # Parse and normalize date
    clean_df['Date'] = pd.to_datetime(clean_df['Date']).dt.strftime('%Y-%m-%d')

    save_results(clean_df, quarantined_df, 'holidays', reports)
    return clean_df


# ═══════════════════════════════════════════════════════════════════════════
# 6. CROSS-DATASET REFERENTIAL INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════
def cross_dataset_checks(txn_df, outlet_df, coords_df, season_df):
    """Run referential integrity checks across datasets."""
    print("\n" + "▓" * 60)
    print("  CROSS-DATASET REFERENTIAL INTEGRITY")
    print("▓" * 60)

    all_quarantined = []

    # Transactions → Outlet Master
    txn_df, q1, r1 = check_referential_integrity(
        txn_df, 'Outlet_ID', outlet_df, 'Outlet_ID',
        check_name='txn→outlet_master_ref_check'
    )
    if len(q1) > 0:
        all_quarantined.append(q1)
    print(f"  {'⚠️' if len(q1)>0 else '✅'} Txn→Outlet: {len(q1):,} orphans")

    # Transactions → Outlet Coordinates
    txn_df, q2, r2 = check_referential_integrity(
        txn_df, 'Outlet_ID', coords_df, 'Outlet_ID',
        check_name='txn→outlet_coords_ref_check'
    )
    if len(q2) > 0:
        all_quarantined.append(q2)
    print(f"  {'⚠️' if len(q2)>0 else '✅'} Txn→Coords: {len(q2):,} orphans")

    # Transactions → Distributor Seasonality (Distributor_ID)
    txn_df, q3, r3 = check_referential_integrity(
        txn_df, 'Distributor_ID', season_df, 'Distributor_ID',
        check_name='txn→seasonality_ref_check'
    )
    if len(q3) > 0:
        all_quarantined.append(q3)
    print(f"  {'⚠️' if len(q3)>0 else '✅'} Txn→Seasonality: {len(q3):,} orphans")

    if all_quarantined:
        q_all = pd.concat(all_quarantined, ignore_index=True)
        q_path = os.path.join(QUARANTINE_DIR, 'cross_dataset_quarantined.csv')
        q_all.to_csv(q_path, index=False)
        print(f"  🔒 Cross-dataset quarantined: {q_path} ({len(q_all):,} rows)")

    # Save the final cleaned transactions after ref integrity
    txn_path = os.path.join(SILVER_DIR, 'transactions_clean.csv')
    txn_df.to_csv(txn_path, index=False)
    print(f"  💾 Final transactions saved: {txn_path} ({len(txn_df):,} rows)")

    return txn_df


# ═══════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("\n" + "█" * 60)
    print("  SILVER LAYER - DATA CLEANING PIPELINE")
    print("  Team: CodeStormers | Data Storm 7.0")
    print("█" * 60)

    # Clean each dataset
    txn_df    = clean_transactions()
    outlet_df = clean_outlet_master()
    coords_df = clean_outlet_coordinates()
    season_df = clean_seasonality()
    holiday_df = clean_holidays()

    # Cross-dataset referential integrity
    txn_df = cross_dataset_checks(txn_df, outlet_df, coords_df, season_df)

    print("\n" + "█" * 60)
    print("  ✅ SILVER LAYER COMPLETE")
    print("█" * 60)
