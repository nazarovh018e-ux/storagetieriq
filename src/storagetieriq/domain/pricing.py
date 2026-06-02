"""
storagetieriq.domain.pricing
-----------------------------
The :class:`PricingModel` value object.

Storage cost per GB per month and retrieval cost per GB, plus the
flat-SSD baseline used to compute savings.  Defaults approximate
AWS / GCP rates:

    Hot  -> EBS gp3 SSD        ~$0.08-0.10/GB/mo
    Warm -> S3 Standard-IA     ~$0.0125/GB/mo  (+ $0.01/GB retrieval)
    Cold -> S3 Glacier Instant ~$0.004/GB/mo   (+ $0.03/GB retrieval)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PricingModel:
    """Immutable-ish pricing configuration validated on construction."""

    hot_storage_per_gb: float = 0.092
    warm_storage_per_gb: float = 0.0125
    cold_storage_per_gb: float = 0.004

    hot_retrieval_per_gb: float = 0.0
    warm_retrieval_per_gb: float = 0.01
    cold_retrieval_per_gb: float = 0.03

    baseline_per_gb: float = 0.092

    # Fraction of each tier's data assumed to be retrieved per month
    # (used by the simple monthly cost estimate).
    warm_monthly_retrieval_pct: float = 0.05
    cold_monthly_retrieval_pct: float = 0.01

    name: str = "aws_2024"

    def __post_init__(self) -> None:
        for attr in (
            "hot_storage_per_gb",
            "warm_storage_per_gb",
            "cold_storage_per_gb",
            "baseline_per_gb",
        ):
            if getattr(self, attr) <= 0:
                raise ValueError(f"{attr} must be > 0, got {getattr(self, attr)}")
        if not (
            self.cold_storage_per_gb
            < self.warm_storage_per_gb
            < self.hot_storage_per_gb
        ):
            raise ValueError(
                "Expected cold < warm < hot storage prices; "
                f"got cold={self.cold_storage_per_gb}, "
                f"warm={self.warm_storage_per_gb}, hot={self.hot_storage_per_gb}"
            )

    # ── Helpers used by the cost-optimal strategy ────────────────────────
    def storage_price(self, tier: str) -> float:
        """$/GB/month for *tier*."""
        return {
            "hot": self.hot_storage_per_gb,
            "warm": self.warm_storage_per_gb,
            "cold": self.cold_storage_per_gb,
        }[tier]

    def retrieval_price(self, tier: str) -> float:
        """$/GB per retrieval for *tier*."""
        return {
            "hot": self.hot_retrieval_per_gb,
            "warm": self.warm_retrieval_per_gb,
            "cold": self.cold_retrieval_per_gb,
        }[tier]
