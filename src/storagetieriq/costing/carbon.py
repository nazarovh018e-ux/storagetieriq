"""
storagetieriq.costing.carbon
-----------------------------
Estimate the ENERGY and CARBON footprint of a tiering decision.

Cold / archive tiers don't just cost less money -- they consume far less
electricity, because the underlying media is powered down (or tape is
offline) instead of spinning 24/7 on always-on SSD. Moving rarely-used
data off hot SSD therefore cuts both the bill *and* the carbon footprint.

The model is deliberately transparent and fully configurable:

    energy_kWh(tier) = watt_per_tb(tier) · TB · hours_per_month / 1000
    co2_kg          = energy_kWh · grid_kg_co2_per_kwh

All coefficients are estimates and meant to be tuned to your hardware and
electricity grid. Defaults use fully-burdened figures (drive + server +
cooling overhead) and a world-average grid intensity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from storagetieriq.domain.models import TIER_ORDER


@dataclass
class CarbonModel:
    """Energy-per-TB and grid-intensity assumptions, validated on init."""

    # Fully-burdened power draw per stored TB, in watts.
    hot_watt_per_tb: float = 8.0
    warm_watt_per_tb: float = 2.0
    cold_watt_per_tb: float = 0.5
    baseline_watt_per_tb: float = 8.0  # flat, always-on SSD

    # Grid carbon intensity (kg CO2 per kWh). World avg ~0.4; a coal-heavy
    # grid ~0.7; a clean hydro/nuclear grid (e.g. Sweden) ~0.04.
    grid_kg_co2_per_kwh: float = 0.4

    hours_per_month: float = 730.0
    name: str = "default"

    def __post_init__(self) -> None:
        for attr in (
            "hot_watt_per_tb",
            "warm_watt_per_tb",
            "cold_watt_per_tb",
            "baseline_watt_per_tb",
        ):
            if getattr(self, attr) < 0:
                raise ValueError(f"{attr} must be >= 0, got {getattr(self, attr)}")
        if self.grid_kg_co2_per_kwh < 0:
            raise ValueError("grid_kg_co2_per_kwh must be >= 0")

    def watt_per_tb(self, tier: str) -> float:
        return {
            "hot": self.hot_watt_per_tb,
            "warm": self.warm_watt_per_tb,
            "cold": self.cold_watt_per_tb,
        }[tier]


def estimate_carbon(
    classified: pd.DataFrame,
    carbon: Optional[CarbonModel] = None,
) -> dict:
    """Return monthly/annual energy (kWh) and CO2 (kg) for tiered vs baseline.

    Requires a ``tier`` column on *classified*.
    """
    if "tier" not in classified.columns:
        raise ValueError("DataFrame must have a 'tier' column. Classify it first.")

    carbon = carbon or CarbonModel()
    total_tb = classified["size_mb"].sum() / (1024 * 1024)

    def kwh(tb: float, watt_per_tb: float) -> float:
        return watt_per_tb * tb * carbon.hours_per_month / 1000.0

    tiered_kwh = 0.0
    for tier in TIER_ORDER:
        tb = classified.loc[classified["tier"] == tier, "size_mb"].sum() / (
            1024 * 1024
        )
        tiered_kwh += kwh(tb, carbon.watt_per_tb(tier))

    baseline_kwh = kwh(total_tb, carbon.baseline_watt_per_tb)

    tiered_co2 = tiered_kwh * carbon.grid_kg_co2_per_kwh
    baseline_co2 = baseline_kwh * carbon.grid_kg_co2_per_kwh

    kwh_saved = baseline_kwh - tiered_kwh
    co2_saved = baseline_co2 - tiered_co2
    co2_pct = (co2_saved / baseline_co2 * 100) if baseline_co2 > 0 else 0.0

    return {
        "total_tb": total_tb,
        "tiered_kwh_month": tiered_kwh,
        "baseline_kwh_month": baseline_kwh,
        "kwh_saved_month": kwh_saved,
        "tiered_co2_kg_month": tiered_co2,
        "baseline_co2_kg_month": baseline_co2,
        "co2_saved_kg_month": co2_saved,
        "co2_saved_kg_year": co2_saved * 12,
        "co2_savings_pct": co2_pct,
    }


__all__ = ["CarbonModel", "estimate_carbon"]
