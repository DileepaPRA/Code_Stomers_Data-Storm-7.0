"""
01_bronze_ingest.py
===================
Bronze Layer: Raw Ingestion
Copies all raw CSV files from raw_extract/ to bronze/ with ZERO transformations.
Preserves the original data exactly as provided.
"""

import shutil
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *


def main():
    print("=" * 60)
    print("  BRONZE LAYER: Raw Ingestion")
    print("=" * 60)

    files_to_ingest = [
        TRANSACTIONS_FILE,
        OUTLET_MASTER_FILE,
        OUTLET_COORDS_FILE,
        SEASONALITY_FILE,
        HOLIDAYS_FILE,
    ]

    for fname in files_to_ingest:
        src = os.path.join(RAW_DIR, fname)
        dst = os.path.join(BRONZE_DIR, fname)

        if not os.path.exists(src):
            print(f"  [WARN] Source not found: {src}")
            continue

        shutil.copy2(src, dst)
        size_mb = os.path.getsize(dst) / (1024 * 1024)
        print(f"  [OK] {fname} -> bronze/ ({size_mb:.1f} MB)")

    # Also copy the dataset description for reference
    desc_file = "1. dataset_description.xlsx"
    src_desc = os.path.join(RAW_DIR, desc_file)
    if os.path.exists(src_desc):
        shutil.copy2(src_desc, os.path.join(BRONZE_DIR, desc_file))
        print(f"  [OK] {desc_file} -> bronze/")

    print("\n  Bronze ingestion complete. No transformations applied.")
    print("=" * 60)


if __name__ == "__main__":
    main()
