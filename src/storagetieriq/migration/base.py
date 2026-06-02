"""
storagetieriq.migration.base
-----------------------------
The *migration* abstraction: turning a classification into action.

A classified DataFrame says where each object *should* live.  A migration
plan diffs that target against where each object *currently* lives and
produces the set of moves required.  A :class:`MigrationExecutor` then
carries those moves out -- as a dry run, against AWS S3, GCS, etc.

This is the layer the original project was missing: it had the analysis
but no way to act on it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd

from storagetieriq.domain.models import HOT


@dataclass
class MigrationPlan:
    """A set of tier moves derived from a classification."""

    #: Rows that need to move, with current_tier and target tier columns.
    moves: pd.DataFrame
    #: Count of objects per (current_tier -> target tier) transition.
    transitions: dict[tuple[str, str], int] = field(default_factory=dict)
    #: GB moved per transition.
    gb_by_transition: dict[tuple[str, str], float] = field(default_factory=dict)

    @property
    def n_moves(self) -> int:
        return len(self.moves)

    @property
    def total_gb(self) -> float:
        return float(self.moves["size_mb"].sum() / 1024) if self.n_moves else 0.0

    def summary(self) -> str:
        if self.n_moves == 0:
            return "No migrations required - all objects already on target tier."
        lines = [f"Migration plan: {self.n_moves:,} object(s), {self.total_gb:.2f} GB"]
        for (src, dst), count in sorted(self.transitions.items()):
            gb = self.gb_by_transition.get((src, dst), 0.0)
            lines.append(f"  {src:>4} -> {dst:<4}  {count:>8,} objs  {gb:>9.2f} GB")
        return "\n".join(lines)


def build_migration_plan(
    classified: pd.DataFrame,
    current_tier_col: str = "current_tier",
) -> MigrationPlan:
    """Diff target ``tier`` against current placement to produce a plan.

    If *current_tier_col* is absent, every object is assumed to currently
    live on HOT (a flat-SSD baseline), so the plan contains every object
    whose target tier is not HOT.
    """
    if "tier" not in classified.columns:
        raise ValueError("classified DataFrame must have a 'tier' column.")

    df = classified.copy()
    if current_tier_col not in df.columns:
        df[current_tier_col] = HOT

    needs_move = df[df[current_tier_col] != df["tier"]].copy()
    needs_move = needs_move.rename(columns={current_tier_col: "current_tier"})

    transitions: dict[tuple[str, str], int] = {}
    gb_by_transition: dict[tuple[str, str], float] = {}
    if len(needs_move):
        grouped = needs_move.groupby(["current_tier", "tier"])
        for (src, dst), sub in grouped:
            transitions[(src, dst)] = len(sub)
            gb_by_transition[(src, dst)] = float(sub["size_mb"].sum() / 1024)

    return MigrationPlan(
        moves=needs_move,
        transitions=transitions,
        gb_by_transition=gb_by_transition,
    )


@dataclass
class MigrationResult:
    """Outcome of executing a plan."""

    executed: int
    failed: int
    gb_moved: float
    dry_run: bool

    def summary(self) -> str:
        mode = "DRY RUN" if self.dry_run else "EXECUTED"
        return (
            f"[{mode}] {self.executed:,} moved, {self.failed:,} failed, "
            f"{self.gb_moved:.2f} GB"
        )


class MigrationExecutor(ABC):
    """Carry out a :class:`MigrationPlan`."""

    #: True for executors that never touch real storage.
    dry_run: bool = False

    @abstractmethod
    def execute(self, plan: MigrationPlan) -> MigrationResult:
        raise NotImplementedError


__all__ = [
    "MigrationPlan",
    "MigrationResult",
    "MigrationExecutor",
    "build_migration_plan",
]
