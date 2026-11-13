"""Rule-based classification, manual corrections and review flags.

Two separate layers (never mixed):
  Transaction Type  - how money is treated: Expense, Income, Refund, Internal Transfer
  Spending Category - what an Expense (or Refund) was for

Suggestions are rules, not decisions. Anything uncertain is flagged for review.
"""
from __future__ import annotations

import re

import pandas as pd

EXPENSE, INCOME, REFUND, TRANSFER = "Expense", "Income", "Refund", "Internal Transfer"
TRANSACTION_TYPES = [EXPENSE, INCOME, REFUND, TRANSFER]

NOT_APPLICABLE = "Not applicable"
UNCATEGORISED = "Uncategorised"
SPENDING_CATEGORIES = [
    "Groceries", "Dining", "Transport", "Shopping", "Bills", "Housing",
    "Entertainment", "Health", "Education", "Personal Care", "Travel",
    "Subscriptions", "Other", UNCATEGORISED,
]
ALL_CATEGORY_OPTIONS = SPENDING_CATEGORIES + [NOT_APPLICABLE]

CATEGORY_RULES: dict[str, list[str]] = {
    "Groceries": ["woolworths", "coles", "aldi", "iga", "grocery", "groceries", "supermarket", "harris farm"],
    "Dining": ["restaurant", "cafe", "coffee", "mcdonalds", "mcdonald's", "kfc", "uber eats", "doordash",
               "menulog", "bakery", "hungry jacks", "domino's", "dominos", "sushi", "pizza"],
    "Transport": ["myki", "ptv", "opal", "uber", "didi", "taxi", "fuel", "petrol", "parking",
                  "train", "bp", "ampol", "shell", "7-eleven fuel", "linkt", "citylink"],
    "Shopping": ["amazon", "kmart", "target", "big w", "chemist warehouse", "ebay", "jb hi-fi",
                 "officeworks", "bunnings", "ikea", "myer", "david jones"],
    "Bills": ["electricity", "gas bill", "internet", "phone", "telstra", "optus", "vodafone",
              "water", "agl", "origin energy", "insurance"],
    "Housing": ["rent", "real estate", "realty", "property management", "strata", "mortgage"],
    "Entertainment": ["netflix", "spotify", "cinema", "movie", "movies", "hoyts", "steam", "playstation", "xbox"],
    "Health": ["pharmacy", "medical", "doctor", "dental", "dentist", "chemist", "physio", "medicare", "bupa"],
    "Education": ["university", "tafe", "tuition", "textbook", "course fee", "udemy", "coursera"],
    "Personal Care": ["hairdresser", "barber", "salon", "priceline"],
    "Travel": ["qantas", "virgin australia", "jetstar", "airbnb", "booking.com", "hotel", "expedia"],
    "Subscriptions": ["subscription", "monthly membership", "icloud", "google storage", "patreon"],
}

REFUND_TERMS = ["refund", "refunded", "reversal", "reversed", "chargeback", "returned"]
INCOME_TERMS = ["salary", "wage", "wages", "payroll", "dividend", "interest", "centrelink", "pay slip"]
TRANSFER_TERMS = ["transfer", "tfr", "xfer", "trf"]
MASKED_ACCOUNT = re.compile(r"(?<![a-z0-9])xx(\d{3,4})(?![a-z0-9])")


def _word_pattern(keyword: str) -> re.Pattern:
    """Match a keyword as a whole word or phrase, never inside another word.

    'iga' matches 'IGA Richmond' but not 'NAVIGATOR'; 'rent' matches
    'RENT PAYMENT' but not 'CURRENT' or 'PARENT'.
    """
    return re.compile(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])")


_CATEGORY_PATTERNS = [
    (category, kw, _word_pattern(kw)) for category, kws in CATEGORY_RULES.items() for kw in kws
]
_REFUND_PATTERNS = [_word_pattern(t) for t in REFUND_TERMS]
_INCOME_PATTERNS = [_word_pattern(t) for t in INCOME_TERMS]
_TRANSFER_PATTERNS = [_word_pattern(t) for t in TRANSFER_TERMS]


def _has_any(text: str, patterns) -> bool:
    return any(p.search(text) for p in patterns)


def parse_suffixes(text: str) -> list[str]:
    """'1421, 2939 2891' -> ['1421', '2939', '2891']. Only 3-4 digit values are kept."""
    parts = re.split(r"[,;\s]+", str(text or ""))
    return sorted({p.strip() for p in parts if p.strip().isdigit() and 3 <= len(p.strip()) <= 4})


def suggest_category(description: str) -> tuple[str, str]:
    """Return (category, reason). The longest matching keyword wins,
    so 'uber eats' (Dining) beats 'uber' (Transport)."""
    text = str(description).lower()
    best = None
    for category, kw, pat in _CATEGORY_PATTERNS:
        if pat.search(text) and (best is None or len(kw) > len(best[1])):
            best = (category, kw)
    if best:
        return best[0], f"Description contains '{best[1]}'"
    return UNCATEGORISED, "No category rule matched"


def suggest_type(description: str, amount_cents: int, own_suffixes: list[str]) -> tuple[str, str, list[str]]:
    """Return (transaction_type, reason, uncertainty_notes).

    uncertainty_notes is empty when the suggestion is confident.
    """
    text = str(description).lower()
    notes: list[str] = []
    masked = MASKED_ACCOUNT.findall(text)
    is_transfer_text = _has_any(text, _TRANSFER_PATTERNS)

    own_match = [s for s in masked if s in own_suffixes]
    if own_match and is_transfer_text:
        return TRANSFER, f"Transfer mentioning your account xx{own_match[0]}", []
    if own_match:
        notes.append(f"Mentions your account xx{own_match[0]} but not as a transfer")
    unknown = [s for s in masked if s not in own_suffixes]
    if unknown and is_transfer_text:
        notes.append(f"Transfer involving account xx{unknown[0]}, which is not in My Accounts. "
                     "If it is yours, add it in Settings")

    refund_words = _has_any(text, _REFUND_PATTERNS)
    if amount_cents > 0 and refund_words:
        return REFUND, "Money in with refund wording", notes
    if amount_cents < 0 and refund_words:
        notes.append("Refund wording, but money left the account")
        return EXPENSE, "Money out", notes
    if amount_cents > 0:
        if _has_any(text, _INCOME_PATTERNS):
            return INCOME, "Money in with income wording", notes
        notes.append("Money in without income wording: confirm it is income, not a refund or own transfer")
        return INCOME, "Money in", notes
    if amount_cents < 0:
        return EXPENSE, "Money out", notes
    notes.append("Zero amount")
    return EXPENSE, "Zero amount", notes


def classify(tx: pd.DataFrame, own_suffixes: list[str]) -> pd.DataFrame:
    """Add suggested type, category, reasons and uncertainty notes."""
    out = tx.copy()
    types, reasons, notes, cats, cat_reasons = [], [], [], [], []
    for desc, amt in zip(out["description"], out["amount_cents"]):
        t, r, n = suggest_type(desc, int(amt), own_suffixes)
        if t in (EXPENSE, REFUND):
            c, cr = suggest_category(desc)
        else:
            c, cr = NOT_APPLICABLE, "No spending category for this type"
        types.append(t); reasons.append(r); notes.append(n); cats.append(c); cat_reasons.append(cr)
    out["transaction_type"] = types
    out["spending_category"] = cats
    out["suggestion_reason"] = [f"{r}. {cr}." for r, cr in zip(reasons, cat_reasons)]
    out["uncertainty_notes"] = notes
    out["user_edited"] = False
    out["reviewed"] = False
    out["excluded"] = False
    return out


def apply_overrides(tx: pd.DataFrame, overrides: dict[str, dict]) -> pd.DataFrame:
    """Apply manual corrections, keyed by stable transaction ID.

    Keys inside each override: transaction_type, spending_category, reviewed, excluded.
    Corrections for IDs not in this file are ignored (kept for when they return).
    """
    if not overrides:
        return tx
    out = tx.copy()
    idx = {tid: i for i, tid in enumerate(out["txn_id"])}
    for tid, ov in overrides.items():
        i = idx.get(tid)
        if i is None:
            continue
        for col in ("transaction_type", "spending_category"):
            if col in ov and ov[col] is not None:
                out.at[out.index[i], col] = ov[col]
                out.at[out.index[i], "user_edited"] = True
        for col in ("reviewed", "excluded"):
            if col in ov:
                out.at[out.index[i], col] = bool(ov[col])
    # A type change can leave a stale category: spending types need one, others do not.
    spend_types = out["transaction_type"].isin([EXPENSE, REFUND])
    out.loc[~spend_types, "spending_category"] = NOT_APPLICABLE
    out.loc[spend_types & out["spending_category"].eq(NOT_APPLICABLE), "spending_category"] = UNCATEGORISED
    return out


def sign_conflict(t: str, amount_cents: int) -> bool:
    """True when the type cannot be right for the amount's direction."""
    return (t == EXPENSE and amount_cents > 0) or (t in (REFUND, INCOME) and amount_cents < 0)


def compute_review(tx: pd.DataFrame) -> pd.DataFrame:
    """Add `review_reasons` (list) and `needs_review` (bool) and `review_status`.

    Blocking problems stay flagged even after 'reviewed' is ticked, because they
    change totals: a type/sign conflict and an Expense with no category.
    Soft notes (uncertain suggestion, possible duplicate) clear once the user
    edits the row or ticks 'reviewed'.
    """
    out = tx.copy()
    all_reasons, statuses = [], []
    for row in out.itertuples(index=False):
        hard, soft = [], []
        if row.excluded:
            all_reasons.append(["Excluded by you: not in any total"])
            statuses.append("Excluded")
            continue
        if sign_conflict(row.transaction_type, int(row.amount_cents)):
            direction = "money in" if row.amount_cents > 0 else "money out"
            hard.append(f"{row.transaction_type} cannot be {direction}: not counted in totals until fixed")
        if row.transaction_type == EXPENSE and row.spending_category == UNCATEGORISED:
            hard.append("Expense has no spending category")
        if not (row.user_edited or row.reviewed):
            soft.extend(row.uncertainty_notes)
            if row.missing_description:
                soft.append("Missing description")
            if row.possible_duplicate:
                soft.append(row.duplicate_note)
        reasons = hard + soft
        all_reasons.append(reasons)
        if reasons:
            statuses.append("Needs review")
        elif row.user_edited or row.reviewed:
            statuses.append("Reviewed")
        else:
            statuses.append("OK")
    out["review_reasons"] = all_reasons
    out["needs_review"] = [s == "Needs review" for s in statuses]
    out["review_status"] = statuses
    return out
