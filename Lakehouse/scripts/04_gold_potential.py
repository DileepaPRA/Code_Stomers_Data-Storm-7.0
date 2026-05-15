"""
=============================================================================
GOLD LAYER - Feature Engineering & Latent Potential Estimation
=============================================================================
Team: CodeStormers | Data Storm 7.0

METHODOLOGY: Left-Censored Demand Uncapping
=============================================
Historical sales are LEFT-CENSORED: they show min(true_demand, supply_constraint).
We cannot observe the true demand ceiling, only the constrained realization.

Our approach:
1. PEER BENCHMARKING: For each outlet, identify peers (same type, size, 
   distributor region) and compute P90/P95 volume as the "uncapped" reference.
2. SEASONALITY ADJUSTMENT: Apply distributor-specific Jan 2026 seasonality.
3. POI-BASED DEMAND UPLIFT: Outlets near schools/hospitals/transit have higher
   foot traffic → higher latent demand. We model this as a multiplicative uplift.
4. GROWTH TREND: Capture YoY volume trajectory per outlet.
5. CONSTRAINT DETECTION: Identify outlets whose sales are likely supply-constrained
   (consistently flat at a ceiling, low variance) and apply larger uncapping.

Mathematical Framework:
   Potential_i = max(Historical_Peak_i, Peer_P90) 
                 × Seasonality_Jan2026 
                 × (1 + POI_Uplift)
                 × (1 + Growth_Trend)
                 × Constraint_Uncap_Factor
=============================================================================
"""

import pandas as pd
import numpy as np
import os
import sys
import json
from scipy import stats

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.join(os.path.dirname(__file__), '..')
SILVER_DIR = os.path.join(BASE_DIR, 'silver')
GOLD_DIR   = os.path.join(BASE_DIR, 'gold')
os.makedirs(GOLD_DIR, exist_ok=True)


def load_silver_data():
    """Load all cleaned Silver-layer data."""
    txn    = pd.read_csv(os.path.join(SILVER_DIR, 'transactions_clean.csv'))
    outlet = pd.read_csv(os.path.join(SILVER_DIR, 'outlet_master_clean.csv'))
    coords = pd.read_csv(os.path.join(SILVER_DIR, 'outlet_coordinates_clean.csv'))
    season = pd.read_csv(os.path.join(SILVER_DIR, 'seasonality_clean.csv'))
    
    # POI features (Gold layer from scraping)
    poi_path = os.path.join(GOLD_DIR, 'poi_features.csv')
    poi = pd.read_csv(poi_path) if os.path.exists(poi_path) else pd.DataFrame()
    
    return txn, outlet, coords, season, poi


def compute_monthly_volumes(txn_df):
    """Aggregate to outlet-month level total volume."""
    monthly = txn_df.groupby(['Outlet_ID', 'Year', 'Month', 'Distributor_ID']).agg(
        Volume_Liters=('Volume_Liters', 'sum'),
        Total_Bill_Value=('Total_Bill_Value', 'sum'),
        SKU_Count=('SKU_ID', 'nunique'),
        Transaction_Count=('SKU_ID', 'count')
    ).reset_index()
    return monthly


def compute_outlet_features(monthly_df, outlet_df):
    """
    Feature engineering for each outlet:
    - Historical max, mean, median, P90, P95 volumes
    - Coefficient of variation (consistency)
    - Growth trend (linear slope)
    - Active months count
    - Constraint detection
    """
    features = []
    
    for outlet_id, grp in monthly_df.groupby('Outlet_ID'):
        grp_sorted = grp.sort_values(['Year', 'Month'])
        volumes = grp_sorted['Volume_Liters'].values
        
        # Skip outlets with too few data points
        if len(volumes) < 2:
            features.append({
                'Outlet_ID': outlet_id,
                'Distributor_ID': grp['Distributor_ID'].mode().iloc[0] if len(grp) > 0 else 'UNKNOWN',
                'historical_max': volumes.max() if len(volumes) > 0 else 0,
                'historical_mean': volumes.mean() if len(volumes) > 0 else 0,
                'historical_median': np.median(volumes) if len(volumes) > 0 else 0,
                'historical_p90': np.percentile(volumes, 90) if len(volumes) > 0 else 0,
                'historical_p95': np.percentile(volumes, 95) if len(volumes) > 0 else 0,
                'cv': 0,
                'active_months': len(volumes),
                'avg_sku_breadth': grp['SKU_Count'].mean(),
                'growth_slope': 0,
                'is_constrained': False,
                'total_history_volume': volumes.sum(),
            })
            continue
        
        # Basic statistics
        hist_max = volumes.max()
        hist_mean = volumes.mean()
        hist_median = np.median(volumes)
        hist_p90 = np.percentile(volumes, 90)
        hist_p95 = np.percentile(volumes, 95)
        cv = volumes.std() / hist_mean if hist_mean > 0 else 0
        
        # Growth trend (linear regression slope on monthly index)
        x = np.arange(len(volumes))
        if len(volumes) >= 3:
            slope, _, _, _, _ = stats.linregress(x, volumes)
        else:
            slope = 0
        
        # Constraint Detection:
        # An outlet is likely supply-constrained if:
        # 1. Low CV (< 0.15) = very consistent → hitting a ceiling
        # 2. Multiple months at near-max level (within 5% of max)
        near_max_count = np.sum(volumes >= hist_max * 0.95)
        near_max_ratio = near_max_count / len(volumes)
        is_constrained = (cv < 0.15 and near_max_ratio > 0.3) or (near_max_ratio > 0.5)
        
        features.append({
            'Outlet_ID': outlet_id,
            'Distributor_ID': grp['Distributor_ID'].mode().iloc[0],
            'historical_max': hist_max,
            'historical_mean': hist_mean,
            'historical_median': hist_median,
            'historical_p90': hist_p90,
            'historical_p95': hist_p95,
            'cv': cv,
            'active_months': len(volumes),
            'avg_sku_breadth': grp['SKU_Count'].mean(),
            'growth_slope': slope,
            'is_constrained': is_constrained,
            'total_history_volume': volumes.sum(),
        })
    
    return pd.DataFrame(features)


def compute_peer_benchmarks(feat_df, outlet_df):
    """
    Peer Benchmarking: For each outlet, compute the P90 volume of its peer group.
    Peers = same Outlet_Type + same Outlet_Size + same Distributor region.
    """
    # Merge outlet attributes
    merged = feat_df.merge(outlet_df[['Outlet_ID', 'Outlet_Type', 'Outlet_Size', 'Cooler_Count']],
                           on='Outlet_ID', how='left')
    
    # Extract distributor region
    merged['Region'] = merged['Distributor_ID'].str.extract(r'DIST_(\w+)_\d+')[0]
    
    # Compute peer group P90
    peer_groups = merged.groupby(['Outlet_Type', 'Outlet_Size', 'Region'])
    
    peer_p90 = peer_groups['historical_max'].transform(lambda x: np.percentile(x, 90))
    peer_p75 = peer_groups['historical_max'].transform(lambda x: np.percentile(x, 75))
    peer_median = peer_groups['historical_max'].transform('median')
    
    merged['peer_p90_max'] = peer_p90
    merged['peer_p75_max'] = peer_p75
    merged['peer_median_max'] = peer_median
    merged['peer_group_size'] = peer_groups['Outlet_ID'].transform('count')
    
    return merged


def compute_seasonality_factor(season_df):
    """
    Compute Jan 2026 seasonality multiplier per distributor.
    Uses historical January indices relative to annual average.
    """
    # Map seasonality index to numeric
    season_map = {'Favorable': 1.15, 'Moderate': 1.0, 'Un-Favorable': 0.85}
    season_df['season_numeric'] = season_df['Seasonality_Index'].map(season_map).fillna(1.0)
    
    # Get January-specific seasonality per distributor (average across years)
    jan_season = season_df[season_df['Month'] == 1].groupby('Distributor_ID')['season_numeric'].mean()
    
    # If no Jan 2026 specifically, use average January pattern
    seasonality_factors = jan_season.to_dict()
    
    return seasonality_factors


def compute_poi_uplift(poi_df):
    """
    Convert POI accessibility scores to demand uplift factors.
    
    Logic: Outlets with higher foot traffic proximity (schools, hospitals,
    bus stops) have higher latent demand that may not be captured in
    constrained historical sales.
    
    Uplift formula: 1 + (accessibility_score × max_uplift_pct)
    Where max_uplift_pct reflects the maximum additional demand potential
    from location advantages (capped at 25%).
    """
    if poi_df.empty:
        return {}
    
    MAX_UPLIFT = 0.25  # Maximum 25% uplift from POI proximity
    
    uplift_dict = {}
    for _, row in poi_df.iterrows():
        score = row.get('poi_accessibility_score', 0)
        uplift_dict[row['Outlet_ID']] = 1.0 + (score * MAX_UPLIFT)
    
    return uplift_dict


def compute_holiday_effect():
    """
    January 2026 holiday count effect.
    More holidays → slightly lower demand (shops closed).
    We estimate ~2 public holidays in Jan 2026 (Duruthu Poya, Thai Pongal).
    This is a small correction factor.
    """
    # Average working days in Jan: ~27. With 2 holidays: 25 effective days
    # Adjustment = 25/27 ≈ 0.926 for total monthly, but beverages may spike
    # around holidays (festive demand). Net effect is approximately neutral.
    return 1.0  # Neutral for January


def estimate_latent_potential(merged_df, seasonality_factors, poi_uplift, holiday_factor):
    """
    Final latent potential estimation using the uncapping framework.
    
    For each outlet i:
    
    Base_Potential_i = max(
        historical_p95_i,                    # Own best performance
        peer_P90 × 0.8                       # Peer benchmark (discounted)
    )
    
    If outlet is constrained:
        Base_Potential_i *= constraint_uncap_factor (1.10–1.30)
    
    Potential_i = Base_Potential_i 
                  × Seasonality_Jan2026
                  × POI_Uplift
                  × Holiday_Factor
                  × (1 + growth_adjustment)
    """
    results = []
    
    for _, row in merged_df.iterrows():
        oid = row['Outlet_ID']
        dist_id = row['Distributor_ID']
        
        # ── Step 1: Base Potential (uncapped) ──
        own_best = row['historical_p95']
        peer_ref = row.get('peer_p90_max', own_best) * 0.80  # Discount peer benchmark
        
        base_potential = max(own_best, peer_ref)
        
        # Ensure base potential is at least the historical max 
        # (potential can never be less than observed maximum)
        base_potential = max(base_potential, row['historical_max'])
        
        # ── Step 2: Constraint Uncapping ──
        if row['is_constrained']:
            # How far below peer P90 is this outlet? → larger uncap
            if row['peer_p90_max'] > 0:
                gap_ratio = row['historical_max'] / row['peer_p90_max']
            else:
                gap_ratio = 1.0
            
            if gap_ratio < 0.5:
                uncap_factor = 1.30  # Far below peers → large uncap
            elif gap_ratio < 0.75:
                uncap_factor = 1.20
            else:
                uncap_factor = 1.10
            
            base_potential *= uncap_factor
        
        # ── Step 3: Seasonality ──
        season_factor = seasonality_factors.get(dist_id, 1.0)
        
        # ── Step 4: POI Uplift ──
        poi_factor = poi_uplift.get(oid, 1.0)
        
        # ── Step 5: Growth Trend ──
        # Only apply positive growth (potential is a ceiling, not a prediction)
        growth_adj = max(row['growth_slope'] / (row['historical_mean'] + 1e-6), 0)
        growth_factor = 1.0 + min(growth_adj * 0.5, 0.15)  # Cap at 15% growth uplift
        
        # ── Step 6: Cooler Effect ──
        cooler_count = row.get('Cooler_Count', 0)
        cooler_factor = 1.0 + min(cooler_count * 0.03, 0.15)  # Each cooler adds ~3%, max 15%
        
        # ── Final Potential ──
        potential = (
            base_potential 
            * season_factor 
            * poi_factor 
            * holiday_factor
            * growth_factor
            * cooler_factor
        )
        
        results.append({
            'Outlet_ID': oid,
            'Predicted_Maximum_Monthly_Liters': round(potential, 2),
            'base_potential': round(base_potential, 2),
            'seasonality_factor': round(season_factor, 4),
            'poi_uplift_factor': round(poi_factor, 4),
            'growth_factor': round(growth_factor, 4),
            'cooler_factor': round(cooler_factor, 4),
            'is_constrained': row['is_constrained'],
            'peer_group_size': row.get('peer_group_size', 0),
        })
    
    return pd.DataFrame(results)


def run_gold_pipeline():
    """Execute the complete Gold layer pipeline."""
    print("\n" + "█" * 60)
    print("  GOLD LAYER - LATENT POTENTIAL ESTIMATION")
    print("  Team: CodeStormers | Data Storm 7.0")
    print("█" * 60)
    
    # Load data
    print("\n  📂 Loading Silver-layer data...")
    txn, outlet, coords, season, poi = load_silver_data()
    print(f"    Transactions: {len(txn):,} rows")
    print(f"    Outlets:      {len(outlet):,} rows")
    print(f"    Coordinates:  {len(coords):,} rows")
    print(f"    Seasonality:  {len(season):,} rows")
    print(f"    POI features: {len(poi):,} rows")
    
    # Step 1: Compute monthly aggregates
    print("\n  📊 Computing monthly outlet volumes...")
    monthly = compute_monthly_volumes(txn)
    print(f"    Monthly records: {len(monthly):,}")
    
    # Step 2: Compute outlet-level features
    print("\n  🔧 Computing outlet features...")
    features = compute_outlet_features(monthly, outlet)
    print(f"    Outlets with features: {len(features):,}")
    constrained_count = features['is_constrained'].sum()
    print(f"    Supply-constrained outlets detected: {constrained_count:,} "
          f"({constrained_count/len(features)*100:.1f}%)")
    
    # Step 3: Peer benchmarking
    print("\n  👥 Computing peer group benchmarks...")
    merged = compute_peer_benchmarks(features, outlet)
    
    # Step 4: Seasonality factors
    print("\n  📅 Computing January 2026 seasonality factors...")
    seasonality_factors = compute_seasonality_factor(season)
    for dist_id, factor in sorted(seasonality_factors.items()):
        print(f"    {dist_id}: {factor:.3f}")
    
    # Step 5: POI uplift
    print("\n  📍 Computing POI demand uplift...")
    poi_uplift = compute_poi_uplift(poi)
    if poi_uplift:
        uplift_vals = list(poi_uplift.values())
        print(f"    Mean uplift: {np.mean(uplift_vals):.3f}")
        print(f"    Max uplift: {np.max(uplift_vals):.3f}")
    else:
        print("    ⚠️ No POI data available, using neutral uplift (1.0)")
    
    # Step 6: Holiday effect
    holiday_factor = compute_holiday_effect()
    
    # Step 7: Estimate latent potential
    print("\n  🎯 Estimating Maximum Monthly Purchase Potential...")
    predictions = estimate_latent_potential(merged, seasonality_factors, poi_uplift, holiday_factor)
    
    # Save enriched features to Gold
    enriched_path = os.path.join(GOLD_DIR, 'outlet_enriched_features.csv')
    merged.to_csv(enriched_path, index=False)
    print(f"\n  💾 Enriched features saved: {enriched_path}")
    
    # Save detailed predictions to Gold
    detailed_path = os.path.join(GOLD_DIR, 'predictions_detailed.csv')
    predictions.to_csv(detailed_path, index=False)
    print(f"  💾 Detailed predictions saved: {detailed_path}")
    
    # Save final submission format
    submission = predictions[['Outlet_ID', 'Predicted_Maximum_Monthly_Liters']].copy()
    submission = submission.sort_values('Outlet_ID').reset_index(drop=True)
    
    submission_path = os.path.join(BASE_DIR, '..', 'CodeStormers_predictions.csv')
    submission.to_csv(submission_path, index=False)
    print(f"  💾 Submission file saved: {submission_path}")
    
    # Print summary statistics
    print(f"\n  📊 PREDICTION SUMMARY:")
    print(f"  {'─'*40}")
    vals = submission['Predicted_Maximum_Monthly_Liters']
    print(f"    Total outlets: {len(submission):,}")
    print(f"    Mean potential:   {vals.mean():.1f} L")
    print(f"    Median potential: {vals.median():.1f} L")
    print(f"    Min potential:    {vals.min():.1f} L")
    print(f"    Max potential:    {vals.max():.1f} L")
    print(f"    Total potential:  {vals.sum():,.0f} L")
    
    print(f"\n" + "█" * 60)
    print(f"  ✅ GOLD LAYER COMPLETE")
    print(f"█" * 60)
    
    return submission


if __name__ == '__main__':
    run_gold_pipeline()
