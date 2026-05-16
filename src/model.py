"""
05_latent_potential_model.py
============================
Latent Potential Estimation Model
Predicts the Maximum Monthly Volume Potential (in liters) for January 2026
for each of the 20,000 retail outlets.

Methodology (multi-method ensemble):
  1. Quantile Uncapping     — use P95 of historical monthly volume as base potential
  2. Peer Benchmarking      — outlets in same cluster get lifted to peer frontier
  3. Constraint Detection   — detect constrained outlets via low CV, apply uplift
  4. Seasonality Adjustment — scale to January 2026 seasonality

The final potential is:
  Potential(i) = max(method1, method2, method3) × seasonality_factor
"""

import pandas as pd
import numpy as np
import os
import sys
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *


def load_gold_data():
    """Load the model-ready dataset from Gold layer."""
    path = os.path.join(GOLD_DIR, MODEL_READY_FILE)
    if not os.path.exists(path):
        print(f"  [ERROR] Gold layer data not found: {path}")
        print("  Run 04_gold_feature_engineering.py first!")
        sys.exit(1)

    df = pd.read_csv(path)
    print(f"  Loaded gold data: {len(df):,} outlets × {df.shape[1]} columns")
    return df


def method1_quantile_uncapping(df):
    """
    Method 1: Quantile-Based Uncapping
    Use P95 of historical monthly volume as the base potential estimate.
    For outlets with very few months, use max instead.
    """
    print("\n  [METHOD 1] Quantile Uncapping (P95)...")

    potential = df[['Outlet_ID']].copy()

    # Use P95 for outlets with enough history, max for sparse outlets
    potential['m1_potential'] = np.where(
        df['txn_months_active'] >= 6,
        df['txn_p95_monthly_volume'],
        df['txn_max_monthly_volume']
    )

    # Floor: at least the recent 6-month average
    potential['m1_potential'] = np.maximum(
        potential['m1_potential'],
        df['txn_recent_6m_avg']
    )

    # Apply growth adjustment: if outlet is growing, potential should reflect trend
    growth_adj = np.clip(df['txn_growth_ratio'], 0.8, 2.0)
    potential['m1_potential'] = np.where(
        df['txn_growth_ratio'] > 1.1,
        potential['m1_potential'] * np.sqrt(growth_adj),  # moderate uplift
        potential['m1_potential']
    )

    print(f"    Mean: {potential['m1_potential'].mean():.1f}L | Median: {potential['m1_potential'].median():.1f}L")
    return potential


def method2_peer_benchmarking(df):
    """
    Method 2: Peer Benchmarking
    Cluster outlets by features, then lift underperformers to the peer group's P75.
    """
    print("\n  [METHOD 2] Peer Benchmarking...")

    # Features for clustering
    cluster_features = [
        'outlet_size_encoded', 'outlet_cooler_count',
        'geo_outlet_density_2km', 'txn_avg_sku_diversity',
    ]

    # Add POI total if available
    if 'poi_total' in df.columns:
        cluster_features.append('poi_total')

    # Add outlet type columns
    type_cols = [c for c in df.columns if c.startswith('outlet_type_')]
    cluster_features.extend(type_cols)

    # Prepare clustering data
    X = df[cluster_features].fillna(0).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Determine number of clusters (approx 20 groups for 20K outlets = ~1000 per cluster)
    n_clusters = 20
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
    df_temp = df.copy()
    df_temp['cluster'] = kmeans.fit_predict(X_scaled)

    # For each cluster, compute P75 of monthly volume (the "frontier" benchmark)
    cluster_p75 = df_temp.groupby('cluster')['txn_p95_monthly_volume'].quantile(0.75).to_dict()
    cluster_p90 = df_temp.groupby('cluster')['txn_p95_monthly_volume'].quantile(0.90).to_dict()

    potential = df[['Outlet_ID']].copy()
    potential['m2_potential'] = df_temp['cluster'].map(cluster_p75)

    # For each outlet, potential is max of own P95 and peer group P75
    potential['m2_potential'] = np.maximum(
        potential['m2_potential'],
        df['txn_p95_monthly_volume']
    )

    # For top performers already above P75, use cluster P90 as their ceiling
    above_p75 = df['txn_p95_monthly_volume'] > df_temp['cluster'].map(cluster_p75)
    potential.loc[above_p75, 'm2_potential'] = np.maximum(
        df.loc[above_p75, 'txn_p95_monthly_volume'],
        df_temp.loc[above_p75, 'cluster'].map(cluster_p90)
    )

    print(f"    Clusters: {n_clusters}")
    print(f"    Mean: {potential['m2_potential'].mean():.1f}L | Median: {potential['m2_potential'].median():.1f}L")
    return potential


def method3_constraint_detection(df):
    """
    Method 3: Constraint Detection & Uplift
    Identify constrained outlets (low CV, flat volumes) and apply uplift.
    """
    print("\n  [METHOD 3] Constraint Detection & Uplift...")

    potential = df[['Outlet_ID']].copy()

    # Detect constraint signals
    # 1. Low coefficient of variation (volumes barely change → hitting a cap)
    cv_threshold = 0.3  # below this = likely constrained
    is_low_cv = df['txn_cv_monthly_volume'] < cv_threshold

    # 2. Volume consistently near maximum (ratio of P95/max close to 1)
    p95_max_ratio = np.where(
        df['txn_max_monthly_volume'] > 0,
        df['txn_p95_monthly_volume'] / df['txn_max_monthly_volume'],
        0
    )
    is_flat_top = p95_max_ratio > 0.9

    # 3. Enough history to make the judgment
    has_history = df['txn_months_active'] >= 6

    # Combine signals
    is_constrained = (is_low_cv | is_flat_top) & has_history
    n_constrained = is_constrained.sum()

    # Calculate uplift factor based on constraint severity
    # Use outlet size and cooler count as capacity proxy
    size_factor = df['outlet_size_encoded'] / 2.5  # normalized around 1.0
    cooler_factor = (df['outlet_cooler_count'] + 1) / 3.0  # +1 to avoid zero

    # Uplift: constrained outlets get 15-40% boost depending on their characteristics
    uplift = 1.0 + (size_factor * cooler_factor * 0.15)
    uplift = np.clip(uplift, 1.05, 1.50)  # cap uplift at 50%

    potential['m3_potential'] = np.where(
        is_constrained,
        df['txn_p95_monthly_volume'] * uplift,
        df['txn_p95_monthly_volume']
    )

    # Floor: never below the observed max
    potential['m3_potential'] = np.maximum(
        potential['m3_potential'],
        df['txn_max_monthly_volume']
    )

    print(f"    Constrained outlets detected: {n_constrained:,} ({n_constrained/len(df)*100:.1f}%)")
    print(f"    Mean uplift (constrained): {uplift[is_constrained].mean():.2f}x" if n_constrained > 0 else "    No constrained outlets")
    print(f"    Mean: {potential['m3_potential'].mean():.1f}L | Median: {potential['m3_potential'].median():.1f}L")
    return potential, is_constrained


def apply_seasonality_adjustment(potential, df):
    """Adjust raw potential to January 2026 seasonality."""
    print("\n  Applying January 2026 seasonality adjustment...")

    if 'dist_seasonality_jan_encoded' in df.columns:
        factor = df['dist_seasonality_jan_encoded'].values
    else:
        factor = np.ones(len(df))

    adjusted = potential * factor
    print(f"    Seasonality factors used: {pd.Series(factor).value_counts().to_dict()}")
    return adjusted


def ensemble_predictions(df, m1, m2, m3, is_constrained):
    """
    Combine the three methods into a final prediction.
    Strategy: weighted combination favoring the most defensible method.
    """
    print("\n  Building ensemble prediction...")

    result = df[['Outlet_ID']].copy()

    # Weights: prioritize quantile (most defensible) and peer benchmark
    # For constrained outlets, weight the constraint method higher
    w1, w2, w3 = 0.40, 0.35, 0.25  # default weights

    result['raw_potential'] = (
        w1 * m1['m1_potential'].values +
        w2 * m2['m2_potential'].values +
        w3 * m3['m3_potential'].values
    )

    # For constrained outlets, give more weight to the uplift method
    constrained_potential = (
        0.30 * m1['m1_potential'].values +
        0.25 * m2['m2_potential'].values +
        0.45 * m3['m3_potential'].values
    )
    result.loc[is_constrained, 'raw_potential'] = constrained_potential[is_constrained]

    # Apply seasonality
    result['Maximum_Monthly_Liters'] = apply_seasonality_adjustment(
        result['raw_potential'], df
    )

    # Final floor: potential should never be below the historical average
    result['Maximum_Monthly_Liters'] = np.maximum(
        result['Maximum_Monthly_Liters'],
        df['txn_avg_monthly_volume']
    )

    # Round to 2 decimal places
    result['Maximum_Monthly_Liters'] = result['Maximum_Monthly_Liters'].round(2)

    return result


def validate_predictions(result, df):
    """Sanity check the predictions."""
    print("\n  Validating predictions...")

    preds = result['Maximum_Monthly_Liters']

    print(f"    Total outlets: {len(result):,}")
    print(f"    Predictions range: {preds.min():.1f}L - {preds.max():.1f}L")
    print(f"    Mean: {preds.mean():.1f}L | Median: {preds.median():.1f}L")
    print(f"    Std: {preds.std():.1f}L")
    print(f"    Zero or negative: {(preds <= 0).sum()}")

    # Check that potential >= historical average for most outlets
    above_avg = (preds >= df['txn_avg_monthly_volume']).mean()
    print(f"    Potential >= historical avg: {above_avg*100:.1f}%")

    # Check that potential >= historical max for most outlets
    above_max = (preds >= df['txn_max_monthly_volume']).mean()
    print(f"    Potential >= historical max: {above_max*100:.1f}%")

    # Size ordering check (Large outlets should average higher than Small)
    if 'outlet_size_encoded' in df.columns:
        size_means = df.copy()
        size_means['pred'] = preds
        size_order = size_means.groupby('outlet_size_encoded')['pred'].mean()
        print(f"    Avg potential by size: {size_order.to_dict()}")

    # Distribution
    print(f"\n    Percentiles:")
    for p in [5, 10, 25, 50, 75, 90, 95, 99]:
        print(f"      P{p}: {preds.quantile(p/100):.1f}L")


def main():
    print("\n" + "#" * 60)
    print("#" + " " * 10 + "LATENT POTENTIAL MODEL" + " " * 27 + "#")
    print("#" * 60)

    # Load Gold data
    df = load_gold_data()

    # Run the three estimation methods
    m1 = method1_quantile_uncapping(df)
    m2 = method2_peer_benchmarking(df)
    m3, is_constrained = method3_constraint_detection(df)

    # Ensemble
    result = ensemble_predictions(df, m1, m2, m3, is_constrained)

    # Validate
    validate_predictions(result, df)

    # Save final predictions
    output = result[['Outlet_ID', 'Maximum_Monthly_Liters']].copy()
    output_path = os.path.join(OUTPUT_DIR, PREDICTIONS_FILE)
    output.to_csv(output_path, index=False)

    print(f"\n  Predictions saved to: {output_path}")
    print(f"  Shape: {output.shape}")
    print(f"\n  Preview (first 10):")
    print(output.head(10).to_string(index=False))

    # Also save detailed results for analysis
    detail = result.copy()
    detail['m1_quantile'] = m1['m1_potential']
    detail['m2_peer'] = m2['m2_potential']
    detail['m3_uplift'] = m3['m3_potential']
    detail['is_constrained'] = is_constrained
    detail_path = os.path.join(GOLD_DIR, "potential_analysis.csv")
    detail.to_csv(detail_path, index=False)
    print(f"\n  Detailed analysis saved to: {detail_path}")

    print("\n" + "#" * 60)
    print("#" + " " * 12 + "PIPELINE COMPLETE" + " " * 29 + "#")
    print("#" * 60)


if __name__ == "__main__":
    main()
