"""
03_poi_scraping.py
==================
External Data Acquisition: 3 High-Value Sources
1. OpenStreetMap POIs via Overpass API (batch by geographic grid)
2. Open-Meteo Weather (January temperature/precipitation)
3. Population density proxy from outlet clustering

Output: gold/poi_data.csv — one row per Outlet_ID with all external features.
"""

import pandas as pd
import numpy as np
import requests
import time
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *

OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
OVERPASS_URL = OVERPASS_URLS[0]  # primary mirror
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# Sri Lanka bounding box for province-level queries
PROVINCE_BOUNDS = {
    'Western':       {'lat_min': 6.70, 'lat_max': 7.35, 'lon_min': 79.75, 'lon_max': 80.25},
    'Central':       {'lat_min': 6.85, 'lat_max': 7.75, 'lon_min': 80.20, 'lon_max': 81.10},
    'North-Western': {'lat_min': 7.15, 'lat_max': 8.20, 'lon_min': 79.60, 'lon_max': 80.40},
    'Southern':      {'lat_min': 5.90, 'lat_max': 6.55, 'lon_min': 79.90, 'lon_max': 80.90},
}

# POI filter expressions (without element type — we add node/way in the query)
POI_FILTERS = {
    'schools':     '["amenity"="school"]',
    'hospitals':   '["amenity"~"hospital|clinic|doctors"]',
    'bus_stops':   '["highway"="bus_stop"]',
    'banks':       '["amenity"~"bank|atm"]',
    'shops':       '["shop"]',
    'worship':     '["amenity"="place_of_worship"]',
    'restaurants': '["amenity"~"restaurant|cafe|fast_food"]',
    'tourism':     '["tourism"]',
    'fuel':        '["amenity"="fuel"]',
    'markets':     '["amenity"~"marketplace"]',
}


# ========================================================================
# SOURCE 1: OpenStreetMap POIs (batch by grid cell, not per-outlet)
# ========================================================================
def haversine_km(lat1, lon1, lat2, lon2):
    """Fast vectorized haversine distance in km."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    return R * 2 * np.arcsin(np.sqrt(a))


def fetch_pois_for_bbox(south, west, north, east, tag_filter, retries=2):
    """Fetch all POIs of a given type within a bounding box. Tries multiple mirrors."""
    bbox = f"({south},{west},{north},{east})"
    query = f"""
[out:json][timeout:120];
(
  node{tag_filter}{bbox};
  way{tag_filter}{bbox};
  relation{tag_filter}{bbox};
);
out center;
"""
    for url in OVERPASS_URLS:
        for attempt in range(retries):
            try:
                resp = requests.post(url, data={'data': query}, timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    pois = []
                    for el in data.get('elements', []):
                        lat = el.get('lat') or el.get('center', {}).get('lat')
                        lon = el.get('lon') or el.get('center', {}).get('lon')
                        if lat and lon:
                            pois.append((lat, lon))
                    return pois
                elif resp.status_code in (429, 406):
                    print(f"[{resp.status_code}@{url.split('/')[2][:15]}]", end=" ", flush=True)
                    time.sleep(10 * (attempt + 1))
                else:
                    print(f"[HTTP{resp.status_code}]", end=" ", flush=True)
                    time.sleep(5)
            except Exception as e:
                print(f"[{type(e).__name__}]", end=" ", flush=True)
                time.sleep(5)
        # If this mirror failed, try next one
    return []


def scrape_osm_pois(coords_df, radius_km=1.0):
    """
    Batch POI scraping strategy:
    1. Fetch ALL POIs of each type for the entire Sri Lanka coverage area
    2. For each outlet, count POIs within radius_km using vectorized haversine
    This avoids 20K individual API calls.
    """
    print("\n  [SOURCE 1] OpenStreetMap POIs (batch strategy)")
    print(f"  Radius: {radius_km} km")

    # Overall bounding box from our outlet coordinates
    lat_min = coords_df['Latitude'].min() - 0.02
    lat_max = coords_df['Latitude'].max() + 0.02
    lon_min = coords_df['Longitude'].min() - 0.02
    lon_max = coords_df['Longitude'].max() + 0.02

    print(f"  Bounding box: ({lat_min:.2f}, {lon_min:.2f}) to ({lat_max:.2f}, {lon_max:.2f})")

    outlet_lats = coords_df['Latitude'].values
    outlet_lons = coords_df['Longitude'].values
    n_outlets = len(coords_df)

    results = {f'poi_{cat}': np.zeros(n_outlets, dtype=int) for cat in POI_FILTERS}

    for cat_name, tag_query in POI_FILTERS.items():
        print(f"    Fetching {cat_name}...", end=" ", flush=True)
        pois = fetch_pois_for_bbox(lat_min, lon_min, lat_max, lon_max, tag_query)
        print(f"{len(pois)} POIs found.", end=" ", flush=True)

        if len(pois) == 0:
            print("Skipping.")
            continue

        # Vectorized distance calculation: for each outlet, count POIs within radius
        poi_lats = np.array([p[0] for p in pois])
        poi_lons = np.array([p[1] for p in pois])

        counts = np.zeros(n_outlets, dtype=int)
        # Process in chunks to manage memory
        chunk_size = 500
        for i in range(0, n_outlets, chunk_size):
            end = min(i + chunk_size, n_outlets)
            for j in range(i, end):
                dists = haversine_km(outlet_lats[j], outlet_lons[j], poi_lats, poi_lons)
                counts[j] = (dists <= radius_km).sum()

        results[f'poi_{cat_name}'] = counts
        print(f"Mapped. Avg: {counts.mean():.1f}")
        time.sleep(2)  # be polite to Overpass

    # Build DataFrame
    poi_df = pd.DataFrame(results)
    poi_df['Outlet_ID'] = coords_df['Outlet_ID'].values
    poi_df['poi_total'] = poi_df[[c for c in poi_df.columns if c.startswith('poi_')]].sum(axis=1)

    print(f"\n  POI scraping complete: {len(poi_df)} outlets enriched")
    return poi_df


# ========================================================================
# SOURCE 2: Open-Meteo Weather (January climate for each outlet)
# ========================================================================
def fetch_weather_for_coords(lat, lon, retries=3):
    """Fetch January average temperature and precipitation for a coordinate."""
    params = {
        'latitude': round(lat, 4),
        'longitude': round(lon, 4),
        'start_date': '2025-01-01',
        'end_date': '2025-01-31',
        'daily': 'temperature_2m_mean,precipitation_sum',
        'timezone': 'Asia/Colombo',
    }
    for attempt in range(retries):
        try:
            resp = requests.get(OPEN_METEO_URL, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                daily = data.get('daily', {})
                temps = [t for t in daily.get('temperature_2m_mean', []) if t is not None]
                precip = [p for p in daily.get('precipitation_sum', []) if p is not None]
                return {
                    'weather_temp_jan_avg': np.mean(temps) if temps else None,
                    'weather_temp_jan_max': np.max(temps) if temps else None,
                    'weather_precip_jan_total': np.sum(precip) if precip else None,
                }
            elif resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
            else:
                time.sleep(2)
        except Exception:
            time.sleep(3)
    return {'weather_temp_jan_avg': None, 'weather_temp_jan_max': None, 'weather_precip_jan_total': None}


def scrape_weather(coords_df):
    """
    Fetch January weather for outlets.
    Strategy: cluster outlets into ~100 grid cells, query once per cell.
    """
    print("\n  [SOURCE 2] Open-Meteo Weather (January 2025 climate)")

    # Round coordinates to 0.05 degree grid (~5km cells) to deduplicate
    coords_df = coords_df.copy()
    coords_df['grid_lat'] = (coords_df['Latitude'] * 20).round() / 20
    coords_df['grid_lon'] = (coords_df['Longitude'] * 20).round() / 20
    coords_df['grid_key'] = coords_df['grid_lat'].astype(str) + '_' + coords_df['grid_lon'].astype(str)

    unique_grids = coords_df[['grid_key', 'grid_lat', 'grid_lon']].drop_duplicates()
    print(f"  {len(unique_grids)} unique grid cells (from {len(coords_df)} outlets)")

    # Query each unique grid cell
    grid_weather = {}
    for i, (_, row) in enumerate(unique_grids.iterrows()):
        result = fetch_weather_for_coords(row['grid_lat'], row['grid_lon'])
        grid_weather[row['grid_key']] = result

        if (i + 1) % 20 == 0:
            print(f"    [{i+1}/{len(unique_grids)}] queried...")
        time.sleep(0.3)  # rate limit

    # Map back to outlets
    weather_df = coords_df[['Outlet_ID', 'grid_key']].copy()
    for col in ['weather_temp_jan_avg', 'weather_temp_jan_max', 'weather_precip_jan_total']:
        weather_df[col] = weather_df['grid_key'].map(lambda k: grid_weather.get(k, {}).get(col))

    weather_df = weather_df.drop(columns=['grid_key'])

    # Fill any missing with overall median
    for col in ['weather_temp_jan_avg', 'weather_temp_jan_max', 'weather_precip_jan_total']:
        weather_df[col] = weather_df[col].fillna(weather_df[col].median())

    print(f"  Weather complete: temp avg={weather_df['weather_temp_jan_avg'].mean():.1f}C, "
          f"precip total={weather_df['weather_precip_jan_total'].mean():.1f}mm")
    return weather_df


# ========================================================================
# SOURCE 3: Population Density Proxy (outlet clustering density)
# ========================================================================
def calc_population_proxy(coords_df):
    """
    Population density proxy using outlet density at multiple radii.
    More outlets nearby = denser commercial area = more people.
    Also calculates distance to nearest outlet (competition signal).
    """
    print("\n  [SOURCE 3] Population Density Proxy (outlet clustering)")

    lats = coords_df['Latitude'].values
    lons = coords_df['Longitude'].values
    n = len(coords_df)

    density_500m = np.zeros(n, dtype=int)
    density_1km = np.zeros(n, dtype=int)
    density_2km = np.zeros(n, dtype=int)
    nearest_dist = np.full(n, np.inf)

    for i in range(n):
        dists = haversine_km(lats[i], lons[i], lats, lons)
        dists[i] = np.inf  # exclude self
        density_500m[i] = (dists <= 0.5).sum()
        density_1km[i] = (dists <= 1.0).sum()
        density_2km[i] = (dists <= 2.0).sum()
        nearest_dist[i] = dists.min()

        if (i + 1) % 2000 == 0:
            print(f"    [{i+1}/{n}] processed...")

    pop_df = pd.DataFrame({
        'Outlet_ID': coords_df['Outlet_ID'].values,
        'pop_outlets_500m': density_500m,
        'pop_outlets_1km': density_1km,
        'pop_outlets_2km': density_2km,
        'pop_nearest_outlet_km': np.round(nearest_dist, 3),
    })

    print(f"  Density complete: avg 2km density={density_2km.mean():.1f}")
    return pop_df


# ========================================================================
# MAIN
# ========================================================================
def main():
    print("\n" + "#" * 60)
    print("#" + " " * 10 + "EXTERNAL DATA ACQUISITION" + " " * 23 + "#")
    print("#" * 60)

    # Load cleaned coordinates
    coords_path = os.path.join(SILVER_DIR, OUTLET_COORDS_CLEAN)
    if not os.path.exists(coords_path):
        print(f"  [ERROR] {coords_path} not found. Run 02_silver_clean.py first!")
        return

    coords = pd.read_csv(coords_path)
    print(f"  Loaded {len(coords):,} outlet coordinates")

    cache_path = os.path.join(GOLD_DIR, "external_features_cache.csv")

    # --- Source 1: OSM POIs ---
    poi_df = scrape_osm_pois(coords, radius_km=1.0)

    # Save intermediate
    poi_df.to_csv(os.path.join(GOLD_DIR, POI_DATA_FILE), index=False)
    print(f"  [SAVED] POI data -> gold/{POI_DATA_FILE}")

    # --- Source 2: Weather ---
    weather_df = scrape_weather(coords)

    # --- Source 3: Population Proxy ---
    pop_df = calc_population_proxy(coords)

    # --- Merge all external features ---
    print("\n  Merging all external features...")
    external = poi_df.merge(weather_df, on='Outlet_ID', how='outer')
    external = external.merge(pop_df, on='Outlet_ID', how='outer')

    # Ensure all outlets from outlet_master are present
    outlet_master = pd.read_csv(os.path.join(SILVER_DIR, OUTLET_MASTER_CLEAN))
    all_ids = pd.DataFrame({'Outlet_ID': outlet_master['Outlet_ID'].unique()})
    external = all_ids.merge(external, on='Outlet_ID', how='left')
    external = external.fillna(0)

    # Save final
    output_path = os.path.join(GOLD_DIR, "external_features.csv")
    external.to_csv(output_path, index=False)

    print(f"\n  External features saved: {output_path}")
    print(f"  Shape: {external.shape}")
    print(f"  Columns: {list(external.columns)}")

    # Update poi_data.csv with full feature set for gold layer
    external.to_csv(os.path.join(GOLD_DIR, POI_DATA_FILE), index=False)

    print("\n" + "#" * 60)
    print("#" + " " * 8 + "EXTERNAL DATA COMPLETE" + " " * 28 + "#")
    print("#" * 60)


if __name__ == "__main__":
    main()
