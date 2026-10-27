"""Small text-formatting helpers shared by the tables, workbook and dashboard."""

from __future__ import annotations

import html

import numpy as np
import pandas as pd


def esc(s) -> str:
    """HTML-escape a value."""
    return html.escape(str(s), quote=True)


def fmt(n) -> str:
    """Format a number with thousands separators; other values are returned as text."""
    return f"{n:,.0f}" if isinstance(n, (int, float, np.integer, np.floating)) and not pd.isna(n) else str(n)


def pct(n, d) -> str:
    """Share n/d as a percentage string ('-' when d is 0)."""
    return f"{100 * n / d:.1f}%" if d else "-"


def yes(b) -> str:
    """'Yes' for a truthy value, otherwise ''."""
    return "Yes" if bool(b) else ""
