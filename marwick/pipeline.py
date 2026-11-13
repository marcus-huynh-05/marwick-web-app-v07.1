"""One function that runs the whole deterministic pipeline.

CSV bytes -> raw table -> clean transactions -> suggestions -> user
corrections -> review flags. The Streamlit app and the tests both call
this, so the app never re-implements financial logic.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .classify import apply_overrides, classify, compute_review
from .validators import ColumnMapping, ParseResult, build_transactions


@dataclass
class Prepared:
    transactions: pd.DataFrame
    invalid: pd.DataFrame
    warnings: list[str]


def prepare(raw: pd.DataFrame, mapping: ColumnMapping, own_suffixes: list[str],
            overrides: dict[str, dict] | None = None) -> Prepared:
    parsed: ParseResult = build_transactions(raw, mapping)
    tx = classify(parsed.transactions, own_suffixes)
    tx = apply_overrides(tx, overrides or {})
    tx = compute_review(tx)
    return Prepared(tx, parsed.invalid, parsed.warnings)
