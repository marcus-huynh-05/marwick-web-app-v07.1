"""The financial calculation engine: Marwick's source of truth.

Every amount is integer cents. Every transaction lands in exactly one
"bucket", so nothing can disappear from the totals unseen:

  spend         Expense, money out          -> gross spending
  refund        Refund, money in            -> refunds
  income        Income, money in            -> income
  transfer_in   Internal Transfer, money in -> shown, excluded from income
  transfer_out  Internal Transfer, money out-> shown, excluded from spending
  conflict      type contradicts the sign   -> shown, excluded until fixed
  zero          zero amount                 -> shown, no effect
  excluded      excluded by the user        -> shown, excluded

Net Spending = Gross Spending - Refunds.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

from .classify import EXPENSE, INCOME, NOT_APPLICABLE, REFUND, TRANSFER, UNCATEGORISED, sign_conflict
from .utils import period_days

BUCKETS = ["spend", "refund", "income", "transfer_in", "transfer_out", "conflict", "zero", "excluded"]


def bucket_for(transaction_type: str, amount_cents: int, excluded: bool = False) -> str:
    if excluded:
        return "excluded"
    if amount_cents == 0:
        return "zero"
    if sign_conflict(transaction_type, amount_cents):
        return "conflict"
    if transaction_type == EXPENSE:
        return "spend"
    if transaction_type == REFUND:
        return "refund"
    if transaction_type == INCOME:
        return "income"
    if transaction_type == TRANSFER:
        return "transfer_in" if amount_cents > 0 else "transfer_out"
    return "conflict"  # unknown type: never silently counted


def add_buckets(tx: pd.DataFrame) -> pd.DataFrame:
    out = tx.copy()
    excluded = out["excluded"] if "excluded" in out else pd.Series(False, index=out.index)
    out["bucket"] = [
        bucket_for(t, int(a), bool(e))
        for t, a, e in zip(out["transaction_type"], out["amount_cents"], excluded)
    ]
    return out


@dataclass
class PeriodMetrics:
    start: date
    end: date
    days: int
    transaction_count: int = 0
    gross_spending: int = 0
    refunds: int = 0
    net_spending: int = 0
    income: int = 0
    transfer_in: int = 0
    transfer_out: int = 0
    expense_count: int = 0
    refund_count: int = 0
    income_count: int = 0
    transfer_count: int = 0
    conflict_count: int = 0
    conflict_amount: int = 0  # absolute cents, not in any total
    excluded_count: int = 0
    excluded_amount: int = 0
    zero_count: int = 0
    needs_review_count: int = 0

    @property
    def is_empty(self) -> bool:
        return self.transaction_count == 0

    @property
    def avg_expense(self) -> int | None:
        """Average Expense value in cents (rounded), or None when there are none."""
        if self.expense_count == 0:
            return None
        return _round_div(self.gross_spending, self.expense_count)

    @property
    def net_per_day(self) -> int:
        return _round_div(self.net_spending, self.days)

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(is_empty=self.is_empty, avg_expense=self.avg_expense, net_per_day=self.net_per_day)
        return d


def _round_div(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero (for display averages only)."""
    if denominator == 0:
        raise ZeroDivisionError("denominator is zero")
    q, r = divmod(abs(numerator), denominator)
    if 2 * r >= denominator:
        q += 1
    return q if numerator >= 0 else -q


def slice_period(tx: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    d = tx["date"].dt.date
    return tx.loc[(d >= start) & (d <= end)]


def period_metrics(tx: pd.DataFrame, start: date, end: date) -> PeriodMetrics:
    """Metrics for one date range (inclusive). Expects classified rows."""
    if start > end:
        raise ValueError("Period start must be on or before its end")
    p = add_buckets(slice_period(tx, start, end))
    m = PeriodMetrics(start=start, end=end, days=period_days(start, end))
    if p.empty:
        return m
    amt = p["amount_cents"].astype("int64")
    b = p["bucket"]

    def total(name):
        return int(amt[b == name].sum())

    m.transaction_count = len(p)
    m.gross_spending = -total("spend")
    m.refunds = total("refund")
    m.net_spending = m.gross_spending - m.refunds
    m.income = total("income")
    m.transfer_in = total("transfer_in")
    m.transfer_out = -total("transfer_out")
    m.expense_count = int((b == "spend").sum())
    m.refund_count = int((b == "refund").sum())
    m.income_count = int((b == "income").sum())
    m.transfer_count = int(b.isin(["transfer_in", "transfer_out"]).sum())
    m.conflict_count = int((b == "conflict").sum())
    m.conflict_amount = int(amt[b == "conflict"].abs().sum())
    m.excluded_count = int((b == "excluded").sum())
    m.excluded_amount = int(amt[b == "excluded"].abs().sum())
    m.zero_count = int((b == "zero").sum())
    if "needs_review" in p:
        m.needs_review_count = int(p["needs_review"].sum())
    return m


def pct_change(base: int, new: int) -> tuple[float | None, str | None]:
    """Percentage change, or (None, reason) when a percentage would mislead.

    Undefined when the baseline is zero, and when it is negative
    (refunds larger than spending), because the sign would read backwards.
    """
    if base == 0:
        return None, "Period A is zero, so a percentage change is undefined"
    if base < 0:
        return None, "Period A net spending is negative (refunds exceeded spending), so a percentage would mislead"
    return (new - base) / base * 100, None


def category_table(tx: pd.DataFrame, a: tuple[date, date], b: tuple[date, date]) -> pd.DataFrame:
    """Per-category gross, refunds, net, count and average for both periods.

    Refunds are attributed to their own category. A refund without a spending
    category is shown on an 'Uncategorised' row, so the category nets always
    add up exactly to the headline net spending.
    """
    rows = {}
    for label, (s, e) in (("a", a), ("b", b)):
        p = add_buckets(slice_period(tx, s, e))
        p = p[p["bucket"].isin(["spend", "refund"])].copy()
        p["cat"] = p["spending_category"].replace({NOT_APPLICABLE: UNCATEGORISED})
        for cat, g in p.groupby("cat"):
            r = rows.setdefault(cat, {})
            spend = g[g["bucket"] == "spend"]["amount_cents"]
            refund = g[g["bucket"] == "refund"]["amount_cents"]
            r[f"gross_{label}"] = int(-spend.sum())
            r[f"refunds_{label}"] = int(refund.sum())
            r[f"count_{label}"] = int(len(spend))
    cols = ["gross_a", "refunds_a", "count_a", "gross_b", "refunds_b", "count_b"]
    table = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=cols).fillna(0).astype("int64")
    table.index.name = "category"
    for label in ("a", "b"):
        table[f"net_{label}"] = table[f"gross_{label}"] - table[f"refunds_{label}"]
        table[f"avg_{label}"] = [
            _round_div(g, c) if c else None for g, c in zip(table[f"gross_{label}"], table[f"count_{label}"])
        ]
    table["gross_change"] = table["gross_b"] - table["gross_a"]
    table["net_change"] = table["net_b"] - table["net_a"]
    return table.sort_values("net_change", ascending=False)


@dataclass
class Comparison:
    a: PeriodMetrics
    b: PeriodMetrics
    categories: pd.DataFrame
    net_change: int
    pct: float | None
    pct_note: str | None
    reconciles: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def same_length(self) -> bool:
        return self.a.days == self.b.days


def validate_periods(a: tuple[date, date], b: tuple[date, date]) -> list[str]:
    """Return blocking errors (empty list = OK)."""
    errors = []
    if a[0] > a[1] or b[0] > b[1]:
        errors.append("Each period's start date must be on or before its end date.")
    elif not (a[1] < b[0] or b[1] < a[0]):
        errors.append("The two periods overlap. Choose non-overlapping date ranges.")
    return errors


def compare_periods(tx: pd.DataFrame, a: tuple[date, date], b: tuple[date, date]) -> Comparison:
    errors = validate_periods(a, b)
    if errors:
        raise ValueError(errors[0])
    ma, mb = period_metrics(tx, *a), period_metrics(tx, *b)
    cats = category_table(tx, a, b)
    pct, note = pct_change(ma.net_spending, mb.net_spending)
    reconciles = (
        int(cats["net_a"].sum()) == ma.net_spending and int(cats["net_b"].sum()) == mb.net_spending
        and int(cats["gross_a"].sum()) == ma.gross_spending and int(cats["gross_b"].sum()) == mb.gross_spending
    )
    warnings = []
    if not tx.empty:
        data_start, data_end = tx["date"].min().date(), tx["date"].max().date()
        for name, (s, e) in (("Period A", a), ("Period B", b)):
            if s < data_start or e > data_end:
                warnings.append(
                    f"{name} extends beyond the dates in your file ({data_start:%d %b %Y} to "
                    f"{data_end:%d %b %Y}). Missing days are not assumed to be zero spending."
                )
    for name, m in (("Period A", ma), ("Period B", mb)):
        if m.is_empty:
            warnings.append(f"{name} contains no transactions.")
        if m.conflict_count:
            warnings.append(
                f"{name}: {m.conflict_count} transaction(s) have a type that contradicts their amount "
                "and are not in any total until fixed."
            )
    if ma.days != mb.days:
        warnings.append(
            f"The periods have different lengths ({ma.days} vs {mb.days} days). Compare the per-day figures."
        )
    return Comparison(ma, mb, cats, mb.net_spending - ma.net_spending, pct, note, reconciles, warnings)


def weekly_net_spending(tx: pd.DataFrame) -> pd.DataFrame:
    """Gross, refunds and net spending per week (weeks start Monday)."""
    p = add_buckets(tx)
    p = p[p["bucket"].isin(["spend", "refund"])].copy()
    if p.empty:
        return pd.DataFrame(columns=["week_start", "gross", "refunds", "net"])
    p["week_start"] = (p["date"] - pd.to_timedelta(p["date"].dt.weekday, unit="D")).dt.normalize()
    p["gross"] = p["amount_cents"].where(p["bucket"] == "spend", 0) * -1
    p["refunds"] = p["amount_cents"].where(p["bucket"] == "refund", 0)
    w = p.groupby("week_start")[["gross", "refunds"]].sum().astype("int64")
    full = pd.date_range(w.index.min(), w.index.max(), freq="7D")
    w = w.reindex(full, fill_value=0)
    w.index.name = "week_start"
    w["net"] = w["gross"] - w["refunds"]
    return w.reset_index()
