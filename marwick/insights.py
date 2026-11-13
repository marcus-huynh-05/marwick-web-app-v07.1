"""Deterministic insights built only from engine results.

Each insight carries the exact figures it states and the IDs of the
transactions that support it. No wording here invents a number: every
amount in a statement is formatted from a field on the same insight.
These structured insights are also the future input for an AI layer (v0.9).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .engine import Comparison, add_buckets, slice_period
from .utils import format_money, format_pct

IMPLEMENTED_INSIGHTS = {
    "net_change": "Net spending change between the two periods",
    "category_increase": "Categories where net spending rose",
    "category_decrease": "Categories where net spending fell",
    "new_category": "Categories with spending only in Period B",
    "stopped_category": "Categories with spending only in Period A",
}

PLANNED_INSIGHTS = {
    "frequency_vs_value": "Whether a change came from more transactions or higher average value (v0.8)",
    "recurring": "Recurring payments and likely subscriptions (v0.8)",
    "unusual": "Unusually large transactions compared with your own pattern (v0.8)",
}


@dataclass
class Insight:
    kind: str
    title: str
    statement: str
    category: str | None = None
    amount_a: int | None = None
    amount_b: int | None = None
    change: int | None = None
    pct: float | None = None
    evidence_ids: list[str] = field(default_factory=list)
    rank: float = 0.0


def _evidence(tx: pd.DataFrame, comp: Comparison, category: str | None) -> list[str]:
    ids = []
    for s, e in ((comp.a.start, comp.a.end), (comp.b.start, comp.b.end)):
        p = add_buckets(slice_period(tx, s, e))
        p = p[p["bucket"].isin(["spend", "refund"])]
        if category is not None:
            cats = p["spending_category"].replace({"Not applicable": "Uncategorised"})
            p = p[cats == category]
        ids.extend(p["txn_id"].tolist())
    return ids


def generate_insights(tx: pd.DataFrame, comp: Comparison, currency: str = "AUD") -> list[Insight]:
    out: list[Insight] = []
    a, b = comp.a, comp.b
    if a.is_empty or b.is_empty:
        return out  # no comparison is meaningful with an empty period

    # 1. Headline
    if comp.net_change == 0:
        statement = f"Net spending was unchanged at {format_money(b.net_spending, currency)}."
    else:
        word = "rose" if comp.net_change > 0 else "fell"
        statement = (
            f"Net spending {word} from {format_money(a.net_spending, currency)} to "
            f"{format_money(b.net_spending, currency)} ({format_money(comp.net_change, currency, signed=True)}"
            + (f", {format_pct(comp.pct)}" if comp.pct is not None else "") + ")."
        )
    if not comp.same_length:
        statement += (
            f" Periods differ in length; per day: {format_money(a.net_per_day, currency)} vs "
            f"{format_money(b.net_per_day, currency)}."
        )
    out.append(Insight("net_change", "Net spending", statement, None, a.net_spending, b.net_spending,
                       comp.net_change, comp.pct, _evidence(tx, comp, None), rank=float("inf")))

    # 2. Category changes
    cats = comp.categories
    for cat, r in cats.iterrows():
        change = int(r["net_change"])
        if change == 0:
            continue
        na, nb = int(r["net_a"]), int(r["net_b"])
        if r["count_a"] == 0 and r["refunds_a"] == 0 and nb > 0:
            kind, title = "new_category", f"New spending: {cat}"
            statement = f"{cat}: {format_money(nb, currency)} in Period B, none in Period A."
        elif r["count_b"] == 0 and r["refunds_b"] == 0 and na > 0:
            kind, title = "stopped_category", f"No spending: {cat}"
            statement = f"{cat}: no spending in Period B, down from {format_money(na, currency)} in Period A."
        else:
            kind = "category_increase" if change > 0 else "category_decrease"
            title = f"{cat} {'up' if change > 0 else 'down'}"
            statement = (
                f"{cat} net spending went from {format_money(na, currency)} to {format_money(nb, currency)} "
                f"({format_money(change, currency, signed=True)}). "
                f"Transactions: {int(r['count_a'])} → {int(r['count_b'])}."
            )
        pct = (change / na * 100) if na > 0 else None
        out.append(Insight(kind, title, statement, str(cat), na, nb, change, pct,
                           _evidence(tx, comp, str(cat)), rank=abs(change)))
    out.sort(key=lambda i: i.rank, reverse=True)
    return out
