"""
StorageTierIQ -- Cost-Optimized Storage Tiering System.

A modular toolkit that ingests storage records, classifies them into
HOT / WARM / COLD tiers via pluggable strategies, estimates costs, and
plans (or executes) migrations.

Public API (stable):

    from storagetieriq import (
        generate_dataset, SyntheticSource, CsvSource,
        TieringPolicy, RuleBasedStrategy, CostOptimalStrategy, POLICIES,
        PricingModel, CostEstimator, sensitivity_analysis, compare_policies,
        generate_report,
        build_migration_plan, DryRunExecutor,
        Tier, HOT, WARM, COLD,
    )
"""

from __future__ import annotations

__version__ = "1.0.0"

from storagetieriq.costing.carbon import CarbonModel, estimate_carbon
from storagetieriq.costing.estimator import (
    CostEstimator,
    compare_policies,
    sensitivity_analysis,
)
from storagetieriq.domain.models import COLD, HOT, WARM, Tier
from storagetieriq.domain.pricing import PricingModel
from storagetieriq.ingestion.csv_source import CsvSource
from storagetieriq.ingestion.synthetic import (
    DATA_TYPES,
    SyntheticSource,
    generate_dataset,
    summarize_dataset,
)
from storagetieriq.migration.base import build_migration_plan
from storagetieriq.migration.dry_run import DryRunExecutor
from storagetieriq.policy.base import TieringPolicy, TieringStrategy, tier_summary
from storagetieriq.policy.cost_optimal import CostOptimalStrategy
from storagetieriq.policy.rule_based import POLICIES, PolicyEngine, RuleBasedStrategy
from storagetieriq.reporting.text_report import generate_report

__all__ = [
    "__version__",
    # ingestion
    "generate_dataset",
    "summarize_dataset",
    "SyntheticSource",
    "CsvSource",
    "DATA_TYPES",
    # policy
    "TieringStrategy",
    "TieringPolicy",
    "RuleBasedStrategy",
    "PolicyEngine",
    "CostOptimalStrategy",
    "POLICIES",
    "tier_summary",
    # costing
    "PricingModel",
    "CostEstimator",
    "sensitivity_analysis",
    "compare_policies",
    "CarbonModel",
    "estimate_carbon",
    # reporting
    "generate_report",
    # migration
    "build_migration_plan",
    "DryRunExecutor",
    # domain
    "Tier",
    "HOT",
    "WARM",
    "COLD",
]
