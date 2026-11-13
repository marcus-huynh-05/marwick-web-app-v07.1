import pytest

from marwick.classify import (
    EXPENSE, INCOME, NOT_APPLICABLE, REFUND, TRANSFER, UNCATEGORISED, parse_suffixes, suggest_category,
    suggest_type,
)


# --- Bug 3 from the assessment: keywords matched inside other words
@pytest.mark.parametrize("desc,expected", [
    ("NAVIGATOR CAFE SOUTHBANK", "Dining"),     # was Groceries via 'iga'
    ("CURRENT ACCOUNT FEE", UNCATEGORISED),       # was Housing via 'rent'
    ("PARENT TEACHER ASSOC", UNCATEGORISED),      # was Housing via 'rent'
    ("PERSONAL TRAINER", UNCATEGORISED),          # was Transport via 'train'
    ("WATERFRONT BAR", UNCATEGORISED),            # was Bills via 'water'
    ("STEAMBOAT HOUSE", UNCATEGORISED),           # was Entertainment via 'steam'
])
def test_no_matches_inside_other_words(desc, expected):
    assert suggest_category(desc)[0] == expected


@pytest.mark.parametrize("desc,expected", [
    ("IGA RICHMOND", "Groceries"), ("RENT PAUL JONES REALTY", "Housing"), ("WOOLWORTHS 3121", "Groceries"),
    ("UBER EATS SYDNEY", "Dining"), ("UBER TRIP", "Transport"),          # longest keyword wins
    ("CHEMIST WAREHOUSE", "Shopping"), ("TERRYWHITE PHARMACY", "Health"),
    ("STEAM GAMES", "Entertainment"),
])
def test_whole_word_matches(desc, expected):
    assert suggest_category(desc)[0] == expected


# --- Bugs 1 and 2: refund wording ignored the amount's sign
def test_negative_amount_with_refund_or_cashback_wording_is_expense_and_flagged():
    t, _, notes = suggest_type("WOOLWORTHS CASHBACK", -5000, [])
    assert t == EXPENSE and not notes  # cashback/cash-out is money out: an ordinary Expense
    t, _, notes = suggest_type("REFUND PROCESSING FEE", -500, [])
    assert t == EXPENSE and any("refund wording" in n.lower() for n in notes)


def test_return_trip_is_not_a_refund():
    assert suggest_type("RETURN TRIP BUS TICKET", -1200, [])[0] == EXPENSE


def test_positive_refund_is_refund():
    t, _, notes = suggest_type("AMAZON AU REFUND", 12900, [])
    assert t == REFUND and not notes


# --- Income
def test_salary_is_confident_income():
    t, _, notes = suggest_type("SALARY ACME PTY LTD", 265000, [])
    assert t == INCOME and not notes


def test_unexplained_money_in_is_income_but_flagged():
    t, _, notes = suggest_type("PAYPAL *MARKETPLACE", 4500, [])
    assert t == INCOME and notes


# --- Internal transfers vs external payments
def test_own_account_transfer_is_internal():
    assert suggest_type("TRANSFER TO XX1421 SAVINGS", -50000, ["1421"])[0] == TRANSFER
    assert suggest_type("TRANSFER FROM XX1421", 20000, ["1421"])[0] == TRANSFER


def test_transfer_to_unknown_account_is_external_expense_and_flagged():
    t, _, notes = suggest_type("TRANSFER TO XX9876 J SMITH", -30000, ["1421"])
    assert t == EXPENSE
    assert any("xx9876" in n for n in notes)


def test_transfer_to_named_person_is_not_internal():
    t, _, _ = suggest_type("TRANSFER TO JOHN SMITH RENT", -50000, ["1421"])
    assert t == EXPENSE
    assert suggest_category("TRANSFER TO JOHN SMITH RENT")[0] == "Housing"


def test_suffix_must_be_whole_number():
    # xx14210 must not match suffix 1421
    assert suggest_type("TRANSFER TO XX14210", -100, ["1421"])[0] == EXPENSE


def test_zero_amount_flagged():
    t, _, notes = suggest_type("ADJUSTMENT", 0, [])
    assert notes


def test_parse_suffixes():
    assert parse_suffixes("1421, 2939;2891  abc 12 99999") == ["1421", "2891", "2939"]


# --- Pipeline-level: review flags, overrides, categories per type
def test_review_flags_and_categories(build):
    tx = build([
        ("2026-01-02", "-50.00", "WOOLWORTHS 1"),
        ("2026-01-03", "-38.00", "UNKNOWN MERCHANT"),
        ("2026-01-04", "2650.00", "SALARY ACME"),
        ("2026-01-05", "-10.00", ""),
    ])
    by = dict(zip(tx["description"], tx.itertuples()))
    assert not by["WOOLWORTHS 1"].needs_review
    assert by["UNKNOWN MERCHANT"].needs_review
    assert "no spending category" in " ".join(by["UNKNOWN MERCHANT"].review_reasons).lower()
    assert by["SALARY ACME"].spending_category == NOT_APPLICABLE
    assert by[""].needs_review and "Missing description" in by[""].review_reasons


def test_manual_corrections_survive_reprocessing_with_new_settings(build):
    rows = [("2026-01-02", "-38.00", "UNKNOWN MERCHANT"), ("2026-01-03", "-500.00", "TRANSFER TO XX1421")]
    first = build(rows)
    tid = first.loc[first["description"] == "UNKNOWN MERCHANT", "txn_id"].iloc[0]
    overrides = {tid: {"spending_category": "Dining"}}
    # Re-run with a different own-account setting (this used to reset edits in v0.6).
    second = build(rows, suffixes=["1421"], overrides=overrides)
    row = second.set_index("txn_id").loc[tid]
    assert row["spending_category"] == "Dining" and row["review_status"] == "Reviewed"
    assert second.loc[second["description"] == "TRANSFER TO XX1421", "transaction_type"].iloc[0] == TRANSFER


def test_type_change_to_income_clears_category(build):
    rows = [("2026-01-02", "45.00", "PAYPAL")]
    tid = build(rows)["txn_id"].iloc[0]
    tx = build(rows, overrides={tid: {"transaction_type": REFUND}})
    assert tx["transaction_type"].iloc[0] == REFUND
    assert tx["spending_category"].iloc[0] == UNCATEGORISED
    tx = build(rows, overrides={tid: {"transaction_type": INCOME, "spending_category": "Dining"}})
    assert tx["spending_category"].iloc[0] == NOT_APPLICABLE


def test_sign_conflict_stays_flagged_even_when_marked_reviewed(build):
    rows = [("2026-01-02", "-50.00", "SOMETHING")]
    tid = build(rows)["txn_id"].iloc[0]
    tx = build(rows, overrides={tid: {"transaction_type": REFUND, "reviewed": True}})
    assert tx["needs_review"].iloc[0]
    assert "cannot be money out" in tx["review_reasons"].iloc[0][0]


def test_duplicate_flag_clears_when_reviewed(build):
    rows = [("2026-01-02", "-4.50", "SEVEN SEEDS CAFE"), ("2026-01-02", "-4.50", "SEVEN SEEDS CAFE")]
    tx = build(rows)
    assert tx["needs_review"].all()
    overrides = {t: {"reviewed": True} for t in tx["txn_id"]}
    assert not build(rows, overrides=overrides)["needs_review"].any()
