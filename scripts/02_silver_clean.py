"""
02_silver_clean.py
==================
Silver Layer: Data Cleaning & Quarantine
Applies DQ checks to all Bronze-layer datasets using the reusable dq_checks framework.
Outputs cleaned CSVs to silver/ and quarantined records to silver/rejected_records/.

Anomalies handled:
  - Outlet type typos (Bakry→Bakery, Grocry→Grocery, ' Eatery'→Eatery)
  - Outlet size case issues (small→Small) and null imputation
  - Coordinate swaps (lat/lon swapped when lat > 50)
  - Zero coordinates (0,0) quarantined
  - Negative/zero volume transactions quarantined (credit notes/ghost entries)
  - Extreme volume outliers flagged
  - Referential integrity across datasets
"""

import pandas as pd
import numpy as np
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import *
from dq_checks import *


def clean_outlet_master():
    """Clean outlet_master.csv: fix typos, standardize cases, handle nulls."""
    print("\n" + "=" * 60)
    print("  SILVER: Cleaning outlet_master.csv")
    print("=" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, OUTLET_MASTER_FILE))
    print(f"  Input: {len(df):,} records")

    # --- Pre-cleaning: Fix known typos & standardize BEFORE DQ checks ---
    # Whitespace trim FIRST (so ' Eatery ' becomes 'Eatery')
    df, _ = trim_whitespace(df, ['Outlet_ID', 'Outlet_Size', 'Outlet_Type'])

    # Fix outlet type typos AFTER trimming
    typo_map = {'Bakry': 'Bakery', 'Grocry': 'Grocery', 'Eatery': 'Eatery'}  # 'Eatery' catches trimmed ' Eatery'
    for wrong, correct in typo_map.items():
        mask = df['Outlet_Type'] == wrong
        n = mask.sum()
        if n > 0 and wrong != correct:
            df.loc[mask, 'Outlet_Type'] = correct
            print(f"  [FIX] Outlet_Type '{wrong}' -> '{correct}': {n} records")

    # Standardize outlet size case (small -> Small)
    size_mask = df['Outlet_Size'].notna()
    df.loc[size_mask, 'Outlet_Size'] = df.loc[size_mask, 'Outlet_Size'].str.strip().str.title()
    # Fix "Extra large" -> "Extra Large"
    df['Outlet_Size'] = df['Outlet_Size'].replace({'Extra large': 'Extra Large'})

    # --- DQ Pipeline ---
    checks = [
        lambda d: check_duplicates(d, ['Outlet_ID']),
        lambda d: check_format(d, 'Outlet_ID', r'OUT_\d{5}'),
        lambda d: check_value_range(d, 'Cooler_Count', min_val=0, max_val=20),
    ]

    clean, rejected = run_dq_pipeline(df, checks, "outlet_master")

    # --- Handle null Outlet_Size: impute with mode of same Outlet_Type ---
    null_size = clean['Outlet_Size'].isnull()
    if null_size.sum() > 0:
        print(f"  [IMPUTE] Null Outlet_Size: {null_size.sum()} records")
        for otype in clean['Outlet_Type'].unique():
            mask = null_size & (clean['Outlet_Type'] == otype)
            if mask.sum() > 0:
                mode_val = clean.loc[clean['Outlet_Type'] == otype, 'Outlet_Size'].mode()
                if len(mode_val) > 0:
                    clean.loc[mask, 'Outlet_Size'] = mode_val.iloc[0]
                    print(f"    {otype}: filled {mask.sum()} nulls with '{mode_val.iloc[0]}'")

    # Save
    clean.to_csv(os.path.join(SILVER_DIR, OUTLET_MASTER_CLEAN), index=False)
    if len(rejected) > 0:
        rejected.to_csv(os.path.join(REJECTED_DIR, OUTLET_MASTER_REJECTED), index=False)

    print(f"  Saved: {len(clean):,} clean | {len(rejected):,} rejected")
    return clean


def clean_outlet_coordinates(valid_outlet_ids):
    """Clean outlet_coordinates.csv: fix swapped lat/lon, quarantine zeros."""
    print("\n" + "=" * 60)
    print("  SILVER: Cleaning outlet_coordinates.csv")
    print("=" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, OUTLET_COORDS_FILE))
    print(f"  Input: {len(df):,} records")

    # --- Pre-cleaning: Fix swapped coordinates ---
    # If latitude > 50, it's clearly swapped with longitude (Sri Lanka lat is 5.9-9.9)
    swapped = df['Latitude'] > 50
    n_swapped = swapped.sum()
    if n_swapped > 0:
        df.loc[swapped, ['Latitude', 'Longitude']] = df.loc[swapped, ['Longitude', 'Latitude']].values
        print(f"  [FIX] Swapped lat/lon for {n_swapped} records (lat was > 50)")

    # --- DQ Pipeline ---
    checks = [
        lambda d: check_duplicates(d, ['Outlet_ID']),
        lambda d: check_referential_integrity(d, 'Outlet_ID', valid_outlet_ids),
        # Quarantine zero coordinates (can't be fixed)
        lambda d: check_consistency(
            d,
            lambda x: ~((x['Latitude'] == 0) & (x['Longitude'] == 0)),
            'Zero coordinates (0,0)'
        ),
        # Validate Sri Lanka bounds after swap fix
        lambda d: check_value_range(d, 'Latitude', min_val=SRI_LANKA_LAT_MIN, max_val=SRI_LANKA_LAT_MAX),
        lambda d: check_value_range(d, 'Longitude', min_val=SRI_LANKA_LON_MIN, max_val=SRI_LANKA_LON_MAX),
    ]

    clean, rejected = run_dq_pipeline(df, checks, "outlet_coordinates")

    # Save
    clean.to_csv(os.path.join(SILVER_DIR, OUTLET_COORDS_CLEAN), index=False)
    if len(rejected) > 0:
        rejected.to_csv(os.path.join(REJECTED_DIR, OUTLET_COORDS_REJECTED), index=False)

    print(f"  Saved: {len(clean):,} clean | {len(rejected):,} rejected")
    return clean


def clean_transactions(valid_outlet_ids, valid_distributor_ids):
    """Clean transactions: remove negatives, zeros, outliers, validate FKs."""
    print("\n" + "=" * 60)
    print("  SILVER: Cleaning transactions_history_final.csv")
    print("=" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, TRANSACTIONS_FILE))
    print(f"  Input: {len(df):,} records")

    # Whitespace trim on string columns
    df, _ = trim_whitespace(df, ['Outlet_ID', 'Distributor_ID', 'SKU_ID'])

    # --- DQ Pipeline ---
    checks = [
        # Null check on all columns
        lambda d: check_nulls(d, ['Outlet_ID', 'Year', 'Month', 'Distributor_ID', 'SKU_ID', 'Volume_Liters', 'Total_Bill_Value']),
        # Format checks
        lambda d: check_format(d, 'Outlet_ID', r'OUT_\d{5}'),
        lambda d: check_format(d, 'SKU_ID', r'SKU_\d{2}'),
        # Referential integrity
        lambda d: check_referential_integrity(d, 'Outlet_ID', valid_outlet_ids),
        lambda d: check_referential_integrity(d, 'Distributor_ID', valid_distributor_ids),
        # Value ranges
        lambda d: check_value_range(d, 'Year', min_val=2023, max_val=2025),
        lambda d: check_value_range(d, 'Month', min_val=1, max_val=12),
        # Remove negative volumes (credit notes / returns)
        lambda d: check_value_range(d, 'Volume_Liters', min_val=0),
        # Remove zero volumes (ghost entries)
        lambda d: check_consistency(d, lambda x: x['Volume_Liters'] > 0, 'Zero volume (ghost entry)'),
        # NOTE: We intentionally DO NOT apply IQR outlier removal here.
        # High-volume transactions are critical signals for latent potential estimation.
        # They represent months when constraints were least binding.
    ]

    clean, rejected = run_dq_pipeline(df, checks, "transactions")

    # Save
    clean.to_csv(os.path.join(SILVER_DIR, TRANSACTIONS_CLEAN), index=False)
    if len(rejected) > 0:
        rejected.to_csv(os.path.join(REJECTED_DIR, TRANSACTIONS_REJECTED), index=False)

    print(f"  Saved: {len(clean):,} clean | {len(rejected):,} rejected")
    return clean


def clean_seasonality():
    """Clean distributor_seasonality_details.csv."""
    print("\n" + "=" * 60)
    print("  SILVER: Cleaning distributor_seasonality_details.csv")
    print("=" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, SEASONALITY_FILE))
    print(f"  Input: {len(df):,} records")

    df, _ = trim_whitespace(df, ['Distributor_ID', 'Seasonality_Index'])

    checks = [
        lambda d: check_nulls(d, ['Distributor_ID', 'Year', 'Month', 'Seasonality_Index']),
        lambda d: check_referential_integrity(d, 'Distributor_ID', VALID_DISTRIBUTORS),
        lambda d: check_value_range(d, 'Year', min_val=2023, max_val=2026),
        lambda d: check_value_range(d, 'Month', min_val=1, max_val=12),
    ]

    clean, rejected = run_dq_pipeline(df, checks, "seasonality")

    clean.to_csv(os.path.join(SILVER_DIR, SEASONALITY_CLEAN), index=False)
    print(f"  Saved: {len(clean):,} clean | {len(rejected):,} rejected")
    return clean


def clean_holidays():
    """Clean holiday_list.csv: parse dates, validate."""
    print("\n" + "=" * 60)
    print("  SILVER: Cleaning holiday_list.csv")
    print("=" * 60)

    df = pd.read_csv(os.path.join(BRONZE_DIR, HOLIDAYS_FILE))
    print(f"  Input: {len(df):,} records")

    # Parse date column
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

    checks = [
        lambda d: check_nulls(d, ['Date', 'Holiday_Name', 'Holiday_Type']),
        lambda d: check_duplicates(d, ['Date', 'Holiday_Name', 'Holiday_Type']),
    ]

    clean, rejected = run_dq_pipeline(df, checks, "holidays")

    clean.to_csv(os.path.join(SILVER_DIR, HOLIDAYS_CLEAN), index=False)
    print(f"  Saved: {len(clean):,} clean | {len(rejected):,} rejected")
    return clean


def main():
    print("\n" + "#" * 60)
    print("#" + " " * 17 + "SILVER LAYER PIPELINE" + " " * 20 + "#")
    print("#" * 60)

    # Step 1: Clean outlet master first (we need valid IDs for other checks)
    outlet_clean = clean_outlet_master()
    valid_outlet_ids = set(outlet_clean['Outlet_ID'].unique())

    # Step 2: Clean coordinates
    coords_clean = clean_outlet_coordinates(valid_outlet_ids)

    # Step 3: Clean transactions (largest dataset)
    txn_clean = clean_transactions(valid_outlet_ids, VALID_DISTRIBUTORS)

    # Step 4: Clean seasonality
    season_clean = clean_seasonality()

    # Step 5: Clean holidays
    holiday_clean = clean_holidays()

    # --- Summary ---
    print("\n" + "#" * 60)
    print("  SILVER LAYER COMPLETE — Summary")
    print("#" * 60)
    print(f"  outlet_master:  {len(outlet_clean):,} clean records")
    print(f"  coordinates:    {len(coords_clean):,} clean records")
    print(f"  transactions:   {len(txn_clean):,} clean records")
    print(f"  seasonality:    {len(season_clean):,} clean records")
    print(f"  holidays:       {len(holiday_clean):,} clean records")

    # Count total rejected
    rej_dir = REJECTED_DIR
    total_rej = 0
    for f in os.listdir(rej_dir):
        if f.endswith('.csv'):
            n = len(pd.read_csv(os.path.join(rej_dir, f)))
            total_rej += n
            print(f"  rejected/{f}: {n:,} records")
    print(f"\n  Total quarantined: {total_rej:,}")
    print("#" * 60)


if __name__ == "__main__":
    main()
