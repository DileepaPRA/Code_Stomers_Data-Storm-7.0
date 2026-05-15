"""
=============================================================================
REUSABLE DATA QUALITY CHECK LIBRARY
=============================================================================
Team: CodeStormers | Data Storm 7.0
Purpose: Parameterizable, reusable DQ functions per Lakehouse spec.
         Each function returns (clean_df, quarantined_df, report_dict).
=============================================================================
"""

import pandas as pd
import numpy as np
import re
from typing import Tuple, Dict, List, Optional


def check_duplicates(
    df: pd.DataFrame,
    primary_key_cols: List[str],
    keep: str = 'first',
    check_name: str = 'duplicate_check'
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Detect and quarantine duplicate records based on primary key columns.
    
    Parameters
    ----------
    df : pd.DataFrame - Input dataframe
    primary_key_cols : list - Columns forming the primary key
    keep : str - Which duplicate to keep ('first', 'last', False)
    check_name : str - Name for audit trail
    
    Returns
    -------
    (clean_df, quarantined_df, report)
    """
    dup_mask = df.duplicated(subset=primary_key_cols, keep=keep)
    quarantined = df[dup_mask].copy()
    quarantined['_quarantine_reason'] = f'{check_name}: duplicate on {primary_key_cols}'
    clean = df[~dup_mask].copy()
    
    report = {
        'check': check_name,
        'total_records': len(df),
        'duplicates_found': int(dup_mask.sum()),
        'records_retained': len(clean),
        'key_columns': primary_key_cols
    }
    return clean, quarantined, report


def check_nulls(
    df: pd.DataFrame,
    mandatory_cols: List[str],
    check_name: str = 'null_check'
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Flag records where mandatory fields contain null or empty values.
    
    Parameters
    ----------
    df : pd.DataFrame - Input dataframe
    mandatory_cols : list - Columns that must not be null/empty
    check_name : str - Name for audit trail
    
    Returns
    -------
    (clean_df, quarantined_df, report)
    """
    null_mask = pd.Series(False, index=df.index)
    col_null_counts = {}
    
    for col in mandatory_cols:
        if col in df.columns:
            col_null = df[col].isna() | (df[col].astype(str).str.strip() == '')
            col_null_counts[col] = int(col_null.sum())
            null_mask = null_mask | col_null
    
    quarantined = df[null_mask].copy()
    quarantined['_quarantine_reason'] = f'{check_name}: null/empty in mandatory fields'
    clean = df[~null_mask].copy()
    
    report = {
        'check': check_name,
        'total_records': len(df),
        'null_records_found': int(null_mask.sum()),
        'records_retained': len(clean),
        'null_counts_per_column': col_null_counts
    }
    return clean, quarantined, report


def check_referential_integrity(
    df: pd.DataFrame,
    fk_col: str,
    reference_df: pd.DataFrame,
    ref_pk_col: str,
    check_name: str = 'referential_integrity_check'
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Validate that foreign key values exist in a reference dataset.
    
    Parameters
    ----------
    df : pd.DataFrame - Dataframe with foreign key
    fk_col : str - Foreign key column name
    reference_df : pd.DataFrame - Reference dataframe
    ref_pk_col : str - Primary key column in reference
    check_name : str - Name for audit trail
    
    Returns
    -------
    (clean_df, quarantined_df, report)
    """
    valid_keys = set(reference_df[ref_pk_col].dropna().unique())
    invalid_mask = ~df[fk_col].isin(valid_keys)
    
    quarantined = df[invalid_mask].copy()
    quarantined['_quarantine_reason'] = (
        f'{check_name}: {fk_col} not found in reference {ref_pk_col}'
    )
    clean = df[~invalid_mask].copy()
    
    orphan_values = df.loc[invalid_mask, fk_col].unique().tolist()
    
    report = {
        'check': check_name,
        'total_records': len(df),
        'orphan_records': int(invalid_mask.sum()),
        'records_retained': len(clean),
        'orphan_key_values_sample': orphan_values[:20]
    }
    return clean, quarantined, report


def check_value_range(
    df: pd.DataFrame,
    col: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    check_name: str = 'value_range_check'
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Assert that numeric fields fall within an expected min/max boundary.
    
    Parameters
    ----------
    df : pd.DataFrame - Input dataframe
    col : str - Numeric column to check
    min_val : float or None - Minimum allowed value (inclusive)
    max_val : float or None - Maximum allowed value (inclusive)
    check_name : str - Name for audit trail
    
    Returns
    -------
    (clean_df, quarantined_df, report)
    """
    violation_mask = pd.Series(False, index=df.index)
    
    numeric_series = pd.to_numeric(df[col], errors='coerce')
    non_numeric_mask = numeric_series.isna() & df[col].notna()
    violation_mask = violation_mask | non_numeric_mask
    
    if min_val is not None:
        violation_mask = violation_mask | (numeric_series < min_val)
    if max_val is not None:
        violation_mask = violation_mask | (numeric_series > max_val)
    
    quarantined = df[violation_mask].copy()
    quarantined['_quarantine_reason'] = (
        f'{check_name}: {col} outside range [{min_val}, {max_val}]'
    )
    clean = df[~violation_mask].copy()
    
    report = {
        'check': check_name,
        'total_records': len(df),
        'violations_found': int(violation_mask.sum()),
        'records_retained': len(clean),
        'column': col,
        'range': [min_val, max_val]
    }
    return clean, quarantined, report


def check_format(
    df: pd.DataFrame,
    col: str,
    expected_type: str = 'date',
    pattern: Optional[str] = None,
    check_name: str = 'format_check'
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Validate that fields conform to expected data type or pattern.
    
    Parameters
    ----------
    df : pd.DataFrame - Input dataframe
    col : str - Column to validate
    expected_type : str - 'date', 'id', 'numeric', 'regex'
    pattern : str - Regex pattern (used when expected_type='regex' or 'id')
    check_name : str - Name for audit trail
    
    Returns
    -------
    (clean_df, quarantined_df, report)
    """
    violation_mask = pd.Series(False, index=df.index)
    
    if expected_type == 'date':
        parsed = pd.to_datetime(df[col], errors='coerce')
        violation_mask = parsed.isna() & df[col].notna()
    
    elif expected_type == 'numeric':
        parsed = pd.to_numeric(df[col], errors='coerce')
        violation_mask = parsed.isna() & df[col].notna()
    
    elif expected_type == 'id' and pattern:
        violation_mask = ~df[col].astype(str).str.match(pattern, na=False)
    
    elif expected_type == 'regex' and pattern:
        violation_mask = ~df[col].astype(str).str.match(pattern, na=False)
    
    quarantined = df[violation_mask].copy()
    quarantined['_quarantine_reason'] = (
        f'{check_name}: {col} failed {expected_type} format validation'
    )
    clean = df[~violation_mask].copy()
    
    report = {
        'check': check_name,
        'total_records': len(df),
        'violations_found': int(violation_mask.sum()),
        'records_retained': len(clean),
        'column': col,
        'expected_type': expected_type
    }
    return clean, quarantined, report


def check_outliers_iqr(
    df: pd.DataFrame,
    col: str,
    iqr_factor: float = 3.0,
    check_name: str = 'outlier_check'
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Detect extreme statistical outliers using the IQR method.
    Uses a wide factor (3.0) to only catch severe anomalies.
    
    Parameters
    ----------
    df : pd.DataFrame - Input dataframe
    col : str - Numeric column to check
    iqr_factor : float - IQR multiplier (default 3.0 = very conservative)
    check_name : str - Name for audit trail
    
    Returns
    -------
    (clean_df, quarantined_df, report)
    """
    numeric_vals = pd.to_numeric(df[col], errors='coerce')
    q1 = numeric_vals.quantile(0.25)
    q3 = numeric_vals.quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - iqr_factor * iqr
    upper_bound = q3 + iqr_factor * iqr
    
    outlier_mask = (numeric_vals < lower_bound) | (numeric_vals > upper_bound)
    
    quarantined = df[outlier_mask].copy()
    quarantined['_quarantine_reason'] = (
        f'{check_name}: {col} is an extreme outlier (IQR x{iqr_factor})'
    )
    clean = df[~outlier_mask].copy()
    
    report = {
        'check': check_name,
        'total_records': len(df),
        'outliers_found': int(outlier_mask.sum()),
        'records_retained': len(clean),
        'bounds': {'lower': float(lower_bound), 'upper': float(upper_bound)},
        'iqr_factor': iqr_factor
    }
    return clean, quarantined, report


def run_quality_pipeline(
    df: pd.DataFrame,
    checks: List[Dict],
    dataset_name: str = 'unknown'
) -> Tuple[pd.DataFrame, pd.DataFrame, List[Dict]]:
    """
    Run a sequence of quality checks on a dataframe.
    
    Parameters
    ----------
    df : pd.DataFrame - Input dataframe
    checks : list of dicts - Each dict has 'function' and 'params' keys
    dataset_name : str - Name of the dataset for reporting
    
    Returns
    -------
    (final_clean_df, all_quarantined_df, list_of_reports)
    """
    all_quarantined = []
    all_reports = []
    current_df = df.copy()
    
    print(f"\n{'='*60}")
    print(f"  DATA QUALITY PIPELINE: {dataset_name}")
    print(f"  Starting records: {len(current_df):,}")
    print(f"{'='*60}")
    
    for check_spec in checks:
        func = check_spec['function']
        params = check_spec.get('params', {})
        
        current_df, quarantined, report = func(current_df, **params)
        report['dataset'] = dataset_name
        all_reports.append(report)
        
        if len(quarantined) > 0:
            all_quarantined.append(quarantined)
        
        check_label = report.get('check', func.__name__)
        violations = len(quarantined)
        status = "⚠️" if violations > 0 else "✅"
        print(f"  {status} {check_label}: {violations:,} quarantined → {len(current_df):,} remaining")
    
    all_quarantined_df = pd.concat(all_quarantined, ignore_index=True) if all_quarantined else pd.DataFrame()
    
    print(f"\n  📊 Final: {len(current_df):,} clean | {len(all_quarantined_df):,} quarantined")
    print(f"{'='*60}\n")
    
    return current_df, all_quarantined_df, all_reports
