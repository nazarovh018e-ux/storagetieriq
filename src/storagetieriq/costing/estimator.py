"""
storagetieriq.costing.estimator
--------------------------------
Estimate monthly storage costs per tier and savings vs a flat-SSD
baseline, plus sensitivity and cross-policy comparison helpers.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from storagetieriq.domain.models import TIER_ORDER
from storagetieriq.domain.pricing import PricingModel


class CostEstimator:
    """Compute monthly costs and savings for a classified DataFrame."""

    def __init__(self, pricing: Optional[PricingModel] = None) -> None:
        self.pricing: PricingModel = pricing or PricingModel()

    def estimate(self, classified: pd.DataFrame) -> dict:
        """Return per_tier, tiered_total, baseline, savings and total_gb."""
        if "tier" not in classified.columns:
            raise ValueError(
                "DataFrame must have a 'tier' column. Classify it first."
            )

        p = self.pricing
        total_gb = classified["size_mb"].sum() / 1024

        rows: list[dict] = []
        tiered_total = 0.0

        for tier in TIER_ORDER:
            sub = classified[classified["tier"] == tier]
            gb = sub["size_mb"].sum() / 1024

            if tier == "hot":
                storage_cost = gb * p.hot_storage_per_gb
                retrieval_cost = 0.0
                rate = p.hot_storage_per_gb
            elif tier == "warm":
                storage_cost = gb * p.warm_storage_per_gb
                retrieval_cost = (
                    gb * p.warm_monthly_retrieval_pct * p.warm_retrieval_per_gb
                )
                rate = p.warm_storage_per_gb
            else:
                storage_cost = gb * p.cold_storage_per_gb
                retrieval_cost = (
                    gb * p.cold_monthly_retrieval_pct * p.cold_retrieval_per_gb
                )
                rate = p.cold_storage_per_gb

            tier_total = storage_cost + retrieval_cost
            tiered_total += tier_total

            rows.append(
                {
                    "tier": tier.upper(),
                    "gb": gb,
                    "storage_$/gb": rate,
                    "storage_cost_$": storage_cost,
                    "retrieval_cost_$": retrieval_cost,
                    "total_cost_$": tier_total,
                }
            )

        per_tier_df = pd.DataFrame(rows)
        baseline = total_gb * p.baseline_per_gb
        monthly_savings = baseline - tiered_total
        savings_pct = (monthly_savings / baseline * 100) if baseline > 0 else 0.0
        annual_savings = monthly_savings * 12

        return {
            "per_tier": per_tier_df,
            "tiered_total": tiered_total,
            "baseline": baseline,
            "monthly_savings": monthly_savings,
            "savings_pct": savings_pct,
            "annual_savings": annual_savings,
            "total_gb": total_gb,
        }

    def print_report(self, result: dict) -> None:
        """Print a formatted cost report to the console."""
        print("\n" + "=" * 60)
        print("  COST ESTIMATE - Monthly Storage Bill")
        print("=" * 60)
        print(f"  Total data volume : {result['total_gb']:.2f} GB\n")
        print(
            result["per_tier"].to_string(
                index=False,
                float_format=lambda x: f"${x:,.4f}" if x < 1 else f"${x:,.2f}",
            )
        )
        print()
        print(f"  Tiered total   : ${result['tiered_total']:,.2f} / month")
        print(
            f"  Flat SSD cost  : ${result['baseline']:,.2f} / month  (baseline)"
        )
        print(
            f"  Monthly saving : ${result['monthly_savings']:,.2f}  "
            f"({result['savings_pct']:.1f}% reduction)"
        )
        print(f"  Annual saving  : ${result['annual_savings']:,.2f}")
        print("=" * 60)


def sensitivity_analysis(
    classified: pd.DataFrame,
    pricing: Optional[PricingModel] = None,
) -> pd.DataFrame:
    """Show how annual savings change as the hot-tier price varies."""
    pricing = pricing or PricingModel()
    scenarios: list[dict] = []

    for hot_price in [0.05, 0.08, 0.092, 0.12, 0.20, 0.25]:
        p = PricingModel(
            hot_storage_per_gb=hot_price,
            baseline_per_gb=hot_price,
            name=f"hot@${hot_price}",
        )
        result = CostEstimator(p).estimate(classified)
        scenarios.append(
            {
                "hot_$/gb": hot_price,
                "baseline_$/mo": result["baseline"],
                "tiered_$/mo": result["tiered_total"],
                "monthly_saving": result["monthly_savings"],
                "annual_saving": result["annual_savings"],
                "saving_%": result["savings_pct"],
            }
        )

    return pd.DataFrame(scenarios)


def compare_policies(
    classified_by_policy: dict[str, pd.DataFrame],
    pricing: Optional[PricingModel] = None,
) -> pd.DataFrame:
    """Compare cost results across multiple pre-classified DataFrames.

    Parameters
    ----------
    classified_by_policy:
        Mapping of ``{policy_name: classified_df}``.

    Returns
    -------
    DataFrame sorted by annual savings (descending).
    """
    pricing = pricing or PricingModel()
    estimator = CostEstimator(pricing)
    rows: list[dict] = []

    for policy_name, classified in classified_by_policy.items():
        result = estimator.estimate(classified)
        rows.append(
            {
                "policy": policy_name,
                "total_gb": result["total_gb"],
                "baseline_$/mo": result["baseline"],
                "tiered_$/mo": result["tiered_total"],
                "monthly_saving_$": result["monthly_savings"],
                "saving_%": result["savings_pct"],
                "annual_saving_$": result["annual_savings"],
            }
        )

    return pd.DataFrame(rows).sort_values("annual_saving_$", ascending=False)


__all__ = ["CostEstimator", "sensitivity_analysis", "compare_policies"]
