# StorageTierIQ — Cost-Optimized Storage Tiering System

![CI](https://github.com/nazarovh018e-ux/Cost-Optimized-Storage-Tiering-Strategy/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A modular Python toolkit that simulates a real-world **HOT / WARM / COLD**
storage tiering strategy, estimates costs, justifies the policy
quantitatively, and (optionally) executes the resulting object migrations.

For teams managing large datasets, storage cost is often dominated by data
that is rarely accessed yet sitting on expensive SSD. StorageTierIQ analyses
access patterns and recommends a cost-optimised tier for every object.

---

## What changed in v1.0

This release restructures the project into an installable package with clean
module boundaries and three *pluggable* extension points:

- **`DataSource`** — where records come from (synthetic, CSV, future: S3 inventory)
- **`TieringStrategy`** — how a tier is decided (rule-based, cost-optimal, future: ML)
- **`MigrationExecutor`** — how moves are carried out (dry-run, optional AWS S3)

The old flat modules and `sys.path` hacks are gone; everything installs as a
proper package, so the CLI and the "use as a library" path both just work.

---

## Project structure

```
storagetieriq/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/storagetieriq/
│   ├── domain/        ← dependency-free core types (Tier, schema, PricingModel)
│   ├── ingestion/     ← DataSource ABC + SyntheticSource + CsvSource
│   ├── policy/        ← TieringStrategy ABC + RuleBasedStrategy + CostOptimalStrategy
│   ├── costing/       ← CostEstimator, sensitivity, policy comparison
│   ├── reporting/     ← text report + (optional) PNG dashboard
│   ├── migration/     ← MigrationExecutor ABC + DryRunExecutor + (optional) AwsS3Executor
│   └── cli.py         ← command-line entry point
├── tests/
└── .github/workflows/ci.yml
```

---

## Quick start

```bash
# Install (editable, with charts + dev tooling)
pip install -e ".[viz,dev]"

# Run with defaults (rule-based, 10k synthetic records)
storagetieriq

# Use the cost-optimal (break-even) strategy
storagetieriq --strategy cost-optimal

# Rule-based aggressive preset on a bigger dataset
storagetieriq --policy aggressive --records 50000

# Analyse YOUR data from a CSV inventory export
storagetieriq --input my_inventory.csv

# Show a dry-run migration plan
storagetieriq --strategy cost-optimal --plan-migration

# Skip the PNG dashboard (no matplotlib needed)
storagetieriq --no-dashboard
```

The input CSV must contain at least: `data_type`, `size_mb`, `age_days`,
`days_since_access`, `access_count`.

---

## Tiering strategies

**Rule-based (`--strategy rule`)** — explicit, explainable thresholds on age,
recency, and access count. Tune via presets (`--policy`) or overrides
(`--hot-days`, `--warm-days`, `--hot-access`).

**Cost-optimal (`--strategy cost-optimal`)** — assigns each object to the tier
that minimises its expected total cost over a planning horizon:

```
total(tier) = size_gb · storage_price(tier) · H
            + size_gb · retrieval_price(tier) · E[retrievals over H]
```

Expected retrievals are predicted with a transparent, ML-free estimator
(lifetime access rate × recency decay). Swap that estimator for a learned
model later without touching the decision logic — prediction and decision are
deliberately separated.

| Preset (rule) | Hot age | Warm age | Behaviour |
|---|---|---|---|
| `aggressive` | 14 days | 90 days | Move data to cheaper tiers quickly |
| `default` | 30 days | 180 days | Balanced cost vs availability |
| `conservative` | 60 days | 365 days | Keep data hot/warm longer |

---

## Storage tiers & default pricing

| Tier | Storage type | Default price | Use case |
|---|---|---|---|
| **HOT** | SSD / NVMe | $0.092 /GB/mo | Frequently accessed |
| **WARM** | Object storage (S3-IA) | $0.0125 /GB/mo | Occasional access |
| **COLD** | Glacier / Archive | $0.004 /GB/mo | Compliance / backup |

Edit `PricingModel` (in `domain/pricing.py`) with your provider's real rates.

---

## Energy & carbon footprint

Cold/archive tiers don't just cost less — they draw far less electricity,
because the media is powered down instead of always-on SSD. StorageTierIQ
estimates the energy (kWh) and CO₂ avoided by tiering, alongside the cost:

```python
from storagetieriq import estimate_carbon, CarbonModel

c = estimate_carbon(classified, CarbonModel(grid_kg_co2_per_kwh=0.4))
print(f"CO2 avoided: {c['co2_saved_kg_year']:.1f} kg/year "
      f"({c['co2_savings_pct']:.1f}% lower)")
```

All coefficients (watts per TB per tier, grid carbon intensity) are
configurable to your hardware and region.

---

## Use as a library

```python
from storagetieriq import (
    generate_dataset, RuleBasedStrategy, CostOptimalStrategy,
    TieringPolicy, PricingModel, CostEstimator, POLICIES, compare_policies,
)

df = generate_dataset(10_000)

# Rule-based with a custom policy
policy = TieringPolicy(name="my", hot_age_days=21, warm_age_days=120,
                       hot_min_accesses=30)
classified = RuleBasedStrategy(policy).classify(df)   # returns a copy

# Cost-optimal alternative
classified2 = CostOptimalStrategy(horizon_months=12).classify(df)

result = CostEstimator(PricingModel(hot_storage_per_gb=0.10)).estimate(classified)
print(f"Annual saving: ${result['annual_savings']:.2f}")

# Compare all presets side by side
cmap = {n: RuleBasedStrategy(p).classify(df) for n, p in POLICIES.items()}
print(compare_policies(cmap))
```

### Planning (and executing) migrations

```python
from storagetieriq import build_migration_plan, DryRunExecutor

plan = build_migration_plan(classified)      # diff target tier vs current
print(plan.summary())
DryRunExecutor(verbose=True).execute(plan)    # safe: no real I/O
```

To move real objects, install the AWS extra (`pip install -e ".[aws]"`) and use
`storagetieriq.migration.aws_s3.AwsS3Executor` with a `moves` table that
includes `bucket` and `key` columns.

---

## Running tests

```bash
pip install -e ".[dev]"
pytest --cov=storagetieriq --cov-report=term-missing
```

---

## Output files

| File | Description |
|---|---|
| `storage_records.csv` | Raw (or loaded) dataset |
| `classified_records.csv` | Dataset with `tier` column |
| `tiering_report.txt` | Full policy justification report |
| `storage_tiering_dashboard.png` | 7-panel visual dashboard |

These are runtime artefacts and are git-ignored.

---

## Extending

- **Real data**: implement a new `DataSource` (e.g. an S3-inventory reader) —
  the rest of the pipeline is unchanged.
- **New decision logic**: subclass `TieringStrategy` (e.g. an `MlStrategy` that
  predicts access probability) and plug it into the CLI.
- **Real migration**: implement a `MigrationExecutor` for your provider; the
  included `AwsS3Executor` shows the S3 storage-class transition pattern.
