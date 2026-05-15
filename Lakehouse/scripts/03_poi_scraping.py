"""
=============================================================================
POI PROXY FEATURES - Location-Based Demand Indicators
=============================================================================
Team: CodeStormers | Data Storm 7.0

Since the Overpass API is rate-limited/unavailable, we use a proxy approach:
1. Outlet density within radius = urban/commercial zone indicator
2. Known Sri Lankan city center proximity scoring
3. Coordinate-based province/urbanization estimation

This is documented in the report as an alternative when API is unavailable.
We also attempt a smaller Overpass query as a sample.
=============================================================================
"""

import pandas as pd
import numpy as np
import os
import json
import requests
import time
from math import radians, cos, sin, asin, sqrt

BASE_DIR   = os.path.join(os.path.dirname(__file__), '..')
SILVER_DIR = os.path.join(BASE_DIR, 'silver')
GOLD_DIR   = os.path.join(BASE_DIR, 'gold')
os.makedirs(GOLD_DIR, exist_ok=True)

# Major Sri Lankan urban centers with approximate POI density scores
SRI_LANKA_CENTERS = [
    # (name, lat, lon, population_score)
    ('Colombo', 6.9271, 79.8612, 1.0),
    ('Kandy', 7.2906, 80.6337, 0.7),
    ('Galle', 6.0535, 80.2210, 0.6),
    ('Negombo', 7.2008, 79.8737, 0.5),
    ('Matara', 5.9549, 80.5550, 0.45),
    ('Kurunegala', 7.4863, 80.3647, 0.5),
    ('Ratnapura', 6.6828, 80.3994, 0.4),
    ('Panadura', 6.7133, 79.9044, 0.45),
    ('Moratuwa', 6.7736, 79.8804, 0.55),
    ('Dehiwala', 6.8510, 79.8652, 0.6),
    ('Nuwara Eliya', 6.9497, 80.7891, 0.35),
    ('Badulla', 6.9934, 81.0550, 0.35),
    ('Chilaw', 7.5758, 79.7953, 0.3),
    ('Kegalle', 7.2513, 80.3464, 0.35),
    ('Kalutara', 6.5854, 79.9607, 0.4),
    ('Hambantota', 6.1240, 81.1185, 0.3),
    ('Anuradhapura', 8.3114, 80.4037, 0.35),
    ('Trincomalee', 8.5874, 81.2152, 0.3),
    ('Batticaloa', 7.7310, 81.6924, 0.3),
    ('Jaffna', 9.6615, 80.0255, 0.45),
]


def haversine_vec(lon1, lat1, lon2_arr, lat2_arr):
    """Vectorized haversine distance in meters."""
    lon1, lat1 = radians(lon1), radians(lat1)
    lon2_arr = np.radians(lon2_arr)
    lat2_arr = np.radians(lat2_arr)
    dlat = lat2_arr - lat1
    dlon = lon2_arr - lon1
    a = np.sin(dlat/2)**2 + cos(lat1) * np.cos(lat2_arr) * np.sin(dlon/2)**2
    return 6371000 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def try_overpass_sample(coords_df, sample_size=200):
    """Try to get POI data for a sample of outlets via Overpass API."""
    headers = {'User-Agent': 'DataStorm7-CodeStormers/1.0 (academic)'}
    
    # Sample outlets spread across the coordinate space
    sample = coords_df.sample(min(sample_size, len(coords_df)), random_state=42)
    
    all_pois = []
    # Query in small bbox chunks around clusters
    lat_min, lat_max = sample['Latitude'].min(), sample['Latitude'].max()
    lon_min, lon_max = sample['Longitude'].min(), sample['Longitude'].max()
    
    CELL = 1.0  # 1 degree cells
    for lat_start in np.arange(lat_min, lat_max + CELL, CELL):
        for lon_start in np.arange(lon_min, lon_max + CELL, CELL):
            query = (
                f'[out:json][timeout:25];'
                f'(node["amenity"="school"]({lat_start},{lon_start},{lat_start+CELL},{lon_start+CELL});'
                f'node["amenity"="hospital"]({lat_start},{lon_start},{lat_start+CELL},{lon_start+CELL});'
                f'node["highway"="bus_stop"]({lat_start},{lon_start},{lat_start+CELL},{lon_start+CELL});'
                f');out;'
            )
            try:
                resp = requests.get(OVERPASS_URL, params={'data': query}, headers=headers, timeout=30)
                if resp.status_code == 200:
                    elems = resp.json().get('elements', [])
                    for e in elems:
                        cat = e.get('tags', {}).get('amenity', e.get('tags', {}).get('highway', ''))
                        if cat in ('school', 'hospital', 'bus_stop'):
                            all_pois.append({'lat': e['lat'], 'lon': e['lon'], 'category': cat})
                    print(f"    Grid ({lat_start:.1f},{lon_start:.1f}): {len(elems)} POIs")
                time.sleep(2)
            except:
                pass
    
    return all_pois


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def build_poi_features():
    print("\n" + "=" * 60)
    print("  POI FEATURE ENGINEERING")
    print("=" * 60)

    coords_df = pd.read_csv(os.path.join(SILVER_DIR, 'outlet_coordinates_clean.csv'))
    print(f"  Outlets: {len(coords_df):,}")

    lats = coords_df['Latitude'].values
    lons = coords_df['Longitude'].values

    # ── Attempt Overpass API ──
    cache_path = os.path.join(GOLD_DIR, '_poi_api_cache.json')
    api_pois = []
    
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            api_pois = json.load(f)
        print(f"  Loaded {len(api_pois)} cached API POIs")
    else:
        print("  Attempting Overpass API sample query...")
        try:
            api_pois = try_overpass_sample(coords_df, sample_size=200)
            with open(cache_path, 'w') as f:
                json.dump(api_pois, f)
            print(f"  Scraped {len(api_pois)} POIs from API")
        except Exception as e:
            print(f"  API unavailable: {e}")

    # ── Build features ──
    print("  Computing location features...")
    
    # 1. Outlet density (proxy for urban/commercial zone)
    outlet_density_1km = np.zeros(len(coords_df))
    outlet_density_2km = np.zeros(len(coords_df))
    
    for i in range(len(coords_df)):
        dists = haversine_vec(lons[i], lats[i], lons, lats)
        outlet_density_1km[i] = np.sum(dists <= 1000) - 1  # exclude self
        outlet_density_2km[i] = np.sum(dists <= 2000) - 1
        if (i + 1) % 2000 == 0:
            print(f"    Density: {i+1:,}/{len(coords_df):,}")

    # 2. City proximity score
    city_scores = np.zeros(len(coords_df))
    nearest_city_dist = np.full(len(coords_df), np.inf)
    
    for name, clat, clon, pop_score in SRI_LANKA_CENTERS:
        dists = haversine_vec(clon, clat, lons, lats)
        # Score decays with distance: score = pop_score * exp(-dist/5000)
        contribution = pop_score * np.exp(-dists / 5000)
        city_scores += contribution
        nearest_city_dist = np.minimum(nearest_city_dist, dists)

    # 3. API-based POI counts (if available)
    poi_counts = {'school': np.zeros(len(coords_df)), 
                  'hospital': np.zeros(len(coords_df)),
                  'bus_stop': np.zeros(len(coords_df))}
    nearest_poi = {'school': np.full(len(coords_df), np.nan),
                   'hospital': np.full(len(coords_df), np.nan),
                   'bus_stop': np.full(len(coords_df), np.nan)}
    
    if api_pois:
        poi_lats = np.array([p['lat'] for p in api_pois])
        poi_lons = np.array([p['lon'] for p in api_pois])
        poi_cats = [p['category'] for p in api_pois]
        
        for cat in ['school', 'hospital', 'bus_stop']:
            cat_mask = np.array([c == cat for c in poi_cats])
            if not cat_mask.any():
                continue
            cat_lats = poi_lats[cat_mask]
            cat_lons = poi_lons[cat_mask]
            
            for i in range(len(coords_df)):
                dists = haversine_vec(lons[i], lats[i], cat_lons, cat_lats)
                poi_counts[cat][i] = np.sum(dists <= 1000)
                if len(dists) > 0:
                    nearest_poi[cat][i] = np.min(dists)
                if (i + 1) % 5000 == 0 and cat == 'school':
                    print(f"    POI assignment: {i+1:,}/{len(coords_df):,}")

    # ── Assemble features ──
    result_df = pd.DataFrame({
        'Outlet_ID': coords_df['Outlet_ID'].values,
        'outlet_density_1km': outlet_density_1km.astype(int),
        'outlet_density_2km': outlet_density_2km.astype(int),
        'city_proximity_score': np.round(city_scores, 4),
        'nearest_city_m': np.round(nearest_city_dist, 0),
        'count_schools_1km': poi_counts['school'].astype(int),
        'count_hospitals_1km': poi_counts['hospital'].astype(int),
        'count_bus_stops_1km': poi_counts['bus_stop'].astype(int),
        'nearest_school_m': nearest_poi['school'],
        'nearest_hospital_m': nearest_poi['hospital'],
        'nearest_bus_stop_m': nearest_poi['bus_stop'],
    })

    # Composite accessibility score
    # Combine outlet density + city proximity + API POIs
    density_norm = np.clip(outlet_density_1km / outlet_density_1km.max(), 0, 1) if outlet_density_1km.max() > 0 else np.zeros(len(coords_df))
    city_norm = np.clip(city_scores / city_scores.max(), 0, 1) if city_scores.max() > 0 else np.zeros(len(coords_df))
    
    if api_pois:
        api_score = np.clip(
            (poi_counts['school'] / 3 + poi_counts['hospital'] / 2 + poi_counts['bus_stop'] / 5) / 3,
            0, 1
        )
        result_df['poi_accessibility_score'] = np.round(
            0.30 * density_norm + 0.30 * city_norm + 0.40 * api_score, 4
        )
    else:
        result_df['poi_accessibility_score'] = np.round(
            0.50 * density_norm + 0.50 * city_norm, 4
        )

    out_path = os.path.join(GOLD_DIR, 'poi_features.csv')
    result_df.to_csv(out_path, index=False)
    print(f"\n  Saved: {out_path} ({len(result_df):,} rows)")
    
    print(f"\n  Feature Summary:")
    for col in ['outlet_density_1km', 'city_proximity_score', 'poi_accessibility_score']:
        print(f"    {col}: mean={result_df[col].mean():.3f}, "
              f"median={result_df[col].median():.3f}, max={result_df[col].max():.3f}")

    return result_df


if __name__ == '__main__':
    build_poi_features()
