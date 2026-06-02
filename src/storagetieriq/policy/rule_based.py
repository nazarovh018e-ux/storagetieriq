"""
storagetieriq.policy.rule_based
-------------------------------
Rule-based tiering strategy.

Classifies each record into HOT / WARM / COLD using the configurable
thresholds in :class:`TieringPolicy`.  Fully vectorised (pandas boolean
masks) so it scales to millions of rows.

``PolicyEngine`` is kept as a backwards-compatible alias for
``RuleBasedStrategy`` so existing code / notebooks keep working.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from storagetieriq.domain.models import COLD, HOT, WARM
from storagetieriq.policy.base import TieringPolicy, TieringStrategy


class RuleBasedStrategy(TieringStrategy):
    """Apply a :class:`TieringPolicy` to a DataFrame of storage records."""

    def __init__(self, policy: Optional[TieringPolicy] = None) -> None:
        self.policy: TieringPolicy = policy or TieringPolicy()
        self.name = self.policy.name

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of *df* with a ``tier`` column added.

        The original DataFrame is **not** modified.
        """
        self._validate(df)
        p = self.policy
        out = df.copy()

        age = out["age_days"]
        since = out["days_since_access"]
        count = out["access_count"]
        dtype = out["data_type"]
        size = out["size_mb"]

        # Default everything to COLD.
        out["tier"] = COLD

        # WARM first so HOT can overwrite it.
        warm_mask = (
            (age <= p.warm_age_days)
            | (since <= p.warm_access_days)
            | (count >= p.warm_min_accesses)
        )
        out.loc[warm_mask, "tier"] = WARM

        # HOT (overwrites WARM where criteria met).
        hot_mask = (
            (age <= p.hot_age_days)
            | (since <= p.hot_access_days)
            | (count >= p.hot_min_accesses)
        )
        # Large files skip HOT -> at most WARM.
        large_file_mask = size > p.large_file_threshold_mb
        hot_mask = hot_mask & ~large_file_mask
        out.loc[hot_mask, "tier"] = HOT

        # Override: backup data always cold.
        if p.force_backup_cold:
            out.loc[dtype == "backup", "tier"] = COLD

        return out


# Backwards-compatible alias.
PolicyEngine = RuleBasedStrategy


# ── Preset policies ───────────────────────────────────────────────────────
POLICIES: dict[str, TieringPolicy] = {
    "aggressive": TieringPolicy(
        name="aggressive",
        hot_age_days=14,
        hot_access_days=3,
        hot_min_accesses=50,
        warm_age_days=90,
        warm_access_days=30,
        warm_min_accesses=5,
    ),
    "default": TieringPolicy(name="default"),
    "conservative": TieringPolicy(
        name="conservative",
        hot_age_days=60,
        hot_access_days=30,
        hot_min_accesses=10,
        warm_age_days=365,
        warm_access_days=180,
        warm_min_accesses=2,
    ),
}


__all__ = ["RuleBasedStrategy", "PolicyEngine", "POLICIES"]
