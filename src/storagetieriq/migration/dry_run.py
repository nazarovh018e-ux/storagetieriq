"""
storagetieriq.migration.dry_run
--------------------------------
A safe, side-effect-free executor.

Reports exactly what *would* happen without touching any storage.  This
is the default executor and the one used in tests / CI -- it never needs
credentials or network access.
"""

from __future__ import annotations

from storagetieriq.migration.base import (
    MigrationExecutor,
    MigrationPlan,
    MigrationResult,
)


class DryRunExecutor(MigrationExecutor):
    """Simulate a migration; perform no real I/O."""

    dry_run = True

    def __init__(self, verbose: bool = False, max_preview: int = 5) -> None:
        self.verbose = verbose
        self.max_preview = max_preview

    def execute(self, plan: MigrationPlan) -> MigrationResult:
        if self.verbose and plan.n_moves:
            preview = plan.moves.head(self.max_preview)
            for _, row in preview.iterrows():
                rid = row.get("record_id", "<no-id>")
                print(
                    f"    would move {rid} "
                    f"{row['current_tier']} -> {row['tier']} "
                    f"({row['size_mb'] / 1024:.4f} GB)"
                )
            if plan.n_moves > self.max_preview:
                print(f"    ... and {plan.n_moves - self.max_preview:,} more")

        return MigrationResult(
            executed=plan.n_moves,
            failed=0,
            gb_moved=plan.total_gb,
            dry_run=True,
        )


__all__ = ["DryRunExecutor"]
