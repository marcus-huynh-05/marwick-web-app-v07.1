"""Small shared helpers: money formatting, stable IDs, date presets.

Money is always held as integer cents. Formatting converts cents to text
without going through floating-point numbers, so what is displayed is exact.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

MINUS = "−"  # typographic minus sign


def format_money(cents: int, currency: str = "AUD", signed: bool = False) -> str:
    """Format integer cents, e.g. 123456 -> 'AUD 1,234.56'.

    signed=True adds an explicit '+' for positive values (used for changes).
    """
    cents = int(cents)
    sign = ""
    if cents < 0:
        sign = MINUS
    elif signed and cents > 0:
        sign = "+"
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{currency} {whole:,}.{frac:02d}"


def cents_to_float(cents: int | None) -> float | None:
    """For display widgets and charts only. Never use the result in calculations."""
    if cents is None or cents != cents:  # None or NaN (missing value)
        return None
    return int(cents) / 100


def format_pct(pct: float | None) -> str:
    if pct is None:
        return "n/a"
    return f"{pct:+.1f}%".replace("-", MINUS)


def stable_txn_id(date_text: str, description: str, amount_cents: int, occurrence: int) -> str:
    """Deterministic ID for a transaction.

    The same file always produces the same IDs, so manual corrections survive
    re-runs and settings changes. `occurrence` separates identical rows.
    """
    key = f"{date_text}|{description}|{amount_cents}|{occurrence}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def period_days(start: date, end: date) -> int:
    """Inclusive number of days in a period."""
    return (end - start).days + 1


def preset_periods(min_date: date, max_date: date, preset: str):
    """Return ((a_start, a_end), (b_start, b_end)) for a named preset, or None.

    Presets are anchored on the latest date in the file, not today's date,
    because exports are often a few days or weeks old.
    """
    if preset == "split_half":
        if max_date <= min_date:
            return None
        mid = min_date + (max_date - min_date) // 2
        return (min_date, mid), (mid + timedelta(days=1), max_date)
    if preset in ("last_30", "last_7"):
        n = 30 if preset == "last_30" else 7
        b = (max_date - timedelta(days=n - 1), max_date)
        a = (b[0] - timedelta(days=n), b[0] - timedelta(days=1))
        return a, b
    if preset == "last_month":
        # Latest complete-or-current calendar month in the file vs the month before.
        b_start = max_date.replace(day=1)
        a_end = b_start - timedelta(days=1)
        a_start = a_end.replace(day=1)
        return (a_start, a_end), (b_start, max_date)
    return None
