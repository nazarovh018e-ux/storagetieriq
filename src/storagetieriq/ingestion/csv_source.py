"""
storagetieriq.ingestion.csv_source
-----------------------------------
Load real storage-inventory records from a CSV file.

This is the simplest "real data" source: point it at an export from
your storage inventory (or a previously generated ``storage_records.csv``)
and it conforms to the same :class:`DataSource` contract as the synthetic
generator.  The pipeline downstream does not care which source it came
from.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from storagetieriq.ingestion.base import DataSource


class CsvSource(DataSource):
    """Read storage records from a CSV file.

    Parameters
    ----------
    path:
        Path to the CSV file.
    parse_dates:
        Columns to parse as datetimes (defaults to created_at /
        last_accessed if present).
    """

    def __init__(self, path: str, parse_dates: Optional[list[str]] = None) -> None:
        self.path = path
        self.parse_dates = parse_dates

    def load(self) -> pd.DataFrame:
        candidate_dates = self.parse_dates or ["created_at", "last_accessed"]
        # Only ask pandas to parse date columns that actually exist.
        header = pd.read_csv(self.path, nrows=0).columns
        date_cols = [c for c in candidate_dates if c in header]
        return pd.read_csv(self.path, parse_dates=date_cols or None)
