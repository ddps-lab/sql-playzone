import os
import boto3
import polars as pl
from dotenv import load_dotenv
from io import BytesIO

from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

PROFILE_NAME = os.getenv("PROFILE_NAME")
REGION = os.getenv("REGION")
BUCKET_NAME = os.getenv("BUCKET_NAME")
OBJECT_PATH = os.getenv("OBJECT_PATH") # Original source path

def get_s3_session():
    """Create and return a boto3 session."""
    session_kwargs = {}
    if PROFILE_NAME:
        session_kwargs['profile_name'] = PROFILE_NAME
    if REGION:
        session_kwargs['region_name'] = REGION
    return boto3.Session(**session_kwargs)

def get_date_range(start_date_str, end_date_str):
    """Generate a list of dates between start_date and end_date (inclusive)."""
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    delta = end_date - start_date
    if delta.days < 0:
        return []
    return [start_date + timedelta(days=i) for i in range(delta.days + 1)]

def verify_s3_uploads(start_date_str, end_date_str, target_root):
    """
    Rigorous verification:
    1. Fetches source data from OBJECT_PATH.
    2. Fetches uploaded data from target_root.
    3. Compares row counts 1:1.
    4. Verifies 'user_name' is missing in target.
    """
    session = get_s3_session()
    s3 = session.client('s3')
    dates = get_date_range(start_date_str, end_date_str)

    print("\n" + "="*70)
    print(f"        RIGOROUS S3 DATA CROSS-VERIFICATION")
    print(f"        Source: {OBJECT_PATH}")
    print(f"        Target: {target_root}")
    print(f"        Range:  {start_date_str} to {end_date_str}")
    print("="*70)

    stats = {"pass": 0, "mismatch": 0, "missing_src": 0, "missing_tgt": 0, "pii_fail": 0}

    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        rel_path = f"{date.strftime('%Y/%m/%d')}.csv.gz"
        src_key = f"{OBJECT_PATH}/{rel_path}"
        tgt_key = f"{target_root}/{rel_path}"

        src_rows = None
        tgt_rows = None

        # Fetch Source
        try:
            resp = s3.get_object(Bucket=BUCKET_NAME, Key=src_key)
            src_df = pl.read_csv(BytesIO(resp['Body'].read()))
            src_rows = len(src_df)
        except s3.exceptions.NoSuchKey:
            src_rows = -1 # Mark as missing
        except Exception as e:
            print(f"  [ERR] Source {date_str}: {e}")

        # Fetch Target
        try:
            resp = s3.get_object(Bucket=BUCKET_NAME, Key=tgt_key)
            tgt_df = pl.read_csv(BytesIO(resp['Body'].read()))
            tgt_rows = len(tgt_df)
            
            # PII Check
            if "user_name" in tgt_df.columns:
                print(f"  [FAILURE] {date_str}: PII ('user_name') found in target!")
                stats["pii_fail"] += 1
        except s3.exceptions.NoSuchKey:
            tgt_rows = -1
        except Exception as e:
            print(f"  [ERR] Target {date_str}: {e}")

        # Comparison
        if src_rows == -1:
            print(f"  [SKIP] {date_str}: Source file missing in S3 ({src_key})")
            stats["missing_src"] += 1
        elif tgt_rows == -1:
            print(f"  [FAIL] {date_str}: Target file missing in S3 ({tgt_key})")
            stats["missing_tgt"] += 1
        elif src_rows != tgt_rows:
            print(f"  [FAIL] {date_str}: Row count mismatch! (Src: {src_rows}, Tgt: {tgt_rows})")
            stats["mismatch"] += 1
        else:
            print(f"  [PASS] {date_str}: Row counts match ({src_rows}).")
            stats["pass"] += 1

    print("\n" + "="*70)
    print(f"Verification Summary:")
    print(f"  - PASS:         {stats['pass']}")
    print(f"  - Mismatch:     {stats['mismatch']}")
    print(f"  - Missing Src:  {stats['missing_src']}")
    print(f"  - Missing Tgt:  {stats['missing_tgt']}")
    print(f"  - PII Failures: {stats['pii_fail']}")
    print("="*70 + "\n")

if __name__ == "__main__":
    # Settings (Should match filter_data.py)
    START_DATE = "2025-09-18"
    END_DATE = "2025-12-29"
    TARGET_ROOT_KEY = "filtered/behavior"
    
    verify_s3_uploads(START_DATE, END_DATE, TARGET_ROOT_KEY)
