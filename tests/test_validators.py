from datetime import date

import pandas as pd
import pytest

from marwick.validators import (
    SIGN_POSITIVE_OUT, ColumnMapping, build_transactions, guess_mapping, parse_amount_to_cents,
    parse_dates, read_csv_bytes,
)


@pytest.mark.parametrize("text,cents", [
    ("-12.50", -1250), ("12.5", 1250), ("$1,234.56", 123456), ("(45.00)", -4500),
    ("45.00-", -4500), ("10.00 DR", -1000), ("10.00 CR", 1000), ("+3.10", 310),
    ("0.005", 1), ("-0.005", -1), ("0", 0), ("AUD 7.20", 720),
])
def test_parse_amount_valid(text, cents):
    assert parse_amount_to_cents(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "nan", None, "12..5", "Infinity"])
def test_parse_amount_invalid_returns_none(text):
    assert parse_amount_to_cents(text) is None


def test_amounts_are_exact_integers_not_floats():
    # 0.1 + 0.2 != 0.3 in floating point; in cents it is exact.
    total = sum(parse_amount_to_cents(x) for x in ["0.10", "0.20"])
    assert total == parse_amount_to_cents("0.30") == 30


def test_parse_dates_iso_and_day_first():
    s = pd.Series(["2026-03-01", "02/03/2026", "15 Mar 2026", "not a date"])
    out = parse_dates(s)
    assert out.iloc[0].date() == date(2026, 3, 1)
    assert out.iloc[1].date() == date(2026, 3, 2)  # day first: 2 March
    assert out.iloc[2].date() == date(2026, 3, 15)
    assert pd.isna(out.iloc[3])


def test_invalid_rows_are_kept_aside_with_reasons_not_silently_dropped():
    raw = pd.DataFrame({"Date": ["2026-01-01", "bad", "2026-01-03"],
                        "Amount": ["-10", "-5", "oops"], "Description": ["A", "B", "C"]})
    res = build_transactions(raw, ColumnMapping("Date", "Description", amount_col="Amount"))
    assert len(res.transactions) == 1
    assert len(res.invalid) == 2
    assert set(res.invalid["problem"]) == {"date could not be read", "amount could not be read"}
    assert res.warnings


def test_missing_description_is_flagged():
    raw = pd.DataFrame({"Date": ["2026-01-01"], "Amount": ["-10"], "Description": [""]})
    tx = build_transactions(raw, ColumnMapping("Date", "Description", amount_col="Amount")).transactions
    assert bool(tx["missing_description"].iloc[0])


def test_positive_means_money_out_convention():
    raw = pd.DataFrame({"Date": ["2026-01-01"], "Amount": ["25.00"], "Description": ["Coles"]})
    m = ColumnMapping("Date", "Description", amount_col="Amount", sign_convention=SIGN_POSITIVE_OUT)
    assert build_transactions(raw, m).transactions["amount_cents"].iloc[0] == -2500


def test_debit_credit_columns():
    raw = pd.DataFrame({"Date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
                        "Debit": ["12.00", "", "5", ""], "Credit": ["", "100.00", "5", ""],
                        "Details": ["Coles", "Salary", "Both", "Neither"]})
    m = ColumnMapping("Date", "Details", amount_mode="debit_credit", debit_col="Debit", credit_col="Credit")
    res = build_transactions(raw, m)
    assert res.transactions["amount_cents"].tolist() == [-1200, 10000]
    assert len(res.invalid) == 2


def test_duplicates_flagged_without_balance_but_not_removed():
    raw = pd.DataFrame({"Date": ["2026-01-01"] * 3, "Amount": ["-4.50", "-4.50", "-9.00"],
                        "Description": ["Cafe", "Cafe", "Cafe"]})
    tx = build_transactions(raw, ColumnMapping("Date", "Description", amount_col="Amount")).transactions
    assert len(tx) == 3
    assert tx["possible_duplicate"].tolist() == [True, True, False]
    assert "genuine repeat" in tx["duplicate_note"].iloc[0]
    assert tx["txn_id"].nunique() == 3  # identical rows still get distinct, stable IDs


def test_duplicates_with_balance_only_when_balance_identical():
    raw = pd.DataFrame({"Date": ["2026-01-01"] * 3, "Amount": ["-4.50"] * 3,
                        "Description": ["Cafe"] * 3, "Balance": ["95.50", "91.00", "91.00"]})
    m = ColumnMapping("Date", "Description", amount_col="Amount", balance_col="Balance")
    tx = build_transactions(raw, m).transactions
    assert tx["possible_duplicate"].tolist() == [False, True, True]
    assert "very likely" in tx["duplicate_note"].iloc[1]


def test_ids_are_stable_across_runs():
    raw = pd.DataFrame({"Date": ["2026-01-01", "2026-01-02"], "Amount": ["-1", "-2"], "Description": ["A", "B"]})
    m = ColumnMapping("Date", "Description", amount_col="Amount")
    assert build_transactions(raw, m).transactions["txn_id"].tolist() == \
        build_transactions(raw, m).transactions["txn_id"].tolist()


def test_headerless_csv_and_guessed_mapping():
    data = b"01/08/2026,-1850.00,RENT PAUL JONES REALTY,1350.00\n02/08/2026,-5.30,MYKI TOP UP PTV,1344.70\n"
    raw = read_csv_bytes(data, has_header=False)
    m = guess_mapping(raw)
    assert (m.date_col, m.amount_col, m.desc_col, m.balance_col) == ("Column 1", "Column 2", "Column 3", "Column 4")


def test_guessed_mapping_on_sample(sample_path):
    raw = read_csv_bytes(sample_path.read_bytes(), has_header=True)
    m = guess_mapping(raw)
    assert (m.date_col, m.amount_col, m.desc_col, m.balance_col) == ("Date", "Amount", "Description", "Balance")
    res = build_transactions(raw, m)
    assert len(res.invalid) == 0
    assert res.transactions["possible_duplicate"].sum() == 2  # the one duplicated export row (both copies)


def test_guessed_mapping_debit_credit_export():
    data = b"Transaction Date,Details,Debit,Credit\n2026-08-01,COLES,50.00,\n2026-08-10,SALARY,,2000.00\n"
    raw = read_csv_bytes(data, has_header=True)
    m = guess_mapping(raw)
    assert (m.amount_mode, m.debit_col, m.credit_col, m.desc_col) == ("debit_credit", "Debit", "Credit", "Details")
    assert build_transactions(raw, m).transactions["amount_cents"].tolist() == [-5000, 200000]
