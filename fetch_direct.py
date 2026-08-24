import sys
import os
import json

# Ensure utf-8 output on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import duckdb

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

    con = duckdb.connect()
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

    # Optimized query matching both clean and space-padded strings with parquet pushdown
    query = f"""
        SELECT *, 'Main' AS _record_type FROM read_parquet('{primary_url}') 
        WHERE mobile IN ('{number}', ' {number} ')
        UNION ALL
        SELECT *, 'Alt' AS _record_type FROM read_parquet('{alt_url}') 
        WHERE alt IN ('{number}', ' {number} ')
    """

    try:
        raw_results = con.execute(query).df().to_dict(orient="records")

        main_records = []
        alt_records = []

        for row in raw_results:
            rec_type = row.pop('_record_type')
            # Clean string values (strip extra whitespaces)
            cleaned_row = {k: v.strip() if isinstance(v, str) else v for k, v in row.items()}
            if rec_type == 'Main':
                main_records.append(cleaned_row)
            else:
                alt_records.append(cleaned_row)

        if not main_records and not alt_records:
            result = {
                "status": "not_found",
                "phone": number,
                "Developer": "@Maybechx"
            }
        else:
            result = {
                "status": "success",
                "phone": number,
                "Data": {
                    "Main_Records": main_records,
                    "Alt_Records": alt_records
                },
                "Developer": "@Maybechx"
            }

        print("\n=== SUCCESSFUL RESULT ===")
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        return result

    except Exception as e:
        err_msg = str(e)
        error_result = {
            "status": "error",
            "message": f"Database processing error: {err_msg}",
            "Developer": "@Maybechx"
        }
        print("\n=== ERROR ===")
        print(json.dumps(error_result, indent=2))
        return error_result

if __name__ == "__main__":
    phone_num = sys.argv[1] if len(sys.argv) > 1 else input("Enter Phone Number: ")
    token = sys.argv[2] if len(sys.argv) > 2 else os.getenv("HF_TOKEN", "")
    fetch_data_direct(phone_num, token)

