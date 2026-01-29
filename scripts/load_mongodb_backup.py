#!/usr/bin/env python3
"""
Load MongoDB backup data from JSON files into local MongoDB.
Usage: python scripts/load_mongodb_backup.py [backup_dir]
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bson import json_util
from pymongo import MongoClient

from conf.config import CONF


def load_backup(backup_dir: str):
    """Load all JSON files from backup directory into MongoDB."""

    # Connect to MongoDB
    ip = CONF["mongodb"]["mongodb_ip"]
    port = CONF["mongodb"]["mongodb_port"]
    db_name = CONF["mongodb"]["mongodb_name"]

    print(f"Connecting to MongoDB: mongodb://{ip}:{port}/{db_name}")
    client = MongoClient(f"mongodb://{ip}:{port}/")
    db = client[db_name]

    backup_path = Path(backup_dir)
    if not backup_path.exists():
        print(f"Error: Backup directory not found: {backup_dir}")
        return False

    # Find all JSON files
    json_files = list(backup_path.glob("*.json"))
    if not json_files:
        print(f"Error: No JSON files found in {backup_dir}")
        return False

    print(f"Found {len(json_files)} collections to restore")
    print("-" * 50)

    total_docs = 0
    for json_file in sorted(json_files):
        coll_name = json_file.stem  # filename without extension

        # Read and parse JSON with Extended JSON support
        with open(json_file, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip() or content.strip() == "[]":
                print(f"⏭ {coll_name}: empty, skipped")
                continue
            docs = json_util.loads(content)

        if not docs:
            print(f"⏭ {coll_name}: no documents, skipped")
            continue

        # Clear existing collection and insert new documents
        collection = db[coll_name]
        existing_count = collection.count_documents({})

        if existing_count > 0:
            print(f"  Clearing {existing_count} existing documents in {coll_name}...")
            collection.delete_many({})

        # Insert documents
        result = collection.insert_many(docs)
        inserted_count = len(result.inserted_ids)
        total_docs += inserted_count

        print(f"✓ {coll_name}: {inserted_count} documents loaded")

    print("-" * 50)
    print(f"Restore complete! Total: {total_docs} documents")

    client.close()
    return True


def main():
    # Default backup directory
    default_backup = "mongodb_20251230_220610"

    if len(sys.argv) > 1:
        backup_dir = sys.argv[1]
    else:
        # Try to find in project root
        project_root = Path(__file__).parent.parent
        backup_dir = project_root / default_backup

    print(f"Loading backup from: {backup_dir}")
    load_backup(str(backup_dir))


if __name__ == "__main__":
    main()
