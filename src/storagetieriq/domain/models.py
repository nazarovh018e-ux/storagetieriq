"""
storagetieriq.domain.models
----------------------------
Core domain types shared across the whole package.

This module contains **no I/O and no business logic** — only the
vocabulary (tiers, required columns, the canonical record schema) that
every other layer depends on.  Keeping it dependency-free prevents
circular imports between ingestion / policy / costing.
"""

from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    """
    Storage tiers, ordered from most expensive / fastest (HOT) to
    cheapest / slowest (COLD).

    Inherits from ``str`` so a :class:`Tier` compares equal to its plain
    string value (``Tier.HOT == "hot"``).  This keeps DataFrame columns
    that store plain strings fully interoperable with the enum.
    """

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


# Convenience string constants (backwards-compatible with the original
# flat module that exported HOT / WARM / COLD as bare strings).
HOT: str = Tier.HOT.value
WARM: str = Tier.WARM.value
COLD: str = Tier.COLD.value

# Canonical ordering used by summaries, reports, and charts.
TIER_ORDER: list[str] = [HOT, WARM, COLD]

# Every column a classifier needs to be present on an input DataFrame.
REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {"age_days", "days_since_access", "access_count", "data_type", "size_mb"}
)


def validate_columns(columns) -> None:
    """Raise ``ValueError`` if any required column is missing.

    Centralised here so every strategy validates identically.
    """
    missing = REQUIRED_COLUMNS - set(columns)
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")
