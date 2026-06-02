"""
storagetieriq.policy.cost_optimal
---------------------------------
Cost-optimal tiering strategy (break-even minimisation).

Instead of "is this old?", this strategy answers the economically correct
question: **which tier minimises the expected total cost of this object
over a planning horizon, given how often we expect it to be retrieved?**

For each object and each candidate tier *t* over a horizon of *H* months:

    storage_cost(t)   = size_gb * storage_price(t) * H
    retrieval_cost(t) = size_gb * retrieval_price(t) * E[retrievals over H]
    total(t)          = storage_cost(t) + retrieval_cost(t)

The object is assigned ``argmin_t total(t)``.  Rarely-accessed large data
falls to COLD (storage dominates); frequently-accessed data stays HOT
(cold retrieval fees would dominate).

Expected retrievals are predicted with a transparent, ML-free estimator:

    rate_per_month = access_count / max(age_months, 1)        # lifetime avg
    recency_factor = exp(-days_since_access / decay_days)     # recent = hotter
    E[retrievals]  = rate_per_month * recency_factor * H

Swap this estimator for a learned model later without changing the
decision logic -- prediction and decision are deliberately separated.
"""

from __future__ import annotations

from typing import Iterable, Optional

import numpy as np
import pandas as pd

from storagetieriq.domain.models import COLD, HOT, TIER_ORDER, WARM
from storagetieriq.domain.pricing import PricingModel
from storagetieriq.policy.base import TieringStrategy

# Rank used to enforce a "never below HOT" floor for protected types.
_TIER_RANK = {HOT: 0, WARM: 1, COLD: 2}


class CostOptimalStrategy(TieringStrategy):
    """Assign each record to the expected-cost-minimising tier.

    Parameters
    ----------
    pricing:
        Pricing model providing per-tier storage and retrieval prices.
    horizon_months:
        Planning horizon over which costs are compared.
    recency_decay_days:
        Time constant for the recency factor; smaller => recency matters more.
    archive_only_types:
        Data types always forced to COLD (e.g. ``{"backup"}``).
    hot_protected_types:
        Data types that may never be placed below HOT (SLA guarantee).
    """

    def __init__(
        self,
        pricing: Optional[PricingModel] = None,
        horizon_months: int = 12,
        recency_decay_days: float = 90.0,
        archive_only_types: Optional[Iterable[str]] = ("backup",),
        hot_protected_types: Optional[Iterable[str]] = None,
        name: str = "cost_optimal",
    ) -> None:
        if horizon_months <= 0:
            raise ValueError(f"horizon_months must be > 0, got {horizon_months}")
        if recency_decay_days <= 0:
            raise ValueError(
                f"recency_decay_days must be > 0, got {recency_decay_days}"
            )
        self.pricing = pricing or PricingModel()
        self.horizon_months = horizon_months
        self.recency_decay_days = recency_decay_days
        self.archive_only_types = set(archive_only_types or [])
        self.hot_protected_types = set(hot_protected_types or [])
        self.name = name

    def _expected_retrievals(self, df: pd.DataFrame) -> pd.Series:
        """Vectorised E[retrievals over horizon] for every row."""
        age_months = np.maximum(df["age_days"] / 30.0, 1.0)
        rate_per_month = df["access_count"] / age_months
        recency = np.exp(-df["days_since_access"] / self.recency_decay_days)
        return rate_per_month * recency * self.horizon_months

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate(df)
        out = df.copy()

        gb = out["size_mb"] / 1024.0
        expected_retrievals = self._expected_retrievals(out)
        H = self.horizon_months

        # Total expected cost per tier (Series aligned to rows).
        costs = {}
        for tier in TIER_ORDER:
            storage = gb * self.pricing.storage_price(tier) * H
            retrieval = (
                gb * self.pricing.retrieval_price(tier) * expected_retrievals
            )
            costs[tier] = storage + retrieval

        cost_matrix = pd.concat(
            [costs[t].rename(t) for t in TIER_ORDER], axis=1
        )
        # argmin across the three tier columns -> chosen tier label.
        out["tier"] = cost_matrix.idxmin(axis=1)

        # Expose the economics for reporting / debugging.
        out["expected_retrievals"] = expected_retrievals.round(3)
        out["chosen_tier_cost_$"] = cost_matrix.min(axis=1).round(4)

        # ── Constraints / overrides ──────────────────────────────────────
        if self.hot_protected_types:
            protected = out["data_type"].isin(self.hot_protected_types)
            below_hot = out["tier"].map(_TIER_RANK) > _TIER_RANK[HOT]
            out.loc[protected & below_hot, "tier"] = HOT

        if self.archive_only_types:
            out.loc[out["data_type"].isin(self.archive_only_types), "tier"] = COLD

        return out


__all__ = ["CostOptimalStrategy"]
