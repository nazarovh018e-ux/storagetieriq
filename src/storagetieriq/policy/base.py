"""
storagetieriq.policy.base
-------------------------
The tiering *decision* abstraction.

``TieringStrategy`` is the seam that lets you swap how a record's tier is
chosen without touching ingestion, costing, reporting, or the CLI:

    * RuleBasedStrategy  -> explicit age / access thresholds (explainable)
    * CostOptimalStrategy -> per-object break-even cost minimisation
    * (future) MlStrategy -> learned access-probability + cost model

Every strategy returns a *copy* of the input DataFrame with a ``tier``
column added; it must never mutate its input.

``TieringPolicy`` is the tunable configuration consumed by the
rule-based strategy.  It lives here (rather than in rule_based.py) because
the report generator and CLI reference it as the canonical "policy" type.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from storagetieriq.domain.models import (
    COLD,
    HOT,
    TIER_ORDER,
    WARM,
    validate_columns,
)


# ── Policy configuration (used by the rule-based strategy) ────────────────
@dataclass
class TieringPolicy:
    """Tunable thresholds for rule-based tiering.

    HOT criteria (any one true): age <= hot_age_days OR
    days_since_access <= hot_access_days OR access_count >= hot_min_accesses.

    WARM criteria (any one true, after excluding HOT): age <= warm_age_days
    OR days_since_access <= warm_access_days OR access_count >= warm_min_accesses.

    COLD: everything else.

    Overrides: backup data is forced COLD (if ``force_backup_cold``); files
    larger than ``large_file_threshold_mb`` may not enter HOT.
    """

    # HOT thresholds
    hot_age_days: int = 30
    hot_access_days: int = 7
    hot_min_accesses: int = 20

    # WARM thresholds
    warm_age_days: int = 180
    warm_access_days: int = 60
    warm_min_accesses: int = 3

    # Overrides
    force_backup_cold: bool = True
    large_file_threshold_mb: float = 1000.0

    # Label
    name: str = "default"

    def __post_init__(self) -> None:
        if self.hot_age_days >= self.warm_age_days:
            raise ValueError(
                f"hot_age_days ({self.hot_age_days}) must be < "
                f"warm_age_days ({self.warm_age_days})"
            )
        if self.hot_min_accesses <= self.warm_min_accesses:
            raise ValueError(
                f"hot_min_accesses ({self.hot_min_accesses}) must be > "
                f"warm_min_accesses ({self.warm_min_accesses})"
            )

    def describe(self) -> str:
        return "\n".join(
            [
                f"Policy: '{self.name}'",
                f"  HOT  -> age <= {self.hot_age_days}d  OR  "
                f"last-access <= {self.hot_access_days}d  OR  "
                f"accesses >= {self.hot_min_accesses}",
                f"  WARM -> age <= {self.warm_age_days}d  OR  "
                f"last-access <= {self.warm_access_days}d  OR  "
                f"accesses >= {self.warm_min_accesses}",
                "  COLD -> everything else",
                f"  Overrides: backup->COLD={self.force_backup_cold}, "
                f"large-file>{self.large_file_threshold_mb:.0f}MB->skip HOT",
            ]
        )


def tier_summary(classified: pd.DataFrame) -> pd.DataFrame:
    """Return a per-tier summary DataFrame.

    Strategy-agnostic: works on any DataFrame that already has a ``tier``
    column, regardless of which strategy produced it.
    """
    if "tier" not in classified.columns:
        raise ValueError("DataFrame must have a 'tier' column before summarising.")

    total_records = len(classified)
    total_mb = classified["size_mb"].sum()

    rows = []
    for tier in TIER_ORDER:
        sub = classified[classified["tier"] == tier]
        rows.append(
            {
                "tier": tier.upper(),
                "records": len(sub),
                "pct_records": len(sub) / total_records * 100 if total_records else 0,
                "total_gb": sub["size_mb"].sum() / 1024,
                "pct_gb": sub["size_mb"].sum() / total_mb * 100 if total_mb else 0,
                "avg_age_days": sub["age_days"].mean() if len(sub) else 0.0,
                "avg_accesses": sub["access_count"].mean() if len(sub) else 0.0,
            }
        )
    return pd.DataFrame(rows)


# ── Strategy abstraction ──────────────────────────────────────────────────
class TieringStrategy(ABC):
    """Decide a tier for every record in a DataFrame."""

    #: Human-readable label used in reports / dashboards.
    name: str = "abstract"

    @abstractmethod
    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of *df* with a ``tier`` column. Must not mutate *df*."""
        raise NotImplementedError

    # Shared helpers available to every concrete strategy ----------------
    def _validate(self, df: pd.DataFrame) -> None:
        validate_columns(df.columns)

    def tier_summary(self, classified: pd.DataFrame) -> pd.DataFrame:
        return tier_summary(classified)


__all__ = [
    "TieringPolicy",
    "TieringStrategy",
    "tier_summary",
    "HOT",
    "WARM",
    "COLD",
]
