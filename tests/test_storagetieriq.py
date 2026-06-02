"""
tests/test_storagetieriq.py
---------------------------
Unit tests for StorageTierIQ.

Run with:
    pytest                 # or: pytest tests/ -v --cov=storagetieriq
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from storagetieriq.costing.carbon import CarbonModel, estimate_carbon
from storagetieriq.costing.estimator import (
    CostEstimator,
    compare_policies,
    sensitivity_analysis,
)
from storagetieriq.domain.models import COLD, HOT, WARM, Tier
from storagetieriq.domain.pricing import PricingModel
from storagetieriq.ingestion.synthetic import (
    DATA_TYPES,
    SyntheticSource,
    generate_dataset,
)
from storagetieriq.migration.base import build_migration_plan
from storagetieriq.migration.dry_run import DryRunExecutor
from storagetieriq.policy.base import TieringPolicy
from storagetieriq.policy.cost_optimal import CostOptimalStrategy
from storagetieriq.policy.rule_based import (
    POLICIES,
    PolicyEngine,
    RuleBasedStrategy,
)


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def small_df() -> pd.DataFrame:
    return generate_dataset(500, seed=0)


@pytest.fixture(scope="module")
def classified_df(small_df) -> pd.DataFrame:
    return RuleBasedStrategy(POLICIES["default"]).classify(small_df)


@pytest.fixture
def default_policy() -> TieringPolicy:
    return TieringPolicy(name="test")


@pytest.fixture
def default_pricing() -> PricingModel:
    return PricingModel()


# ── data_generator tests ────────────────────────────────────────────────────
class TestDataGenerator:
    def test_row_count(self):
        df = generate_dataset(200, seed=1)
        assert len(df) == 200

    def test_required_columns(self):
        df = generate_dataset(50, seed=2)
        expected = {
            "record_id", "data_type", "size_mb", "created_at",
            "last_accessed", "access_count", "age_days", "days_since_access",
        }
        assert expected.issubset(set(df.columns))

    def test_reproducible_with_seed(self):
        ref = datetime(2024, 1, 1)
        df1 = generate_dataset(100, seed=42, reference_date=ref)
        df2 = generate_dataset(100, seed=42, reference_date=ref)
        cols = [c for c in df1.columns if c != "record_id"]
        pd.testing.assert_frame_equal(
            df1[cols].reset_index(drop=True),
            df2[cols].reset_index(drop=True),
        )

    def test_different_seeds_differ(self):
        df1 = generate_dataset(100, seed=1)
        df2 = generate_dataset(100, seed=2)
        assert not df1["size_mb"].equals(df2["size_mb"])

    def test_age_days_in_range(self):
        df = generate_dataset(1_000, seed=3)
        assert df["age_days"].min() >= 1
        assert df["age_days"].max() <= 1095

    def test_days_since_access_le_age(self):
        df = generate_dataset(500, seed=4)
        assert (df["days_since_access"] <= df["age_days"]).all()

    def test_no_negative_sizes(self):
        df = generate_dataset(500, seed=5)
        assert (df["size_mb"] > 0).all()

    def test_data_types_are_known(self):
        df = generate_dataset(500, seed=6)
        assert set(df["data_type"].unique()).issubset(set(DATA_TYPES))

    def test_unique_record_ids(self):
        df = generate_dataset(500, seed=7)
        assert df["record_id"].nunique() == len(df)

    def test_custom_reference_date(self):
        ref = datetime(2023, 1, 1)
        df = generate_dataset(100, seed=8, reference_date=ref)
        assert (df["created_at"] <= ref).all()

    def test_invalid_n_records_raises(self):
        with pytest.raises(ValueError):
            generate_dataset(0)

    def test_synthetic_source_validates(self):
        df = SyntheticSource(100, seed=9).load_validated()
        assert len(df) == 100


# ── TieringPolicy tests ─────────────────────────────────────────────────────
class TestTieringPolicy:
    def test_default_instantiates(self):
        assert TieringPolicy().name == "default"

    def test_invalid_hot_ge_warm_raises(self):
        with pytest.raises(ValueError):
            TieringPolicy(hot_age_days=200, warm_age_days=100)

    def test_invalid_accesses_raises(self):
        with pytest.raises(ValueError):
            TieringPolicy(hot_min_accesses=2, warm_min_accesses=5)

    def test_describe_returns_string(self, default_policy):
        desc = default_policy.describe()
        assert isinstance(desc, str)
        assert "HOT" in desc and "WARM" in desc and "COLD" in desc

    def test_preset_policies_exist(self):
        for name in ["default", "aggressive", "conservative"]:
            assert name in POLICIES
            assert isinstance(POLICIES[name], TieringPolicy)


# ── RuleBasedStrategy tests ──────────────────────────────────────────────────
class TestRuleBasedStrategy:
    def test_policy_engine_alias(self):
        assert PolicyEngine is RuleBasedStrategy

    def test_classify_returns_copy(self, small_df):
        result = RuleBasedStrategy().classify(small_df)
        assert "tier" not in small_df.columns, "classify() must not mutate input"
        assert "tier" in result.columns

    def test_tier_values_are_valid(self, classified_df):
        assert set(classified_df["tier"].unique()).issubset({HOT, WARM, COLD})

    def test_all_records_get_a_tier(self, small_df, classified_df):
        assert len(classified_df) == len(small_df)
        assert classified_df["tier"].notna().all()

    def test_backup_always_cold(self, classified_df):
        backup_rows = classified_df[classified_df["data_type"] == "backup"]
        assert (backup_rows["tier"] == COLD).all()

    def test_very_recent_data_is_hot(self):
        df = pd.DataFrame([{
            "record_id": "abc", "data_type": "log", "size_mb": 1.0,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None), "last_accessed": datetime.now(timezone.utc).replace(tzinfo=None),
            "access_count": 100, "age_days": 1, "days_since_access": 0,
        }])
        assert RuleBasedStrategy().classify(df).iloc[0]["tier"] == HOT

    def test_large_file_not_in_hot(self):
        df = pd.DataFrame([{
            "record_id": "xyz", "data_type": "media", "size_mb": 2000.0,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None), "last_accessed": datetime.now(timezone.utc).replace(tzinfo=None),
            "access_count": 999, "age_days": 1, "days_since_access": 0,
        }])
        assert RuleBasedStrategy().classify(df).iloc[0]["tier"] != HOT

    def test_old_infrequent_data_is_cold(self):
        df = pd.DataFrame([{
            "record_id": "old", "data_type": "log", "size_mb": 5.0,
            "created_at": datetime(2020, 1, 1),
            "last_accessed": datetime(2020, 6, 1),
            "access_count": 1, "age_days": 1000, "days_since_access": 900,
        }])
        assert RuleBasedStrategy().classify(df).iloc[0]["tier"] == COLD

    def test_missing_column_raises(self):
        bad_df = pd.DataFrame([{"age_days": 10, "size_mb": 5.0}])
        with pytest.raises(ValueError, match="missing required columns"):
            RuleBasedStrategy().classify(bad_df)

    def test_tier_summary_has_all_tiers(self, classified_df):
        summary = RuleBasedStrategy().tier_summary(classified_df)
        assert set(summary["tier"].str.lower()) == {HOT, WARM, COLD}

    def test_tier_summary_pct_sums_to_100(self, classified_df):
        summary = RuleBasedStrategy().tier_summary(classified_df)
        assert abs(summary["pct_records"].sum() - 100.0) < 1e-6
        assert abs(summary["pct_gb"].sum() - 100.0) < 1e-6

    def test_preset_policies_produce_different_distributions(self, small_df):
        distributions = {}
        for name, policy in POLICIES.items():
            classified = RuleBasedStrategy(policy).classify(small_df)
            distributions[name] = (
                classified["tier"].value_counts(normalize=True).to_dict()
            )
        assert (
            distributions["aggressive"].get(COLD, 0)
            >= distributions["conservative"].get(COLD, 0)
        )


# ── CostOptimalStrategy tests (new) ──────────────────────────────────────────
class TestCostOptimalStrategy:
    def test_classify_returns_copy(self, small_df):
        result = CostOptimalStrategy().classify(small_df)
        assert "tier" not in small_df.columns
        assert "tier" in result.columns

    def test_tier_values_are_valid(self, small_df):
        result = CostOptimalStrategy().classify(small_df)
        assert set(result["tier"].unique()).issubset({HOT, WARM, COLD})

    def test_all_records_get_a_tier(self, small_df):
        result = CostOptimalStrategy().classify(small_df)
        assert result["tier"].notna().all()

    def test_backup_forced_cold(self, small_df):
        result = CostOptimalStrategy(archive_only_types=("backup",)).classify(small_df)
        backup = result[result["data_type"] == "backup"]
        assert (backup["tier"] == COLD).all()

    def test_hot_protected_types_never_below_hot(self, small_df):
        result = CostOptimalStrategy(
            hot_protected_types=("transaction",)
        ).classify(small_df)
        protected = result[result["data_type"] == "transaction"]
        assert (protected["tier"] == HOT).all()

    def test_frequently_accessed_data_is_hot(self):
        df = pd.DataFrame([{
            "record_id": "freq", "data_type": "log", "size_mb": 1.0,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None), "last_accessed": datetime.now(timezone.utc).replace(tzinfo=None),
            "access_count": 1000, "age_days": 30, "days_since_access": 0,
        }])
        assert CostOptimalStrategy().classify(df).iloc[0]["tier"] == HOT

    def test_rarely_accessed_large_data_is_cold(self):
        df = pd.DataFrame([{
            "record_id": "rare", "data_type": "media", "size_mb": 800.0,
            "created_at": datetime(2021, 1, 1),
            "last_accessed": datetime(2021, 2, 1),
            "access_count": 1, "age_days": 900, "days_since_access": 850,
        }])
        assert CostOptimalStrategy().classify(df).iloc[0]["tier"] == COLD

    def test_invalid_horizon_raises(self):
        with pytest.raises(ValueError):
            CostOptimalStrategy(horizon_months=0)

    def test_adds_economics_columns(self, small_df):
        result = CostOptimalStrategy().classify(small_df)
        assert "expected_retrievals" in result.columns
        assert "chosen_tier_cost_$" in result.columns

    def test_cost_optimal_saves_money(self, small_df, default_pricing):
        result = CostOptimalStrategy().classify(small_df)
        est = CostEstimator(default_pricing).estimate(result)
        assert est["monthly_savings"] > 0


# ── CostEstimator tests ──────────────────────────────────────────────────────
class TestCostEstimator:
    def test_estimate_returns_expected_keys(self, classified_df, default_pricing):
        result = CostEstimator(default_pricing).estimate(classified_df)
        for key in ["per_tier", "tiered_total", "baseline", "monthly_savings",
                    "savings_pct", "annual_savings", "total_gb"]:
            assert key in result

    def test_tiered_total_lt_baseline(self, classified_df, default_pricing):
        result = CostEstimator(default_pricing).estimate(classified_df)
        assert result["tiered_total"] < result["baseline"]

    def test_savings_positive(self, classified_df, default_pricing):
        result = CostEstimator(default_pricing).estimate(classified_df)
        assert result["monthly_savings"] > 0
        assert result["annual_savings"] == pytest.approx(
            result["monthly_savings"] * 12
        )

    def test_savings_pct_in_range(self, classified_df, default_pricing):
        result = CostEstimator(default_pricing).estimate(classified_df)
        assert 0 < result["savings_pct"] < 100

    def test_per_tier_has_three_rows(self, classified_df, default_pricing):
        result = CostEstimator(default_pricing).estimate(classified_df)
        assert len(result["per_tier"]) == 3

    def test_total_gb_matches_data(self, classified_df, default_pricing):
        result = CostEstimator(default_pricing).estimate(classified_df)
        expected_gb = classified_df["size_mb"].sum() / 1024
        assert result["total_gb"] == pytest.approx(expected_gb)

    def test_aggressive_policy_saves_more(self, small_df, default_pricing):
        results = {}
        for name, policy in POLICIES.items():
            classified = RuleBasedStrategy(policy).classify(small_df)
            results[name] = CostEstimator(default_pricing).estimate(classified)
        assert (
            results["aggressive"]["monthly_savings"]
            >= results["conservative"]["monthly_savings"]
        )

    def test_sensitivity_analysis_returns_dataframe(self, classified_df, default_pricing):
        df = sensitivity_analysis(classified_df, default_pricing)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "hot_$/gb" in df.columns
        assert "annual_saving" in df.columns

    def test_sensitivity_savings_increase_with_hot_price(self, classified_df, default_pricing):
        df = sensitivity_analysis(classified_df, default_pricing).sort_values("hot_$/gb")
        savings = df["annual_saving"].tolist()
        assert savings == sorted(savings)


# ── PricingModel tests ───────────────────────────────────────────────────────
class TestPricingModel:
    def test_default_instantiates(self):
        p = PricingModel()
        assert p.hot_storage_per_gb > p.warm_storage_per_gb > p.cold_storage_per_gb

    def test_zero_price_raises(self):
        with pytest.raises(ValueError):
            PricingModel(hot_storage_per_gb=0)

    def test_inverted_prices_raise(self):
        with pytest.raises(ValueError):
            PricingModel(cold_storage_per_gb=1.0, warm_storage_per_gb=0.5,
                         hot_storage_per_gb=0.1)

    def test_missing_tier_column_raises(self, small_df):
        with pytest.raises(ValueError, match="'tier' column"):
            CostEstimator().estimate(small_df)

    def test_price_helpers(self):
        p = PricingModel()
        assert p.storage_price("hot") == p.hot_storage_per_gb
        assert p.retrieval_price("cold") == p.cold_retrieval_per_gb


# ── compare_policies tests ───────────────────────────────────────────────────
class TestComparePolicies:
    def _classified_map(self, small_df):
        return {
            name: RuleBasedStrategy(policy).classify(small_df)
            for name, policy in POLICIES.items()
        }

    def test_returns_one_row_per_policy(self, small_df):
        result = compare_policies(self._classified_map(small_df))
        assert len(result) == len(POLICIES)

    def test_sorted_by_annual_savings(self, small_df):
        result = compare_policies(self._classified_map(small_df))
        savings = result["annual_saving_$"].tolist()
        assert savings == sorted(savings, reverse=True)

    def test_aggressive_tops_comparison(self, small_df):
        result = compare_policies(self._classified_map(small_df))
        assert result.iloc[0]["policy"] == "aggressive"


# ── Migration tests (new) ────────────────────────────────────────────────────
class TestMigration:
    def test_plan_requires_tier(self, small_df):
        with pytest.raises(ValueError, match="'tier' column"):
            build_migration_plan(small_df)

    def test_plan_assumes_hot_baseline(self, classified_df):
        plan = build_migration_plan(classified_df)
        # Everything not already HOT must be a move.
        non_hot = (classified_df["tier"] != HOT).sum()
        assert plan.n_moves == non_hot

    def test_plan_with_explicit_current_tier(self, classified_df):
        df = classified_df.copy()
        df["current_tier"] = df["tier"]  # nothing to move
        plan = build_migration_plan(df)
        assert plan.n_moves == 0
        assert "No migrations required" in plan.summary()

    def test_dry_run_executor_moves_nothing_real(self, classified_df):
        plan = build_migration_plan(classified_df)
        result = DryRunExecutor().execute(plan)
        assert result.dry_run is True
        assert result.failed == 0
        assert result.executed == plan.n_moves
        assert result.gb_moved == pytest.approx(plan.total_gb)


# ── Carbon tests (new) ───────────────────────────────────────────────────────
class TestCarbon:
    def test_requires_tier(self, small_df):
        with pytest.raises(ValueError, match="'tier' column"):
            estimate_carbon(small_df)

    def test_negative_watt_raises(self):
        with pytest.raises(ValueError):
            CarbonModel(hot_watt_per_tb=-1)

    def test_returns_expected_keys(self, classified_df):
        c = estimate_carbon(classified_df)
        for key in ["baseline_kwh_month", "tiered_kwh_month", "kwh_saved_month",
                    "co2_saved_kg_month", "co2_saved_kg_year", "co2_savings_pct"]:
            assert key in c

    def test_tiered_uses_less_energy(self, classified_df):
        c = estimate_carbon(classified_df)
        assert c["tiered_kwh_month"] <= c["baseline_kwh_month"]
        assert c["co2_saved_kg_month"] >= 0

    def test_annual_is_twelve_months(self, classified_df):
        c = estimate_carbon(classified_df)
        assert c["co2_saved_kg_year"] == pytest.approx(c["co2_saved_kg_month"] * 12)

    def test_cleaner_grid_less_co2(self, classified_df):
        dirty = estimate_carbon(classified_df, CarbonModel(grid_kg_co2_per_kwh=0.7))
        clean = estimate_carbon(classified_df, CarbonModel(grid_kg_co2_per_kwh=0.04))
        assert clean["co2_saved_kg_month"] < dirty["co2_saved_kg_month"]


# ── Domain tests (new) ───────────────────────────────────────────────────────
class TestDomain:
    def test_tier_enum_equals_string(self):
        assert Tier.HOT == "hot"
        assert Tier.COLD.value == COLD

    def test_tier_order(self):
        from storagetieriq.domain.models import TIER_ORDER
        assert TIER_ORDER == [HOT, WARM, COLD]
