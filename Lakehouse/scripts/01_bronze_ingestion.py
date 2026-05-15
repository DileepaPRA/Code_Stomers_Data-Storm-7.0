"""
=============================================================================
BRONZE LAYER - Raw Data Ingestion
=============================================================================
Team: CodeStormers | Data Storm 7.0
Purpose: Ingest all raw flat files as-is with no transformations.
         Adds ingestion metadata (timestamp, source) for lineage tracking.
=============================================================================
"""

import shutil
import os
import datetime
import json

# ── Paths ──────────────────────────────────────────────────────────────────
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'datastorm-7-0-rotaract')
BRONZE_DIR   = os.path.join(os.path.dirname(__file__), '..', 'bronze')

RAW_FILES = [
    'transactions_history_final.csv',
    'outlet_master.csv',
    'outlet_coordinates.csv',
    'distributor_seasonality_details.csv',
    'holiday_list.csv',
    '1. dataset_description.xlsx',
]


def ingest_to_bronze():
    """Copy raw files into Bronze layer with ingestion metadata."""
    os.makedirs(BRONZE_DIR, exist_ok=True)
    manifest = {
        'ingestion_timestamp': datetime.datetime.now().isoformat(),
        'source_directory': os.path.abspath(RAW_DATA_DIR),
        'files': []
    }

    for fname in RAW_FILES:
        src = os.path.join(RAW_DATA_DIR, fname)
        dst = os.path.join(BRONZE_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            file_size = os.path.getsize(dst)
            manifest['files'].append({
                'filename': fname,
                'size_bytes': file_size,
                'status': 'ingested'
            })
            print(f"  ✓ Ingested: {fname} ({file_size:,} bytes)")
        else:
            manifest['files'].append({
                'filename': fname,
                'status': 'NOT FOUND'
            })
            print(f"  ✗ NOT FOUND: {fname}")

    # Write manifest for lineage
    manifest_path = os.path.join(BRONZE_DIR, '_ingestion_manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  📋 Manifest written to: {manifest_path}")


if __name__ == '__main__':
    print("=" * 60)
    print("BRONZE LAYER INGESTION")
    print("=" * 60)
    ingest_to_bronze()
    print("\n✅ Bronze ingestion complete.")
