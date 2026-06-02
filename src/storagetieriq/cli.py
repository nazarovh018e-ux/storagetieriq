"""
storagetieriq.cli
-----------------
Command-line entry point. Orchestrates ingestion -> classification ->
costing -> reporting -> (dry-run) migration using only the public
abstractions, so swapping a strategy or data source needs no CLI changes.

Usage:
    storagetieriq                              # defaults
    storagetieriq --strategy cost-optimal      # break-even strategy
    storagetieriq --policy aggressive          # rule-based preset
    storagetieriq --records 50000 --hot-days 14
    storagetieriq --input my_inventory.csv     # real data from CSV
    storagetieriq --no-dashboard
    storagetieriq --plan-migration             # show dry-run migration plan
"""

from __future__ import annotations

import argparse
import os

from storagetieriq.costing.carbon import CarbonModel, estimate_carbon
from storagetieriq.costing.estimator import (
    CostEstimator,
    sensitivity_analysis,
)
from storagetieriq.domain.pricing import PricingModel
from storagetieriq.ingestion.csv_source import CsvSource
from storagetieriq.ingestion.synthetic import SyntheticSource, summarize_dataset
from storagetieriq.migration.base import build_migration_plan
from storagetieriq.migration.dry_run import DryRunExecutor
from storagetieriq.policy.cost_optimal import CostOptimalStrategy
from storagetieriq.policy.rule_based import POLICIES, RuleBasedStrategy
from storagetieriq.reporting.text_report import generate_report


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="storagetieriq",
        description="StorageTierIQ - Cost-Optimized Storage Tiering System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--records", type=int, default=10_000,
                   help="Synthetic records to generate (default: 10000)")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    p.add_argument("--input", default=None,
                   help="Read real records from this CSV instead of generating")

    p.add_argument("--strategy", choices=["rule", "cost-optimal"], default="rule",
                   help="Tiering strategy (default: rule)")
    p.add_argument("--policy",
                   choices=["default", "aggressive", "conservative", "custom"],
                   default="default", help="Rule-based preset")
    p.add_argument("--horizon-months", type=int, default=12,
                   help="Planning horizon for cost-optimal strategy")

    # Rule-based overrides
    p.add_argument("--hot-days", type=int, default=None)
    p.add_argument("--warm-days", type=int, default=None)
    p.add_argument("--hot-access", type=int, default=None)
    p.add_argument("--hot-price", type=float, default=None)

    p.add_argument("--plan-migration", action="store_true",
                   help="Build and print a dry-run migration plan")
    p.add_argument("--no-dashboard", action="store_true",
                   help="Skip dashboard PNG generation")
    p.add_argument("--output-dir", default=".", help="Output directory")
    return p.parse_args(argv)


def _build_strategy(args):
    """Return (strategy, policy_label) from parsed args."""
    if args.strategy == "cost-optimal":
        pricing = PricingModel()
        if args.hot_price is not None:
            pricing.hot_storage_per_gb = args.hot_price
            pricing.baseline_per_gb = args.hot_price
        strat = CostOptimalStrategy(pricing, horizon_months=args.horizon_months)
        return strat, strat.name

    policy = POLICIES.get(args.policy, POLICIES["default"])
    if args.hot_days is not None:
        policy.hot_age_days = args.hot_days
    if args.warm_days is not None:
        policy.warm_age_days = args.warm_days
    if args.hot_access is not None:
        policy.hot_access_days = args.hot_access
    if args.policy == "custom":
        policy.name = "custom"
    return RuleBasedStrategy(policy), policy.name


def main(argv=None) -> None:
    args = parse_args(argv)
    os.makedirs(args.output_dir, exist_ok=True)

    print("\n" + "=" * 60)
    print("  StorageTierIQ - Storage Tiering Cost Analyser")
    print("=" * 60)

    # 1. Ingest -----------------------------------------------------------
    if args.input:
        print(f"\n[1/5] Loading records from {args.input} ...")
        source = CsvSource(args.input)
    else:
        print(f"\n[1/5] Generating {args.records:,} synthetic records ...")
        source = SyntheticSource(args.records, seed=args.seed)
    df = source.load_validated()
    summarize_dataset(df)

    csv_path = os.path.join(args.output_dir, "storage_records.csv")
    df.to_csv(csv_path, index=False)
    print(f"      Saved raw dataset -> {csv_path}")

    # 2. Build strategy ---------------------------------------------------
    print(f"\n[2/5] Building '{args.strategy}' strategy ...")
    strategy, policy_label = _build_strategy(args)

    # 3. Classify ---------------------------------------------------------
    print("\n[3/5] Classifying records ...")
    classified = strategy.classify(df)
    summary = strategy.tier_summary(classified)
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    classified_path = os.path.join(args.output_dir, "classified_records.csv")
    classified.to_csv(classified_path, index=False)
    print(f"\n      Saved classified dataset -> {classified_path}")

    # 4. Estimate costs ---------------------------------------------------
    print("\n[4/5] Estimating costs ...")
    pricing = PricingModel()
    if args.hot_price is not None:
        pricing.hot_storage_per_gb = args.hot_price
        pricing.baseline_per_gb = args.hot_price
    estimator = CostEstimator(pricing)
    result = estimator.estimate(classified)
    estimator.print_report(result)
    sens_df = sensitivity_analysis(classified, pricing)

    # Energy + carbon footprint
    carbon = estimate_carbon(classified, CarbonModel())
    print("\n" + "=" * 60)
    print("  ENERGY & CARBON FOOTPRINT")
    print("=" * 60)
    print(f"  Flat-SSD energy : {carbon['baseline_kwh_month']:,.1f} kWh / month")
    print(f"  Tiered energy   : {carbon['tiered_kwh_month']:,.1f} kWh / month")
    print(f"  Energy saved    : {carbon['kwh_saved_month']:,.1f} kWh / month")
    print(
        f"  CO2 avoided     : {carbon['co2_saved_kg_month']:,.2f} kg / month  "
        f"({carbon['co2_savings_pct']:.1f}% lower)"
    )
    print(f"  CO2 avoided/yr  : {carbon['co2_saved_kg_year']:,.2f} kg / year")
    print("=" * 60)

    # 5. Outputs ----------------------------------------------------------
    print("\n[5/5] Generating outputs ...")

    # For the text report we need a TieringPolicy to describe rules. For the
    # cost-optimal strategy we hand it the default policy purely for the
    # "rules" section header; the numbers come from the classification.
    report_policy = getattr(strategy, "policy", POLICIES["default"])
    report_path = os.path.join(args.output_dir, "tiering_report.txt")
    generate_report(classified, result, report_policy, pricing,
                    output_file=report_path)

    if args.plan_migration:
        plan = build_migration_plan(classified)
        executor = DryRunExecutor(verbose=True)
        outcome = executor.execute(plan)
        print("\n  " + plan.summary().replace("\n", "\n  "))
        print("  " + outcome.summary())

    if not args.no_dashboard:
        try:
            from storagetieriq.reporting.dashboard import build_dashboard

            dash_path = os.path.join(args.output_dir,
                                     "storage_tiering_dashboard.png")
            build_dashboard(classified, result, sens_df,
                            policy_name=policy_label, output_path=dash_path)
            print(f"      Dashboard saved     -> {dash_path}")
        except ImportError as e:
            print(f"      [WARNING] Dashboard skipped: {e}")
    else:
        print("      Dashboard skipped (--no-dashboard).")

    # Final summary -------------------------------------------------------
    print("\n" + "=" * 60)
    print("  Analysis complete!")
    print(f"  Total records   : {len(classified):,}")
    print(f"  Total data      : {result['total_gb']:.2f} GB")
    print(f"  Monthly saving  : ${result['monthly_savings']:,.2f}  "
          f"({result['savings_pct']:.1f}%)")
    print(f"  Annual saving   : ${result['annual_savings']:,.2f}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
