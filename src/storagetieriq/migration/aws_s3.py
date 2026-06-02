"""
storagetieriq.migration.aws_s3
------------------------------
OPTIONAL real-storage executor for AWS S3.

This module imports cleanly even without ``boto3`` installed -- the
dependency is imported lazily inside :meth:`execute`, so the rest of the
package (and the test suite) never breaks.  To use it you need:

    pip install boto3
    # plus configured AWS credentials and a column mapping each record
    # to its S3 bucket/key.

It maps StorageTierIQ tiers to S3 storage classes:

    hot  -> STANDARD
    warm -> STANDARD_IA
    cold -> GLACIER

A move is performed as an in-place copy with a new ``StorageClass`` (the
standard S3 idiom for transitioning an existing object).
"""

from __future__ import annotations

from storagetieriq.migration.base import (
    MigrationExecutor,
    MigrationPlan,
    MigrationResult,
)

TIER_TO_S3_CLASS = {
    "hot": "STANDARD",
    "warm": "STANDARD_IA",
    "cold": "GLACIER",
}


class AwsS3Executor(MigrationExecutor):
    """Transition real S3 objects to the storage class implied by their tier.

    The plan's ``moves`` DataFrame must contain ``bucket`` and ``key``
    columns identifying each object.
    """

    dry_run = False

    def __init__(self, bucket_col: str = "bucket", key_col: str = "key") -> None:
        self.bucket_col = bucket_col
        self.key_col = key_col

    def execute(self, plan: MigrationPlan) -> MigrationResult:
        try:
            import boto3  # noqa: WPS433 (lazy, optional dependency)
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "AwsS3Executor requires boto3. Install it with `pip install boto3`."
            ) from exc

        moves = plan.moves
        for col in (self.bucket_col, self.key_col):
            if col not in moves.columns:
                raise ValueError(
                    f"moves DataFrame is missing required column '{col}'. "
                    "Real S3 migration needs bucket/key identifiers per object."
                )

        s3 = boto3.client("s3")
        executed = failed = 0
        gb_moved = 0.0

        for _, row in moves.iterrows():  # pragma: no cover - needs network/creds
            bucket = row[self.bucket_col]
            key = row[self.key_col]
            storage_class = TIER_TO_S3_CLASS[row["tier"]]
            try:
                s3.copy_object(
                    Bucket=bucket,
                    Key=key,
                    CopySource={"Bucket": bucket, "Key": key},
                    StorageClass=storage_class,
                    MetadataDirective="COPY",
                )
                executed += 1
                gb_moved += float(row["size_mb"]) / 1024
            except Exception:  # noqa: BLE001 - record and continue
                failed += 1

        return MigrationResult(
            executed=executed, failed=failed, gb_moved=gb_moved, dry_run=False
        )


__all__ = ["AwsS3Executor", "TIER_TO_S3_CLASS"]
