"""
04_gold_feature_engineering.py
==============================
Gold Layer: Feature Engineering
Merges all Silver-layer datasets + POI data into a single outlet-level feature matrix.
Produces model_ready.csv in gold/ with ~30+ engineered features per outlet.
"""

import pandas as pd
import numpy as np
import os
import sys
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *


def load_silver_data():
    """Load all cleaned datasets from Silver layer."""
    print("  Loading Silver-layer datasets...")

    txn = pd.read_csv(os.path.join(SILVER_DIR, TRANSACTIONS_CLEAN))
    outlet = pd.read_csv(os.path.join(SILVER_DIR, OUTLET_MASTER_CLEAN))
    coords = pd.read_csv(os.path.join(SILVER_DIR, OUTLET_COORDS_CLEAN))
    season = pd.read_csv(os.path.join(SILVER_DIR, SEASONALITY_CLEAN))
    holidays = pd.read_csv(os.path.join(SILVER_DIR, HOLIDAYS_CLEAN))

    print(f"    transactions: {len(txn):,}")
    print(f"    outlet_master: {len(outlet):,}")
    print(f"    coordinates: {len(coords):,}")
    print(f"    seasonality: {len(season):,}")
    print(f"    holidays: {len(holidays):,}")

    return txn, outlet, coords, season, holidays


def build_transaction_features(txn):
    """
    Build per-outlet features from transaction history.
    Aggregates across all SKUs and months.
    """
    print("\n  Building transaction features...")

    # Monthly outlet-level aggregation (sum across SKUs within each month)
    monthly = txn.groupby(['Outlet_ID', 'Year', 'Month']).agg(
        monthly_volume=('Volume_Liters', 'sum'),
        monthly_bill=('Total_Bill_Value', 'sum'),
        sku_count=('SKU_ID', 'nunique'),
    ).reset_index()

    # Create a time index for trend calculation
    monthly['time_idx'] = (monthly['Year'] - 2023) * 12 + monthly['Month']

    # Per-outlet aggregation
    features = monthly.groupby('Outlet_ID').agg(
        txn_total_volume_all=('monthly_volume', 'sum'),
        txn_avg_monthly_volume=('monthly_volume', 'mean'),
        txn_median_monthly_volume=('monthly_volume', 'median'),
        txn_max_monthly_volume=('monthly_volume', 'max'),
        txn_min_monthly_volume=('monthly_volume', 'min'),
        txn_std_monthly_volume=('monthly_volume', 'std'),
        txn_months_active=('monthly_volume', 'count'),
        txn_avg_monthly_bill=('monthly_bill', 'mean'),
        txn_max_monthly_bill=('monthly_bill', 'max'),
        txn_avg_sku_diversity=('sku_count', 'mean'),
    ).reset_index()

    # Fill NaN std (outlets with only 1 month)
    features.loc[features['txn_months_active'] < 2, 'txn_std_monthly_volume'] = np.nan

    # Coefficient of Variation (low CV → possibly constrained at a cap)
    features['txn_cv_monthly_volume'] = np.where(
        (features['txn_avg_monthly_volume'] > 0) & (features['txn_months_active'] >= 2),
        features['txn_std_monthly_volume'] / features['txn_avg_monthly_volume'],
        np.nan
    )

    # Percentiles (P90, P95) — closest to true potential
    pcts = monthly.groupby('Outlet_ID')['monthly_volume'].quantile([0.90, 0.95]).unstack()
    pcts.columns = ['txn_p90_monthly_volume', 'txn_p95_monthly_volume']
    features = features.merge(pcts, on='Outlet_ID', how='left')

    # Volume trend slope (OLS of monthly_volume vs time_idx)
    def calc_slope(group):
        if len(group) < 3:
            return 0.0
        slope, _, _, _, _ = stats.linregress(group['time_idx'], group['monthly_volume'])
        return slope

    slopes = monthly.groupby('Outlet_ID').apply(calc_slope, include_groups=False).reset_index()
    slopes.columns = ['Outlet_ID', 'txn_volume_trend_slope']
    features = features.merge(slopes, on='Outlet_ID', how='left')

    # Recent performance (last 6 months: Oct-Dec 2025)
    recent = monthly[monthly['time_idx'] >= 31]  # months 31-36 = Jul-Dec 2025
    recent_agg = recent.groupby('Outlet_ID')['monthly_volume'].mean().reset_index()
    recent_agg.columns = ['Outlet_ID', 'txn_recent_6m_avg']
    features = features.merge(recent_agg, on='Outlet_ID', how='left')
    features['txn_recent_6m_avg'] = features['txn_recent_6m_avg'].fillna(features['txn_avg_monthly_volume'])

    # Growth ratio (recent vs early)
    early = monthly[monthly['time_idx'] <= 6]
    early_agg = early.groupby('Outlet_ID')['monthly_volume'].mean().reset_index()
    early_agg.columns = ['Outlet_ID', 'txn_early_6m_avg']
    features = features.merge(early_agg, on='Outlet_ID', how='left')
    features['txn_early_6m_avg'] = features['txn_early_6m_avg'].fillna(features['txn_avg_monthly_volume'])
    features['txn_growth_ratio'] = np.where(
        features['txn_early_6m_avg'] > 0,
        features['txn_recent_6m_avg'] / features['txn_early_6m_avg'],
        1.0
    )

    # Revenue per liter
    features['txn_revenue_per_liter'] = np.where(
        features['txn_avg_monthly_volume'] > 0,
        features['txn_avg_monthly_bill'] / features['txn_avg_monthly_volume'],
        0
    )

    # Get distributor mapping (most common distributor per outlet)
    dist_map = txn.groupby('Outlet_ID')['Distributor_ID'].agg(lambda x: x.mode().iloc[0]).reset_index()
    dist_map.columns = ['Outlet_ID', 'Distributor_ID']
    features = features.merge(dist_map, on='Outlet_ID', how='left')

    # Drop intermediate column
    features = features.drop(columns=['txn_early_6m_avg'], errors='ignore')

    print(f"  Transaction features: {features.shape[1] - 1} features for {len(features):,} outlets")
    return features


def build_outlet_features(outlet):
    """Encode outlet master attributes."""
    print("\n  Building outlet attribute features...")

    df = outlet.copy()

    # Ordinal encode outlet size
    df['outlet_size_encoded'] = df['Outlet_Size'].map(OUTLET_SIZE_ORDER).fillna(1)

    # One-hot encode outlet type
    type_dummies = pd.get_dummies(df['Outlet_Type'], prefix='outlet_type')
    df = pd.concat([df, type_dummies], axis=1)

    # Rename for clarity
    df = df.rename(columns={'Cooler_Count': 'outlet_cooler_count'})

    # Drop raw string columns (keep encoded)
    df = df.drop(columns=['Outlet_Size', 'Outlet_Type'])

    print(f"  Outlet features: {df.shape[1] - 1} features for {len(df):,} outlets")
    return df


def build_geo_features(coords, all_outlet_ids):
    """Build geographic features including outlet density."""
    print("\n  Building geographic features...")

    df = coords.copy()
    df = df.rename(columns={'Latitude': 'geo_latitude', 'Longitude': 'geo_longitude'})

    # Calculate outlet density (count of other outlets within ~2km)
    # Using simple Euclidean approximation (1 degree ≈ 111km at equator)
    # 2km ≈ 0.018 degrees
    threshold = 0.018
    densities = []
    lat_arr = df['geo_latitude'].values
    lon_arr = df['geo_longitude'].values

    for i in range(len(df)):
        dist = np.sqrt((lat_arr - lat_arr[i])**2 + (lon_arr - lon_arr[i])**2)
        count = (dist < threshold).sum() - 1  # exclude self
        densities.append(count)

    df['geo_outlet_density_2km'] = densities

    # For outlets without coordinates (quarantined), we'll fill with 0 later
    # Ensure all outlets are represented
    all_ids_df = pd.DataFrame({'Outlet_ID': list(all_outlet_ids)})
    df = all_ids_df.merge(df, on='Outlet_ID', how='left')

    # Fill missing geo features with median
    for col in ['geo_latitude', 'geo_longitude', 'geo_outlet_density_2km']:
        df[col] = df[col].fillna(df[col].median())

    print(f"  Geo features: {df.shape[1] - 1} features for {len(df):,} outlets")
    return df


def build_seasonality_features(season, distributor_map):
    """Build seasonality features for the target prediction month (Jan 2026)."""
    print("\n  Building seasonality features...")

    # Get January seasonality for each distributor
    # If Jan 2026 exists, use it; otherwise average Jan 2023/2024/2025
    jan_data = season[season['Month'] == 1]

    jan_avg = jan_data.groupby('Distributor_ID')['Seasonality_Index'].agg(
        lambda x: x.mode().iloc[0] if len(x) > 0 else 'Moderate'
    ).reset_index()
    jan_avg.columns = ['Distributor_ID', 'jan_seasonality']

    # Map to numeric
    jan_avg['dist_seasonality_jan_encoded'] = jan_avg['jan_seasonality'].map(SEASONALITY_ENCODING).fillna(1.0)

    # Merge with distributor mapping
    result = distributor_map.merge(jan_avg, on='Distributor_ID', how='left')
    result['dist_seasonality_jan_encoded'] = result['dist_seasonality_jan_encoded'].fillna(1.0)

    # Province encoding from distributor
    result['dist_province'] = result['Distributor_ID'].map(DISTRIBUTOR_PROVINCE)
    province_dummies = pd.get_dummies(result['dist_province'], prefix='province')
    result = pd.concat([result, province_dummies], axis=1)

    result = result.drop(columns=['jan_seasonality', 'dist_province'], errors='ignore')

    print(f"  Seasonality features: {result.shape[1] - 1} features for {len(result):,} outlets")
    return result


def build_holiday_features(holidays):
    """Count holidays in January 2026 (or January average)."""
    print("\n  Building holiday features...")

    holidays['Date'] = pd.to_datetime(holidays['Date'], errors='coerce')
    holidays['Year'] = holidays['Date'].dt.year
    holidays['Month'] = holidays['Date'].dt.month

    # Count Jan holidays per year
    jan_holidays = holidays[holidays['Month'] == 1]
    avg_jan_holidays = len(jan_holidays) / jan_holidays['Year'].nunique() if jan_holidays['Year'].nunique() > 0 else 0

    # Count by type for January
    jan_by_type = jan_holidays.groupby('Holiday_Type').size()
    poya_count = jan_by_type.get('Poya Day', 0) / (jan_holidays['Year'].nunique() or 1)

    print(f"  Average January holidays: {avg_jan_holidays:.1f}")
    print(f"  Average January Poya days: {poya_count:.1f}")

    # These are global features (same for all outlets)
    return {
        'cal_holidays_jan': round(avg_jan_holidays),
        'cal_poya_days_jan': round(poya_count),
    }


def merge_external_data(all_outlet_ids):
    """Load external features (POI + Weather + Population) from gold layer."""
    print("\n  Loading external features (POI + Weather + Population)...")

    # Try the full external features file first
    ext_path = os.path.join(GOLD_DIR, "external_features.csv")
    poi_path = os.path.join(GOLD_DIR, POI_DATA_FILE)

    if os.path.exists(ext_path):
        ext = pd.read_csv(ext_path)
        # Keep Outlet_ID + all feature columns (poi_, weather_, pop_)
        feat_cols = ['Outlet_ID'] + [c for c in ext.columns
                     if c.startswith(('poi_', 'weather_', 'pop_'))]
        ext = ext[feat_cols]
        print(f"  External features loaded: {len(ext):,} outlets, {len(feat_cols)-1} features")
    elif os.path.exists(poi_path):
        ext = pd.read_csv(poi_path)
        feat_cols = ['Outlet_ID'] + [c for c in ext.columns if c.startswith('poi_')]
        ext = ext[feat_cols]
        print(f"  POI-only data loaded: {len(ext):,} outlets, {len(feat_cols)-1} features")
    else:
        print(f"  [WARN] No external data found. Creating empty features.")
        print(f"  Run 03_poi_scraping.py to populate.")
        ext = pd.DataFrame({'Outlet_ID': list(all_outlet_ids)})
        for cat in ['schools', 'hospitals', 'bus_stops', 'banks', 'shops',
                     'worship', 'restaurants', 'tourism', 'fuel', 'markets', 'total']:
            ext[f'poi_{cat}'] = 0

    # Ensure all outlets are represented
    all_ids_df = pd.DataFrame({'Outlet_ID': list(all_outlet_ids)})
    ext = all_ids_df.merge(ext, on='Outlet_ID', how='left')
    ext = ext.fillna(0)

    return ext


def main():
    print("\n" + "#" * 60)
    print("#" + " " * 14 + "GOLD LAYER: FEATURE ENGINEERING" + " " * 13 + "#")
    print("#" * 60)

    # Load Silver data
    txn, outlet, coords, season, holidays = load_silver_data()

    all_outlet_ids = set(outlet['Outlet_ID'].unique())
    print(f"\n  Total outlets to process: {len(all_outlet_ids):,}")

    # Build feature groups
    txn_features = build_transaction_features(txn)
    outlet_features = build_outlet_features(outlet)
    geo_features = build_geo_features(coords, all_outlet_ids)

    # Distributor map from txn features
    dist_map = txn_features[['Outlet_ID', 'Distributor_ID']].copy()
    season_features = build_seasonality_features(season, dist_map)

    holiday_feats = build_holiday_features(holidays)
    external_features = merge_external_data(all_outlet_ids)

    # --- MERGE ALL FEATURES ---
    print("\n  Merging all feature groups...")

    # Start with all active outlet IDs (from outlet master)
    model_df = pd.DataFrame({'Outlet_ID': list(all_outlet_ids)})

    # Merge transaction features
    model_df = model_df.merge(txn_features, on='Outlet_ID', how='left')

    # Fallback for missing Distributor_ID (outlets with zero valid transactions)
    mode_dist = dist_map['Distributor_ID'].mode()[0] if not dist_map.empty else 'DIST_W_01'
    model_df['Distributor_ID'] = model_df['Distributor_ID'].fillna(mode_dist)

    # Merge outlet attributes
    model_df = model_df.merge(outlet_features, on='Outlet_ID', how='left')

    # Merge geo features
    model_df = model_df.merge(geo_features, on='Outlet_ID', how='left')

    # Merge seasonality (on Outlet_ID + Distributor_ID)
    season_cols = [c for c in season_features.columns if c != 'Distributor_ID' or c == 'Outlet_ID']
    model_df = model_df.merge(
        season_features.drop(columns=['Distributor_ID'], errors='ignore'),
        on='Outlet_ID', how='left'
    )

    # Merge external features (POI + Weather + Population)
    model_df = model_df.merge(external_features, on='Outlet_ID', how='left')

    # Add global holiday features
    for k, v in holiday_feats.items():
        model_df[k] = v

    # Fill any remaining NaN
    numeric_cols = model_df.select_dtypes(include=[np.number]).columns
    model_df[numeric_cols] = model_df[numeric_cols].fillna(0)

    # Save
    output_path = os.path.join(GOLD_DIR, MODEL_READY_FILE)
    model_df.to_csv(output_path, index=False)

    # Also save the feature matrix (without Distributor_ID string)
    feature_path = os.path.join(GOLD_DIR, OUTLET_FEATURES_FILE)
    model_df.drop(columns=['Distributor_ID'], errors='ignore').to_csv(feature_path, index=False)

    print(f"\n  Gold layer complete!")
    print(f"  Output: {output_path}")
    print(f"  Shape: {model_df.shape[0]:,} outlets × {model_df.shape[1]} columns")
    print(f"\n  Feature columns:")
    for col in sorted(model_df.columns):
        if col != 'Outlet_ID':
            print(f"    {col}")
    print("#" * 60)


if __name__ == "__main__":
    main()
