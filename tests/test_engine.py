from datetime import date

import pytest

from marwick.classify import REFUND
from marwick.engine import compare_periods, period_metrics, pct_change, validate_periods, weekly_net_spending
from marwick.insights import generate_insights
from marwick.pipeline import prepare
from marwick.validators import guess_mapping, read_csv_bytes

JAN = (date(2026, 1, 1), date(2026, 1, 31))
FEB = (date(2026, 2, 1), date(2026, 2, 28))


def test_expenses_income_refunds_transfers(build):
    tx = build([
        ("2026-01-02", "-100.00", "WOOLWORTHS"),
        ("2026-01-03", "-50.25", "UBER EATS"),
        ("2026-01-04", "20.00", "WOOLWORTHS REFUND"),
        ("2026-01-05", "2650.00", "SALARY ACME"),
        ("2026-01-06", "-500.00", "TRANSFER TO XX1421"),
        ("2026-01-07", "200.00", "TRANSFER FROM XX1421"),
        ("2026-01-08", "-300.00", "TRANSFER TO XX9876 J SMITH"),  # external payment
    ], suffixes=["1421"])
    m = period_metrics(tx, *JAN)
    assert m.gross_spending == 10000 + 5025 + 30000
    assert m.refunds == 2000
    assert m.net_spending == m.gross_spending - m.refunds == 43025
    assert m.income == 265000  # internal transfer in is NOT income
    assert (m.transfer_out, m.transfer_in) == (50000, 20000)
    assert m.expense_count == 3 and m.avg_expense == 15008  # 45025 / 3 = 15008.33 -> 15008


def test_bug1_negative_refund_is_never_silently_dropped(build):
    # v0.6: a -50 'Refund' plus a -10 Expense gave gross spending of 10.
    tx = build([("2026-01-02", "-50.00", "WOOLWORTHS CASHBACK"), ("2026-01-03", "-10.00", "COLES")])
    assert period_metrics(tx, *JAN).gross_spending == 6000
    # Even if a user forces the wrong type, it is reported as a conflict, not lost.
    tid = tx["txn_id"].iloc[0]
    tx2 = build([("2026-01-02", "-50.00", "WOOLWORTHS CASHBACK"), ("2026-01-03", "-10.00", "COLES")],
                overrides={tid: {"transaction_type": REFUND}})
    m = period_metrics(tx2, *JAN)
    assert m.gross_spending == 1000
    assert (m.conflict_count, m.conflict_amount) == (1, 5000)
    assert m.needs_review_count == 1


def test_every_transaction_lands_in_exactly_one_bucket(sample_path):
    raw = read_csv_bytes(sample_path.read_bytes(), True)
    tx = prepare(raw, guess_mapping(raw), ["1421"]).transactions
    start, end = tx["date"].min().date(), tx["date"].max().date()
    m = period_metrics(tx, start, end)
    counted = (m.expense_count + m.refund_count + m.income_count + m.transfer_count
               + m.conflict_count + m.zero_count + m.excluded_count)
    assert counted == m.transaction_count == len(tx)
    # Money conservation: every cent in the file is accounted for.
    signed = (-m.gross_spending + m.refunds + m.income + m.transfer_in - m.transfer_out)
    assert signed == int(tx["amount_cents"].sum())


def test_excluded_rows_reported_not_counted(build):
    rows = [("2026-01-02", "-4.50", "CAFE"), ("2026-01-02", "-4.50", "CAFE")]
    tx = build(rows)
    tx = build(rows, overrides={tx["txn_id"].iloc[1]: {"excluded": True}})
    m = period_metrics(tx, *JAN)
    assert m.gross_spending == 450 and (m.excluded_count, m.excluded_amount) == (1, 450)


def test_net_spending_can_be_negative_and_pct_is_withheld(build):
    tx = build([
        ("2026-01-02", "-20.00", "COLES"), ("2026-01-03", "100.00", "AMAZON REFUND"),
        ("2026-02-02", "-50.00", "COLES"),
    ])
    c = compare_periods(tx, JAN, FEB)
    assert c.a.net_spending == -8000
    assert c.pct is None and "negative" in c.pct_note


def test_pct_change_rules():
    assert pct_change(0, 500) == (None, pct_change(0, 500)[1])
    assert pct_change(0, 500)[1] is not None
    assert pct_change(-100, 50)[0] is None
    assert pct_change(1000, 1500)[0] == pytest.approx(50.0)
    assert pct_change(1000, 500)[0] == pytest.approx(-50.0)


def test_zero_baseline(build):
    tx = build([("2026-01-05", "2650.00", "SALARY"), ("2026-02-02", "-50.00", "COLES")])
    c = compare_periods(tx, JAN, FEB)
    assert c.a.net_spending == 0 and not c.a.is_empty
    assert c.pct is None and "zero" in c.pct_note


def test_empty_period_is_flagged_not_treated_as_zero_spending(build):
    tx = build([("2026-02-02", "-50.00", "COLES")])
    c = compare_periods(tx, JAN, FEB)
    assert c.a.is_empty
    assert any("Period A contains no transactions" in w for w in c.warnings)
    assert any("beyond the dates in your file" in w for w in c.warnings)
    assert generate_insights(tx, c) == []  # no comparison insight from an empty period


def test_different_period_lengths_give_per_day_figures(build):
    tx = build([("2026-01-10", "-310.00", "COLES"), ("2026-02-10", "-280.00", "COLES")])
    c = compare_periods(tx, JAN, FEB)
    assert (c.a.days, c.b.days) == (31, 28)
    assert c.a.net_per_day == 1000 and c.b.net_per_day == 1000
    assert any("different lengths" in w for w in c.warnings)
    headline = generate_insights(tx, c)[0]
    assert "per day" in headline.statement


def test_category_totals_reconcile_with_gross_and_net(sample_path):
    raw = read_csv_bytes(sample_path.read_bytes(), True)
    tx = prepare(raw, guess_mapping(raw), ["1421"]).transactions
    c = compare_periods(tx, (date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 10, 1), date(2026, 10, 31)))
    assert c.reconciles
    assert int(c.categories["net_b"].sum()) == c.b.net_spending
    assert int(c.categories["gross_a"].sum()) == c.a.gross_spending


def test_refund_without_category_still_reconciles(build):
    tx = build([("2026-01-02", "-50.00", "COLES"), ("2026-01-03", "20.00", "MYSTERY REFUND")])
    c = compare_periods(tx, JAN, FEB)
    assert c.reconciles
    assert c.categories.loc["Uncategorised", "refunds_a"] == 2000


def test_overlapping_and_reversed_periods_rejected():
    assert validate_periods(JAN, (date(2026, 1, 15), date(2026, 2, 15)))
    assert validate_periods((date(2026, 1, 31), date(2026, 1, 1)), FEB)
    assert validate_periods(JAN, FEB) == []
    with pytest.raises(ValueError):
        compare_periods(None, JAN, JAN)


def test_insight_numbers_come_from_engine_fields(build):
    tx = build([
        ("2026-01-02", "-100.00", "UBER EATS"), ("2026-02-02", "-160.00", "UBER EATS"),
        ("2026-02-03", "-40.00", "UBER EATS"), ("2026-01-05", "-80.00", "COLES"),
    ])
    c = compare_periods(tx, JAN, FEB)
    ins = generate_insights(tx, c)
    dining = next(i for i in ins if i.category == "Dining")
    assert (dining.amount_a, dining.amount_b, dining.change) == (10000, 20000, 10000)
    assert "AUD 100.00" in dining.statement and "AUD 200.00" in dining.statement
    assert len(dining.evidence_ids) == 3
    stopped = next(i for i in ins if i.category == "Groceries")
    assert stopped.kind == "stopped_category"


def test_weekly_series_sums_to_net(sample_path):
    raw = read_csv_bytes(sample_path.read_bytes(), True)
    tx = prepare(raw, guess_mapping(raw), ["1421"]).transactions
    w = weekly_net_spending(tx)
    m = period_metrics(tx, tx["date"].min().date(), tx["date"].max().date())
    assert int(w["net"].sum()) == m.net_spending
