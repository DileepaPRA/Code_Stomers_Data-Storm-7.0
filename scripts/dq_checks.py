"""
dq_checks.py
============
Reusable, parameterizable Data Quality (DQ) check framework.
Every check returns (passed_df, failed_df) where failed_df includes
a 'DQ_Failure_Reason' column documenting why each record was quarantined.

Checks:
  1. Duplicate Check         - configurable composite key
  2. Null Check              - mandatory fields null/empty
  3. Referential Integrity   - FK validation
  4. Value Range Check       - numeric min/max bounds
  5. Format / Type Check     - regex conformance
  6. Outlier Check (IQR)     - statistical outlier detection
  7. Consistency Check       - cross-field logical rules
  8. Whitespace Trim         - leading/trailing whitespace (cleans, doesn't quarantine)
"""

import pandas as pd
import numpy as np
from datetime import datetime


# ---------------------------------------------------------------------------
# 1. DUPLICATE CHECK
# ---------------------------------------------------------------------------
def check_duplicates(df, key_columns, keep='first'):
    """Detect duplicate records based on a configurable primary key."""
    dup_mask = df.duplicated(subset=key_columns, keep=keep)
    failed = df[dup_mask].copy()
    if len(failed) > 0:
        failed['DQ_Failure_Reason'] = f'Duplicate on key: {key_columns}'
    passed = df[~dup_mask].copy()
    print(f"  [DQ] Duplicate Check on {key_columns}: {dup_mask.sum()} duplicates found")
    return passed, failed


# ---------------------------------------------------------------------------
# 2. NULL CHECK
# ---------------------------------------------------------------------------
def check_nulls(df, mandatory_columns):
    """Flag records where mandatory fields contain null or empty string values."""
    null_mask = pd.Series(False, index=df.index)
    for col in mandatory_columns:
        if df[col].dtype == 'object' or str(df[col].dtype) == 'string':
            col_null = df[col].isnull() | (df[col].astype(str).str.strip() == '') | (df[col].astype(str).str.lower() == 'nan')
        else:
            col_null = df[col].isnull()
        null_mask = null_mask | col_null

    failed = df[null_mask].copy()
    if len(failed) > 0:
        reasons = []
        for idx in failed.index:
            bad = [c for c in mandatory_columns
                   if pd.isnull(failed.at[idx, c]) or
                   (isinstance(failed.at[idx, c], str) and failed.at[idx, c].strip() in ('', 'nan'))]
            reasons.append(f'Null/empty in: {bad}')
        failed['DQ_Failure_Reason'] = reasons

    passed = df[~null_mask].copy()
    print(f"  [DQ] Null Check on {mandatory_columns}: {null_mask.sum()} failures")
    return passed, failed


# ---------------------------------------------------------------------------
# 3. REFERENTIAL INTEGRITY CHECK
# ---------------------------------------------------------------------------
def check_referential_integrity(df, fk_column, reference_values):
    """Validate that FK values exist in a reference set."""
    if isinstance(reference_values, pd.DataFrame):
        raise ValueError("Pass a set/list of valid values, not a DataFrame")
    valid_set = set(reference_values)
    invalid_mask = ~df[fk_column].isin(valid_set)
    failed = df[invalid_mask].copy()
    if len(failed) > 0:
        failed['DQ_Failure_Reason'] = f'Referential integrity: invalid {fk_column}'
    passed = df[~invalid_mask].copy()
    print(f"  [DQ] Referential Integrity ({fk_column}): {invalid_mask.sum()} failures")
    return passed, failed


# ---------------------------------------------------------------------------
# 4. VALUE RANGE CHECK
# ---------------------------------------------------------------------------
def check_value_range(df, column, min_val=None, max_val=None):
    """Assert that a numeric field falls within expected [min, max]."""
    out = pd.Series(False, index=df.index)
    if min_val is not None:
        out = out | (df[column] < min_val)
    if max_val is not None:
        out = out | (df[column] > max_val)

    failed = df[out].copy()
    if len(failed) > 0:
        failed['DQ_Failure_Reason'] = f'Range violation: {column} not in [{min_val}, {max_val}]'
    passed = df[~out].copy()
    print(f"  [DQ] Value Range ({column} in [{min_val}, {max_val}]): {out.sum()} failures")
    return passed, failed


# ---------------------------------------------------------------------------
# 5. FORMAT / TYPE CHECK
# ---------------------------------------------------------------------------
def check_format(df, column, pattern):
    """Validate that field values conform to a regex pattern."""
    str_vals = df[column].astype(str)
    match_mask = str_vals.str.fullmatch(pattern, na=False)
    failed = df[~match_mask].copy()
    if len(failed) > 0:
        failed['DQ_Failure_Reason'] = f'Format violation: {column} !~ {pattern}'
    passed = df[match_mask].copy()
    print(f"  [DQ] Format Check ({column}): {(~match_mask).sum()} failures")
    return passed, failed


# ---------------------------------------------------------------------------
# 6. OUTLIER CHECK (IQR)
# ---------------------------------------------------------------------------
def check_outliers_iqr(df, column, factor=3.0):
    """Detect statistical outliers using the IQR method."""
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr

    outlier_mask = (df[column] < lower) | (df[column] > upper)
    failed = df[outlier_mask].copy()
    if len(failed) > 0:
        failed['DQ_Failure_Reason'] = f'IQR outlier: {column} outside [{lower:.2f}, {upper:.2f}]'
    passed = df[~outlier_mask].copy()
    print(f"  [DQ] Outlier IQR ({column}, x{factor}): {outlier_mask.sum()} outliers [{lower:.2f}, {upper:.2f}]")
    return passed, failed


# ---------------------------------------------------------------------------
# 7. CONSISTENCY CHECK
# ---------------------------------------------------------------------------
def check_consistency(df, condition_func, reason_msg):
    """
    Flag records that violate a cross-field logical condition.
    condition_func: callable that takes df and returns a boolean Series (True = valid).
    """
    valid_mask = condition_func(df)
    failed = df[~valid_mask].copy()
    if len(failed) > 0:
        failed['DQ_Failure_Reason'] = f'Consistency: {reason_msg}'
    passed = df[valid_mask].copy()
    print(f"  [DQ] Consistency ({reason_msg}): {(~valid_mask).sum()} failures")
    return passed, failed


# ---------------------------------------------------------------------------
# 8. WHITESPACE TRIM (cleans in-place, doesn't quarantine)
# ---------------------------------------------------------------------------
def trim_whitespace(df, columns):
    """Strip leading/trailing whitespace from string columns. Returns cleaned df."""
    df = df.copy()
    total = 0
    for col in columns:
        if df[col].dtype == 'object' or str(df[col].dtype) == 'string':
            has_ws = df[col].astype(str).str.contains(r'^\s+|\s+$', regex=True, na=False)
            n = has_ws.sum()
            if n > 0:
                df[col] = df[col].astype(str).str.strip()
                total += n
                print(f"  [DQ] Whitespace trim ({col}): {n} records cleaned")
    return df, total


# ---------------------------------------------------------------------------
# PIPELINE RUNNER: chain multiple checks, accumulate rejected records
# ---------------------------------------------------------------------------
def run_dq_pipeline(df, checks, dataset_name="dataset"):
    """
    Run a sequence of DQ checks, collecting all rejected records.

    Parameters
    ----------
    df : pd.DataFrame
    checks : list of callables, each takes df -> (passed, failed)
    dataset_name : str

    Returns
    -------
    (clean_df, all_rejected_df)
    """
    print(f"\n{'='*60}")
    print(f"  DQ Pipeline: {dataset_name}")
    print(f"  Input records: {len(df):,}")
    print(f"{'='*60}")

    all_rejected = []
    current = df.copy()

    for check_fn in checks:
        passed, failed = check_fn(current)
        if len(failed) > 0:
            failed['DQ_Source_Dataset'] = dataset_name
            failed['DQ_Timestamp'] = datetime.now().isoformat()
            all_rejected.append(failed)
        current = passed

    rejected = pd.concat(all_rejected, ignore_index=True) if all_rejected else pd.DataFrame()
    print(f"{'='*60}")
    print(f"  Result: {len(current):,} passed | {len(rejected):,} quarantined")
    print(f"{'='*60}\n")
    return current, rejected
