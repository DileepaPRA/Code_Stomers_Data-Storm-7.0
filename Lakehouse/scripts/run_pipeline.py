"""
=============================================================================
MASTER PIPELINE RUNNER
=============================================================================
Team: CodeStormers | Data Storm 7.0
Purpose: Orchestrate the full Lakehouse pipeline: Bronze → Silver → Gold
=============================================================================
"""

import os
import sys
import time

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))

def main():
    start_time = time.time()
    
    print("\n" + "╔" + "═"*58 + "╗")
    print("║  DATA STORM 7.0 - LAKEHOUSE PIPELINE                    ║")
    print("║  Team: CodeStormers                                     ║")
    print("╚" + "═"*58 + "╝")
    
    # ── STEP 1: Bronze Ingestion ──
    print("\n\n🥉 STEP 1: BRONZE LAYER - Raw Data Ingestion")
    print("─" * 50)
    from scripts_01_bronze import ingest_to_bronze
    ingest_to_bronze()
    
    # ── STEP 2: Silver Cleaning ──
    print("\n\n🥈 STEP 2: SILVER LAYER - Data Quality & Cleaning")
    print("─" * 50)
    from scripts_02_silver import (
        clean_transactions, clean_outlet_master, clean_outlet_coordinates,
        clean_seasonality, clean_holidays, cross_dataset_checks
    )
    txn_df    = clean_transactions()
    outlet_df = clean_outlet_master()
    coords_df = clean_outlet_coordinates()
    season_df = clean_seasonality()
    holiday_df = clean_holidays()
    txn_df    = cross_dataset_checks(txn_df, outlet_df, coords_df, season_df)
    
    # ── STEP 3: POI Scraping ──
    print("\n\n📍 STEP 3: POI SCRAPING - External Data Enrichment")
    print("─" * 50)
    try:
        from scripts_03_poi import scrape_poi_features
        poi_df = scrape_poi_features()
    except Exception as e:
        print(f"  ⚠️ POI scraping had issues: {e}")
        print(f"  ℹ️ Continuing without POI data (neutral uplift)...")
    
    # ── STEP 4: Gold Layer ──
    print("\n\n🥇 STEP 4: GOLD LAYER - Latent Potential Estimation")
    print("─" * 50)
    from scripts_04_gold import run_gold_pipeline
    submission = run_gold_pipeline()
    
    elapsed = time.time() - start_time
    print(f"\n\n{'='*60}")
    print(f"  🏁 PIPELINE COMPLETE in {elapsed:.1f} seconds")
    print(f"{'='*60}")


if __name__ == '__main__':
    # Import individual modules with aliased names
    import importlib
    
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    
    # Use importlib to handle module names with numbers
    scripts_01_bronze = importlib.import_module('01_bronze_ingestion')
    scripts_02_silver = importlib.import_module('02_silver_cleaning')
    scripts_03_poi    = importlib.import_module('03_poi_scraping')
    scripts_04_gold   = importlib.import_module('04_gold_potential')
    
    ingest_to_bronze = scripts_01_bronze.ingest_to_bronze
    
    clean_transactions = scripts_02_silver.clean_transactions
    clean_outlet_master = scripts_02_silver.clean_outlet_master
    clean_outlet_coordinates = scripts_02_silver.clean_outlet_coordinates
    clean_seasonality = scripts_02_silver.clean_seasonality
    clean_holidays = scripts_02_silver.clean_holidays
    cross_dataset_checks = scripts_02_silver.cross_dataset_checks
    
    scrape_poi_features = scripts_03_poi.scrape_poi_features
    run_gold_pipeline = scripts_04_gold.run_gold_pipeline
    
    start_time = time.time()
    
    print("\n" + "╔" + "═"*58 + "╗")
    print("║  DATA STORM 7.0 - LAKEHOUSE PIPELINE                    ║")
    print("║  Team: CodeStormers                                     ║")
    print("╚" + "═"*58 + "╝")
    
    # STEP 1
    print("\n\n🥉 STEP 1: BRONZE LAYER - Raw Data Ingestion")
    print("─" * 50)
    ingest_to_bronze()
    
    # STEP 2
    print("\n\n🥈 STEP 2: SILVER LAYER - Data Quality & Cleaning")
    print("─" * 50)
    txn_df    = clean_transactions()
    outlet_df = clean_outlet_master()
    coords_df = clean_outlet_coordinates()
    season_df = clean_seasonality()
    holiday_df = clean_holidays()
    txn_df    = cross_dataset_checks(txn_df, outlet_df, coords_df, season_df)
    
    # STEP 3
    print("\n\n📍 STEP 3: POI SCRAPING - External Data Enrichment")
    print("─" * 50)
    try:
        poi_df = scrape_poi_features()
    except Exception as e:
        print(f"  ⚠️ POI scraping had issues: {e}")
        print(f"  ℹ️ Continuing without POI data (neutral uplift)...")
    
    # STEP 4
    print("\n\n🥇 STEP 4: GOLD LAYER - Latent Potential Estimation")
    print("─" * 50)
    submission = run_gold_pipeline()
    
    elapsed = time.time() - start_time
    print(f"\n\n{'='*60}")
    print(f"  🏁 PIPELINE COMPLETE in {elapsed:.1f} seconds")
    print(f"{'='*60}")
