import sys
import os
import json
import math
from dotenv import load_dotenv

load_dotenv()

# Ensure utf-8 output on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import duckdb

def sanitize_value(val):
    if val is None:
        return None
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    return str(val)

def fetch_data_direct(number: str):
    """
    Directly query Hugging Face 3-digit parquet shards using DuckDB without running local server.
    """
    number = str(number).strip()
    if not number.isdigit() or len(number) < 10 or len(number) > 15:
        print(f"[ERROR] Invalid number '{number}'. Must be 10-15 digits.")
        return None

    hf_token = os.getenv("HF_TOKEN", "").strip()
    hf_dataset = os.getenv("HF_DATASET", "MRSHREY197/hitek-3digit-rah").strip()

    # 3-digit shard routing (e.g., 027 for numbers ending in 027)
    shard_id = number[-3:]
    primary_url = f"https://huggingface.co/datasets/{hf_dataset}/resolve/main/main_shard_{shard_id}.parquet"
    alt_url = f"https://huggingface.co/datasets/{hf_dataset}/resolve/main/alt_shard_{shard_id}.parquet"

    print(f"[INFO] Searching data for: {number} (Shard: {shard_id})...")

    con = duckdb.connect(config={
        'max_memory': '250MB',
        'threads': '2',
        'enable_object_cache': 'false',
        'preserve_insertion_order': 'false'
    })
    con.execute("INSTALL httpfs;")
    con.execute("LOAD httpfs;")

    if hf_token:
        try:
            con.execute(f"""
                CREATE OR REPLACE SECRET hf_secret (
                    TYPE HUGGINGFACE,
                    TOKEN '{hf_token}'
                );
            """)
        except Exception as err:
            print(f"[WARN] HF Secret setting error: {err}")

    try:
        # 1. Main Shard
        query_main = f"""
            SELECT mobile, name, fname, address, alt, circle, id, email 
            FROM read_parquet('{primary_url}') 
            WHERE TRIM(mobile) = '{number}' OR mobile IN ('{number}', ' {number} ')
        """
        rel_main = con.execute(query_main)
        cols_main = [d[0] for d in rel_main.description]
        main_records = [
            {col: sanitize_value(v) for col, v in zip(cols_main, row)}
            for row in rel_main.fetchall()
        ]

        # 2. Alt Shard
        query_alt = f"""
            SELECT mobile, name, fname, address, alt, circle, id, email 
            FROM read_parquet('{alt_url}') 
            WHERE TRIM(alt) = '{number}' OR alt IN ('{number}', ' {number} ')
        """
        rel_alt = con.execute(query_alt)
        cols_alt = [d[0] for d in rel_alt.description]
        alt_records = [
            {col: sanitize_value(v) for col, v in zip(cols_alt, row)}
            for row in rel_alt.fetchall()
        ]

        if not main_records and not alt_records:
            result = {
                "status": "not_found",
                "phone": number,
                "Developer": "@anupam"
            }
        else:
            result = {
                "status": "success",
                "phone": number,
                "Data": {
                    "Main_Records": main_records,
                    "Alt_Records": alt_records
                },
                "Developer": "@anupam"
            }

        return result

    except Exception as e:
        print(f"[ERROR] Database query failed: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_direct.py <PHONE_NUMBER>")
        print("Example: python fetch_direct.py 011100012027")
        sys.exit(1)

    phone = sys.argv[1]
    res = fetch_data_direct(phone)
    if res:
        print(json.dumps(res, indent=2, ensure_ascii=False))
