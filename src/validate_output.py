"""
validate_output.py
===================
Strict CI-gate validation for the final predictions CSV.
Run this as the last step in the pipeline to assert correctness.
If any assertion fails, the script exits with code 1.
"""

import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *


def main():
    print("\n" + "=" * 60)
    print("  VALIDATION KILL-SWITCH: Final Output Audit")
    print("=" * 60)

    pred_path = os.path.join(OUTPUT_DIR, PREDICTIONS_FILE)
    assert os.path.exists(pred_path), f"FAIL: Predictions file not found at {pred_path}"
    preds = pd.read_csv(pred_path)

    # --- 1. Row count ---
    n = len(preds)
    print(f"  [CHECK 1] Row count: {n}")
    assert n == 20000, f"FAIL: Expected 20,000 rows, got {n}"
    print(f"    PASS (exactly 20,000 outlets)")

    # --- 2. Required columns ---
    required = {'Outlet_ID', 'Maximum_Monthly_Liters'}
    assert required.issubset(set(preds.columns)), f"FAIL: Missing columns: {required - set(preds.columns)}"
    print(f"  [CHECK 2] Columns: {list(preds.columns)}")
    print(f"    PASS")

    # --- 3. No duplicate Outlet_IDs ---
    n_dup = preds['Outlet_ID'].duplicated().sum()
    print(f"  [CHECK 3] Duplicate Outlet_IDs: {n_dup}")
    assert n_dup == 0, f"FAIL: {n_dup} duplicate Outlet_IDs found"
    print(f"    PASS")

    # --- 4. No nulls ---
    null_count = preds.isnull().sum().sum()
    print(f"  [CHECK 4] Null values: {null_count}")
    assert null_count == 0, f"FAIL: {null_count} null values found"
    print(f"    PASS")

    # --- 5. No zero or negative predictions ---
    min_val = preds['Maximum_Monthly_Liters'].min()
    print(f"  [CHECK 5] Minimum prediction: {min_val:.2f}L")
    assert min_val > 0, f"FAIL: Minimum prediction is {min_val} (must be > 0)"
    print(f"    PASS")

    # --- 6. Reasonable range ---
    max_val = preds['Maximum_Monthly_Liters'].max()
    mean_val = preds['Maximum_Monthly_Liters'].mean()
    print(f"  [CHECK 6] Range: {min_val:.1f}L - {max_val:.1f}L (mean: {mean_val:.1f}L)")
    assert max_val < 50000, f"FAIL: Max prediction {max_val} is unreasonably high"
    assert mean_val > 50, f"FAIL: Mean prediction {mean_val} is unreasonably low"
    print(f"    PASS")

    # --- 7. Outlet ID format ---
    bad_ids = preds[~preds['Outlet_ID'].str.match(r'^OUT_\d{5}$')]
    print(f"  [CHECK 7] Invalid Outlet_ID format: {len(bad_ids)}")
    assert len(bad_ids) == 0, f"FAIL: {len(bad_ids)} outlets have invalid ID format"
    print(f"    PASS")

    # --- 8. Cross-check against Gold layer if available ---
    gold_path = os.path.join(GOLD_DIR, MODEL_READY_FILE)
    if os.path.exists(gold_path):
        gold = pd.read_csv(gold_path)
        merged = preds.merge(gold[['Outlet_ID', 'txn_avg_monthly_volume']], on='Outlet_ID', how='inner')
        above_avg = (merged['Maximum_Monthly_Liters'] >= merged['txn_avg_monthly_volume']).mean()
        print(f"  [CHECK 8] Prediction >= historical avg: {above_avg*100:.1f}%")
        assert above_avg >= 0.95, f"FAIL: Only {above_avg*100:.1f}% of predictions exceed historical average"
        print(f"    PASS")

    print("\n" + "=" * 60)
    print("  ALL CHECKS PASSED. Output is submission-ready.")
    print("=" * 60)


if __name__ == "__main__":
    main()
