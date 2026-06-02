#!/usr/bin/env python3
"""
s3_export.py
------------
Export REAL Amazon S3 object metadata into the StorageTierIQ CSV schema.

Output columns (exactly what `storagetieriq --input` expects):
    record_id, data_type, size_mb, created_at, last_accessed,
    access_count, age_days, days_since_access

What comes from where
---------------------
* size_mb, created_at, age_days   -> from each object's size + LastModified
                                     (real; note S3 only stores LastModified,
                                      which we use as a creation proxy).
* access_count, days_since_access -> from S3 *server access logs*, if you
                                     point the script at them. Until logging
                                     has run for a while these default to
                                     0 / age (and the script warns you).

Usage
-----
    pip install boto3
    aws configure          # enter your Access Key, Secret, region

    # Stage 1 (today) - object metadata only:
    python s3_export.py --bucket MY_BUCKET --out storage_records.csv

    # Stage 2 (after enabling + collecting server access logs):
    python s3_export.py --bucket MY_BUCKET \
        --access-logs-bucket MY_LOG_BUCKET \
        --access-logs-prefix logs/ \
        --out storage_records.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone

# Map common file extensions / S3 prefixes to StorageTierIQ data types.
EXT_TO_TYPE = {
    ".log": "log", ".txt": "log",
    ".sql": "transaction", ".db": "transaction", ".csv": "transaction",
    ".jpg": "media", ".jpeg": "media", ".png": "media", ".mp4": "media",
    ".mov": "media", ".gif": "media", ".mp3": "media",
    ".bak": "backup", ".tar": "backup", ".gz": "backup", ".zip": "backup",
    ".parquet": "analytics", ".json": "analytics", ".avro": "analytics",
}


def classify_data_type(key: str) -> str:
    """Infer a StorageTierIQ data_type from an object key (extension/prefix)."""
    lower = key.lower()
    # Prefix hints win first (e.g. "backups/...", "logs/...").
    for hint, dtype in (
        ("backup", "backup"), ("log", "log"), ("media", "media"),
        ("analytics", "analytics"), ("user", "user_data"),
    ):
        if hint in lower:
            return dtype
    for ext, dtype in EXT_TO_TYPE.items():
        if lower.endswith(ext):
            return dtype
    return "user_data"


def rows_from_objects(objects: list[dict], now: datetime) -> dict:
    """Build base rows (size/age) keyed by S3 key from a list of S3 objects.

    Each object dict must have: Key, Size, LastModified (tz-aware datetime).
    """
    rows: dict[str, dict] = {}
    for obj in objects:
        key = obj["Key"]
        if key.endswith("/") or obj["Size"] == 0:
            continue  # skip "folders" / empty markers
        last_modified = obj["LastModified"]
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)
        age_days = max(1, (now - last_modified).days)
        rows[key] = {
            "record_id": key,
            "data_type": classify_data_type(key),
            "size_mb": round(obj["Size"] / (1024 * 1024), 4),
            "created_at": last_modified.strftime("%Y-%m-%d %H:%M:%S"),
            "last_accessed": last_modified.strftime("%Y-%m-%d %H:%M:%S"),
            "access_count": 0,
            "age_days": age_days,
            "days_since_access": age_days,
        }
    return rows


def parse_access_logs(log_lines: list[str]) -> dict:
    """Aggregate S3 server access log lines into per-key access stats.

    Returns {key: {"count": int, "last_access": datetime}} counting only
    successful object GETs. S3 access log fields are space-separated; the
    operation is field index 7 and the key is field 8 (standard format).
    Time is the bracketed field, e.g. [06/Feb/2024:00:00:38 +0000].
    """
    stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "last_access": None})
    for line in log_lines:
        parts = line.split()
        if len(parts) < 9:
            continue
        operation = parts[7]
        key = parts[8]
        if "GET.OBJECT" not in operation or key == "-":
            continue
        # Timestamp is wrapped in [ ... ] starting around field 2.
        ts = None
        for token in parts:
            if token.startswith("["):
                try:
                    ts = datetime.strptime(
                        token.strip("[]"), "%d/%b/%Y:%H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    ts = None
                break
        stats[key]["count"] += 1
        if ts and (stats[key]["last_access"] is None or ts > stats[key]["last_access"]):
            stats[key]["last_access"] = ts
    return dict(stats)


def merge_access_stats(rows: dict, stats: dict, now: datetime) -> None:
    """Fold access-log stats into the base rows (mutates rows in place)."""
    for key, stat in stats.items():
        if key not in rows:
            continue
        rows[key]["access_count"] = stat["count"]
        if stat["last_access"] is not None:
            rows[key]["last_accessed"] = stat["last_access"].strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            rows[key]["days_since_access"] = max(
                0, (now - stat["last_access"]).days
            )


def write_csv(rows: dict, out_path: str) -> None:
    fields = [
        "record_id", "data_type", "size_mb", "created_at", "last_accessed",
        "access_count", "age_days", "days_since_access",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows.values():
            writer.writerow(row)


# ── AWS-facing glue (needs boto3 + credentials) ────────────────────────────
def list_s3_objects(bucket: str):
    import boto3  # imported lazily so the pure logic stays testable offline

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket):
        objects.extend(page.get("Contents", []))
    return objects


def fetch_access_log_lines(log_bucket: str, prefix: str):
    import boto3

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    lines: list[str] = []
    for page in paginator.paginate(Bucket=log_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            body = s3.get_object(Bucket=log_bucket, Key=obj["Key"])["Body"].read()
            lines.extend(body.decode("utf-8", errors="ignore").splitlines())
    return lines


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Export S3 metadata to StorageTierIQ CSV")
    p.add_argument("--bucket", required=True, help="Source S3 bucket name")
    p.add_argument("--out", default="storage_records.csv", help="Output CSV path")
    p.add_argument("--access-logs-bucket", default=None,
                   help="Bucket holding S3 server access logs (optional)")
    p.add_argument("--access-logs-prefix", default="",
                   help="Prefix of the access log objects")
    args = p.parse_args(argv)

    now = datetime.now(timezone.utc)

    print(f"Listing objects in s3://{args.bucket} ...")
    objects = list_s3_objects(args.bucket)
    rows = rows_from_objects(objects, now)
    print(f"  Found {len(rows)} usable objects.")

    if args.access_logs_bucket:
        print(f"Reading access logs from s3://{args.access_logs_bucket}/"
              f"{args.access_logs_prefix} ...")
        lines = fetch_access_log_lines(args.access_logs_bucket,
                                       args.access_logs_prefix)
        stats = parse_access_logs(lines)
        merge_access_stats(rows, stats, now)
        print(f"  Parsed {len(lines):,} log lines, "
              f"{len(stats)} objects with recorded accesses.")
    else:
        print("  [WARNING] No --access-logs-bucket given. access_count and")
        print("  days_since_access are placeholders (0 / age). Enable S3 server")
        print("  access logging and re-run with --access-logs-bucket for real")
        print("  access frequencies.")

    write_csv(rows, args.out)
    print(f"Wrote {len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
