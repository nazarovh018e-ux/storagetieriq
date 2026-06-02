"""
storagetieriq.ingestion.base
-----------------------------
The :class:`DataSource` abstraction.

A *data source* is anything that can produce a DataFrame of storage
records with the canonical schema (see :data:`REQUIRED_COLUMNS`).  This
is the seam that lets the rest of the pipeline stay identical whether
records come from a synthetic generator, a CSV export, an AWS S3
inventory report, or a SQL query against a metadata store.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from storagetieriq.domain.models import validate_columns


class DataSource(ABC):
    """Produce a DataFrame of storage records on demand."""

    @abstractmethod
    def load(self) -> pd.DataFrame:
        """Return a DataFrame containing at least :data:`REQUIRED_COLUMNS`."""
        raise NotImplementedError

    def load_validated(self) -> pd.DataFrame:
        """Call :meth:`load` and assert the schema before returning.

        Concrete sources should not need to re-implement validation.
        """
        df = self.load()
        validate_columns(df.columns)
        return df
