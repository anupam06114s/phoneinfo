import sys
import os
import json
import math

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

def fetch_data_direct(number: str, hf_token: str = None):
    """
    Directly query Hugging Face parquet shards without running a local web server.
    """
    number = str(number).strip()
    if not number.isdigit() or len(number) < 10 or len(number) > 15:
        print(f"[ERROR] Invalid number '{number}'. Must be 10-15 digits.")
        return None

    if not hf_token:
        hf_token = os.getenv("HF_TOKEN", "").strip()

    last_digit = number[-1]
    primary_url = f"https://huggingface.co/datasets/ansh21112/hitek-data-bucket/resolve/main/final_master_shard_{last_digit}.parquet"
    alt_url = f"https://huggingface.co/datasets/ansh21112/hitek-data-bucket/resolve/main/alt_master_shard_{last_digit}.parquet"

    print(f"[INFO] Searching data for: {number} (Shard: {last_digit})...")

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
            print(f"[WARN] Secret setting: {err}")

    try:
        # 1. Main Shard
        query_main = f"""
            SELECT mobile, name, fname, address, alt, circle, id, email 
            FROM read_parquet('{primary_url}') 
            WHERE mobile IN ('{number}', ' {number} ')
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
            WHERE alt IN ('{number}', ' {number} ')
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

        print("\n=== SUCCESSFUL RESULT ===")
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        return result

    except Exception as e:
        err_msg = str(e)
        error_result = {
            "status": "error",
            "message": f"Database processing error: {err_msg}",
            "Developer": "@anupam"
        }
        print("\n=== ERROR ===")
        print(json.dumps(error_result, indent=2))
        return error_result

if __name__ == "__main__":
    phone_num = sys.argv[1] if len(sys.argv) > 1 else input("Enter Phone Number: ")
    token = sys.argv[2] if len(sys.argv) > 2 else os.getenv("HF_TOKEN", "")
    fetch_data_direct(phone_num, token)
