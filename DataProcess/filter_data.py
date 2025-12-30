import os
import boto3
import polars as pl
from dotenv import load_dotenv
from datetime import datetime, timedelta
from io import BytesIO
from collections import defaultdict

# Load environment variables
load_dotenv()

PROFILE_NAME = os.getenv("PROFILE_NAME")
REGION = os.getenv("REGION")
BUCKET_NAME = os.getenv("BUCKET_NAME")
OBJECT_PATH = os.getenv("OBJECT_PATH")


def get_s3_session():
    """Create and return a boto3 session."""
    try:
        # Use profile_name and region_name if provided in .env
        session_kwargs = {}
        if PROFILE_NAME:
            session_kwargs['profile_name'] = PROFILE_NAME
        if REGION:
            session_kwargs['region_name'] = REGION

        return boto3.Session(**session_kwargs)
    except Exception as e:
        print(f"Error creating boto3 session: {e}")
        return None


def get_date_range(start_date_str, end_date_str):
    """Generate a list of dates between start_date and end_date (inclusive)."""
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    delta = end_date - start_date
    if delta.days < 0:
        return []
    return [start_date + timedelta(days=i) for i in range(delta.days + 1)]


def fetch_data_from_s3(start_date_str, end_date_str):
    """
    Fetch data from S3 for the given date range using Polars.
    Returns a dictionary where keys are 'YYYY/MM/DD.csv.gz' and values are Polars DataFrames.
    """
    session = get_s3_session()
    if not session:
        return {}

    s3 = session.client('s3')
    dates = get_date_range(start_date_str, end_date_str)

    df_dict = {}
    missing_dates = []
    monthly_rows = defaultdict(int)
    total_rows = 0

    for date in dates:
        year = date.strftime("%Y")
        month = date.strftime("%m")
        day = date.strftime("%d")
        date_key = date.strftime("%Y-%m-%d")

        # Relative key for dictionary: YYYY/MM/DD.csv.gz
        relative_key = f"{year}/{month}/{day}.csv.gz"
        # Full S3 key: path/YYYY/MM/DD.csv.gz
        full_key = f"{OBJECT_PATH}/{relative_key}"

        try:
            print(f"Fetching: s3://{BUCKET_NAME}/{full_key}")
            response = s3.get_object(Bucket=BUCKET_NAME, Key=full_key)
            content = response['Body'].read()

            # Read gzipped CSV using Polars
            df = pl.read_csv(BytesIO(content))
            df_dict[relative_key] = df

            # Update statistics
            row_count = len(df)
            monthly_rows[f"{year}-{month}"] += row_count
            total_rows += row_count

            print(f"  -> Successfully loaded {row_count} rows.")

        except s3.exceptions.NoSuchKey:
            print(f"  -> File not found: {full_key}")
            missing_dates.append(date_key)
        except Exception as e:
            print(f"  -> Error fetching {full_key}: {e}")
            missing_dates.append(date_key)

    # Print Report
    print("\n" + "="*40)
    print("        S3 DATA FETCH REPORT")
    print("="*40)

    if missing_dates:
        print(f"Missing Dates ({len(missing_dates)}):")
        for d in missing_dates:
            print(f"  - {d}")
    else:
        print("All dates in range were successfully loaded.")

    print("\nMonthly Row Counts:")
    for mon, count in sorted(monthly_rows.items()):
        print(f"  - {mon}: {count:,} rows")

    print(f"\nTotal Row Count: {total_rows:,} rows")
    print("="*40 + "\n")

    return df_dict


def remove_pii_data(df_dict):
    """
    Remove PII (user_name column) from all DataFrames in the dictionary.
    """
    cleaned_dict = {}
    for key, df in df_dict.items():
        if "user_name" in df.columns:
            cleaned_dict[key] = df.drop("user_name")
        else:
            cleaned_dict[key] = df
    return cleaned_dict


def upload_data_to_s3(df_dict, target_root_key):
    """
    Upload processed DataFrames back to S3 under a specific root key.
    Maintains the YYYY/MM/DD.csv.gz structure.
    """
    session = get_s3_session()
    if not session:
        return False

    s3 = session.client('s3')
    success_count = 0
    total_count = len(df_dict)

    print("\n" + "="*40)
    print(f"        UPLOADING DATA TO S3 (Root: {target_root_key})")
    print("="*40)

    import gzip
    for relative_key, df in df_dict.items():
        target_key = f"{target_root_key}/{relative_key}"
        try:
            csv_buffer = BytesIO()
            df.write_csv(csv_buffer)
            
            compressed_buffer = BytesIO()
            with gzip.GzipFile(fileobj=compressed_buffer, mode='wb') as f:
                f.write(csv_buffer.getvalue())
            
            print(f"Uploading: s3://{BUCKET_NAME}/{target_key}")
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=target_key,
                Body=compressed_buffer.getvalue()
            )
            success_count += 1
            print(f"  -> Successfully uploaded.")
        except Exception as e:
            print(f"  -> Error uploading {target_key}: {e}")

    print("\n" + "="*40)
    print(f"Upload Complete: {success_count}/{total_count} files uploaded.")
    print("="*40 + "\n")
    return success_count == total_count


if __name__ == "__main__":
    # Settings
    START_DATE = "2025-09-18"
    END_DATE = "2025-12-29"
    TARGET_ROOT_KEY = "filtered/behavior"

    # 1. Download
    data_dict = fetch_data_from_s3(START_DATE, END_DATE)

    if data_dict:
        # Debug: Show head after download
        first_key = list(data_dict.keys())[0]
        print(f"\n[DEBUG] Sample data head after download ({first_key}):")
        print(data_dict[first_key].head(3))

        # 2. Process (Remove PII)
        print("\nRemoving PII data (user_name)...")
        data_dict = remove_pii_data(data_dict)

        # Debug: Show head after PII removal
        print(f"\n[DEBUG] Sample data head after PII removal ({first_key}):")
        print(data_dict[first_key].head(3))

        # 3. Upload
        upload_data_to_s3(data_dict, TARGET_ROOT_KEY)
    else:
        print("No data fetched to process.")
