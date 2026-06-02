"""Ingestion layer: pluggable data sources (synthetic, CSV, ...)."""

from storagetieriq.ingestion.base import DataSource
from storagetieriq.ingestion.csv_source import CsvSource
from storagetieriq.ingestion.synthetic import (
    DATA_TYPES,
    SIZE_RANGES,
    TYPE_WEIGHTS,
    SyntheticSource,
    generate_dataset,
    summarize_dataset,
)

__all__ = [
    "DataSource",
    "SyntheticSource",
    "CsvSource",
    "generate_dataset",
    "summarize_dataset",
    "DATA_TYPES",
    "TYPE_WEIGHTS",
    "SIZE_RANGES",
]
