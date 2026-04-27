"""
Formatting utilities for FolioIQ
Handles currency formatting, data formatting, and display helpers
"""

import pandas as pd


def fmt_inr(number: float) -> str:
    """Format number in Indian numbering system (Lakhs/Crores)."""
    try:
        if pd.isna(number):
            return "₹0"
        is_negative = number < 0
        num_str = str(abs(int(round(number))))
        if len(num_str) <= 3:
            res = num_str
        else:
            res = num_str[:-3]
            res = ",".join([res[max(i-2, 0):i] for i in range(len(res), 0, -2)][::-1]) + "," + num_str[-3:]
        return f"-₹{res}" if is_negative else f"₹{res}"
    except Exception:
        return "₹0"


def fmt_percentage(value: float, decimals: int = 2) -> str:
    """Format a percentage value."""
    try:
        if pd.isna(value):
            return "0%"
        return f"{value:+.{decimals}f}%" if value != 0 else "0%"
    except Exception:
        return "0%"


def fmt_decimal(value: float, decimals: int = 2) -> str:
    """Format a decimal value."""
    try:
        if pd.isna(value):
            return "0"
        return f"{value:.{decimals}f}"
    except Exception:
        return "0"


def color_positive_negative(value: float) -> str:
    """Return color class based on positive/negative value."""
    return "pos" if value >= 0 else "neg"
