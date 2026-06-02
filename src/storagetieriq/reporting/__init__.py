"""Reporting layer: text report and (optional) PNG dashboard.

``build_dashboard`` is imported lazily so that importing this package does
not require matplotlib to be installed.
"""

from storagetieriq.reporting.text_report import generate_report

__all__ = ["generate_report", "build_dashboard"]


def build_dashboard(*args, **kwargs):
    """Lazy proxy to :func:`storagetieriq.reporting.dashboard.build_dashboard`.

    Imported on first call so a missing matplotlib only affects users who
    actually request a dashboard.
    """
    from storagetieriq.reporting.dashboard import build_dashboard as _impl

    return _impl(*args, **kwargs)
