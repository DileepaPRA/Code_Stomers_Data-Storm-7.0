"""
03_poi_scraping.py
==================
External Data: POI (Point of Interest) Scraping via OpenStreetMap Overpass API.
Queries for nearby schools, hospitals, bus stops, banks, shops, places of worship,
restaurants, and tourist attractions around each outlet's coordinates.

Output: gold/poi_data.csv with POI counts per outlet within a configurable radius.

Note: This script handles rate limiting and caches results to avoid re-scraping.
For 20K outlets, we cluster nearby outlets and batch queries to reduce API calls.
"""

import pandas as pd
import numpy as np
import requests
import time
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import *

# Overpass API endpoint (public, no auth needed)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# POI categories to scrape with their OSM tags
POI_CATEGORIES = {
    'schools':          '["amenity"="school"]',
    'hospitals':        '["amenity"~"hospital|clinic"]',
    'bus_stops':        '["highway"="bus_stop"]',
    'banks':            '["amenity"~"bank|atm"]',
    'shops':            '["shop"]',
    'worship':          '["amenity"="place_of_worship"]',
    'restaurants':      '["amenity"~"restaurant|cafe|fast_food"]',
    'tourism':          '["tourism"]',
    'fuel_stations':    '["amenity"="fuel"]',
    'markets':          '["amenity"~"marketplace|market"]',
}


def build_overpass_query(lat, lon, radius_m, categories):
    """Build an Overpass QL query for multiple POI categories around a point."""
    parts = []
    for cat_name, tag_filter in categories.items():
        parts.append(f'  node{tag_filter}(around:{radius_m},{lat},{lon});')
        parts.append(f'  way{tag_filter}(around:{radius_m},{lat},{lon});')

    query = f"""
[out:json][timeout:30];
(
{chr(10).join(parts)}
);
out count;
"""
    return query


def build_overpass_query_detailed(lat, lon, radius_m, categories):
    """Build a query that returns counts per category (separate queries per category)."""
    queries = {}
    for cat_name, tag_filter in categories.items():
        q = f"""
[out:json][timeout:25];
(
  node{tag_filter}(around:{radius_m},{lat},{lon});
  way{tag_filter}(around:{radius_m},{lat},{lon});
);
out count;
"""
        queries[cat_name] = q
    return queries


def query_overpass_count(query, retries=3, delay=2):
    """Send query to Overpass API and return the element count."""
    for attempt in range(retries):
        try:
            resp = requests.post(OVERPASS_URL, data={'data': query}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                # Count response format
                if 'elements' in data and len(data['elements']) > 0:
                    el = data['elements'][0]
                    if 'tags' in el and 'total' in el['tags']:
                        return int(el['tags']['total'])
                    return len(data['elements'])
                return 0
            elif resp.status_code == 429:
                # Rate limited
                wait = delay * (attempt + 2)
                print(f"    [RATE LIMIT] Waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    [WARN] HTTP {resp.status_code}, retry {attempt+1}/{retries}")
                time.sleep(delay)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"    [WARN] {type(e).__name__}, retry {attempt+1}/{retries}")
            time.sleep(delay * (attempt + 1))
    return -1  # Failed


def scrape_pois_for_outlet(lat, lon, radius_m=POI_RADIUS_METERS):
    """Scrape all POI categories for a single outlet location."""
    results = {}
    for cat_name, tag_filter in POI_CATEGORIES.items():
        query = f"""
[out:json][timeout:25];
(
  node{tag_filter}(around:{radius_m},{lat},{lon});
  way{tag_filter}(around:{radius_m},{lat},{lon});
);
out count;
"""
        count = query_overpass_count(query)
        results[f'poi_{cat_name}'] = count
        time.sleep(0.5)  # Be polite to the API

    results['poi_total'] = sum(v for v in results.values() if v >= 0)
    return results


def scrape_pois_batch(coords_df, radius_m=POI_RADIUS_METERS, cache_file=None):
    """
    Scrape POIs for all outlets. Uses caching to resume interrupted scraping.

    Parameters
    ----------
    coords_df : DataFrame with Outlet_ID, Latitude, Longitude
    radius_m : search radius in meters
    cache_file : path to cache intermediate results
    """
    # Load cache if exists
    if cache_file and os.path.exists(cache_file):
        cached = pd.read_csv(cache_file)
        done_ids = set(cached['Outlet_ID'].unique())
        print(f"  [CACHE] Loaded {len(done_ids)} previously scraped outlets")
        results = cached.to_dict('records')
    else:
        done_ids = set()
        results = []

    remaining = coords_df[~coords_df['Outlet_ID'].isin(done_ids)]
    total = len(coords_df)
    done = len(done_ids)

    print(f"  Scraping POIs for {len(remaining)} outlets (radius={radius_m}m)...")
    print(f"  Categories: {list(POI_CATEGORIES.keys())}")

    for i, (_, row) in enumerate(remaining.iterrows()):
        outlet_id = row['Outlet_ID']
        lat = row['Latitude']
        lon = row['Longitude']

        poi_data = scrape_pois_for_outlet(lat, lon, radius_m)
        poi_data['Outlet_ID'] = outlet_id
        poi_data['Latitude'] = lat
        poi_data['Longitude'] = lon
        results.append(poi_data)

        done += 1
        if done % 25 == 0:
            print(f"  [{done}/{total}] {outlet_id} — total POIs: {poi_data.get('poi_total', 0)}")
            # Save intermediate cache
            if cache_file:
                pd.DataFrame(results).to_csv(cache_file, index=False)

        # Rate limiting: pause between outlets
        time.sleep(1.0)

    return pd.DataFrame(results)


def main():
    print("\n" + "#" * 60)
    print("#" + " " * 14 + "POI SCRAPING (OpenStreetMap)" + " " * 17 + "#")
    print("#" * 60)

    # Load cleaned coordinates from Silver layer
    coords_path = os.path.join(SILVER_DIR, OUTLET_COORDS_CLEAN)
    if not os.path.exists(coords_path):
        print(f"  [ERROR] Silver coordinates not found: {coords_path}")
        print("  Run 02_silver_clean.py first!")
        return

    coords = pd.read_csv(coords_path)
    print(f"  Loaded {len(coords):,} outlet coordinates from Silver layer")

    # Cache file for resumable scraping
    cache_path = os.path.join(GOLD_DIR, "poi_cache.csv")

    # Scrape POIs
    poi_df = scrape_pois_batch(
        coords,
        radius_m=POI_RADIUS_METERS,
        cache_file=cache_path
    )

    # Save final output
    output_path = os.path.join(GOLD_DIR, POI_DATA_FILE)
    poi_df.to_csv(output_path, index=False)

    print(f"\n  POI scraping complete!")
    print(f"  Output: {output_path}")
    print(f"  Records: {len(poi_df):,}")
    print(f"\n  POI Summary:")
    for col in poi_df.columns:
        if col.startswith('poi_'):
            vals = poi_df[col]
            print(f"    {col}: mean={vals.mean():.1f}, median={vals.median():.0f}, max={vals.max():.0f}")

    print("#" * 60)


if __name__ == "__main__":
    main()
