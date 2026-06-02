#!/usr/bin/env python3
"""
generate_traffic.py
-------------------
Generate a realistic, differentiated access pattern against a real S3
bucket so that S3 server access logging records meaningful usage. Each
configured object is fetched N times (a 1-byte ranged GET, enough to log
an access without downloading the whole object); objects left out of the
plan stay "cold".

Run this once a day for a few days, varying the plan, so both access_count
and recency (days_since_access) spread across HOT / WARM / COLD.

Usage:
    pip install boto3
    python tools/generate_traffic.py --bucket MY_BUCKET
"""

from __future__ import annotations

import argparse

# Edit this plan to taste: {object_key: number_of_accesses}.
# Frequently-accessed -> hot; rarely -> cold; omit a key -> stays cold.
DEFAULT_PLAN = {
    "Alamdar Nazarov-CV.pdf": 60,
    "Enterprise_AI_Infrastructure_Report.docx": 15,
    "pdf_maker.py": 5,
}


def main() -> int:
    p = argparse.ArgumentParser(description="Generate S3 access traffic for logging")
    p.add_argument("--bucket", default="my-storage-optimizer-bucket-2026")
    args = p.parse_args()

    import boto3

    s3 = boto3.client("s3")
    for key, n in DEFAULT_PLAN.items():
        for _ in range(n):
            s3.get_object(Bucket=args.bucket, Key=key, Range="bytes=0-0")["Body"].read()
        print(f"{key}: {n} accesses")
    print("Done - access pattern generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
