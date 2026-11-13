"""Reading and validating bank CSV exports.

Turns a raw CSV table plus a column mapping into clean transactions:
dates parsed, amounts as integer cents, invalid rows kept aside with a
reason (never silently dropped), and possible duplicates flagged.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd

from .utils import stable_txn_id

SIGN_NEGATIVE_OUT = "negative_out"  # -12.50 means money left the account (most banks)
SIGN_POSITIVE_OUT = "positive_out"  # 12.50 means money left the account (some card exports)


@dataclass
class ColumnMapping:
    date_col: str
    desc_col: str
    amount_mode: str = "single"  # "single" or "debit_credit"
    amount_col: str | None = None
    debit_col: str | None = None
    credit_col: str | None = None
    sign_convention: str = SIGN_NEGATIVE_OUT
    balance_col: str | None = None
    dayfirst: bool = True


@dataclass
class ParseResult:
    transactions: pd.DataFrame
    invalid: pd.DataFrame  # original rows that could not be used, with a reason
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- reading
def read_csv_bytes(data: bytes, has_header: bool) -> pd.DataFrame:
    """Read CSV bytes as text columns (no type guessing, so nothing is lost)."""
    raw = pd.read_csv(
        io.BytesIO(data),
        header=0 if has_header else None,
        dtype=str,
        keep_default_na=False,
        skip_blank_lines=True,
        encoding_errors="replace",
    )
    if not has_header:
        raw.columns = [f"Column {i + 1}" for i in range(raw.shape[1])]
    else:
        raw.columns = [str(c).strip() for c in raw.columns]
    return raw


# ---------------------------------------------------------------- amounts
_AMOUNT_JUNK = re.compile(r"[\s$£€,]|AUD|USD|GBP|EUR|VND", re.IGNORECASE)


def parse_amount_to_cents(value) -> int | None:
    """Parse one amount into integer cents. Returns None if it is not a number.

    Handles '$1,234.56', '-12.50', '(12.50)', '12.50-', '12.50 DR', '12.50 CR'.
    Uses Decimal, never float, and rounds half-up to the cent.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None
    sign = 1
    upper = text.upper()
    if upper.endswith("DR"):
        sign, text = -1, text[:-2]
    elif upper.endswith("CR"):
        text = text[:-2]
    text = _AMOUNT_JUNK.sub("", text)
    if text.startswith("(") and text.endswith(")"):
        sign, text = -sign, text[1:-1]
    if text.endswith("-"):
        sign, text = -sign, text[:-1]
    if text.startswith("+"):
        text = text[1:]
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if not amount.is_finite():
        return None
    cents = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return sign * int(cents)


# ---------------------------------------------------------------- dates
def parse_dates(series: pd.Series, dayfirst: bool = True) -> pd.Series:
    """Parse dates. ISO (2026-03-01) first, then common bank formats.

    Each value is parsed on its own, so one odd row cannot change how the
    rest of the column is read.
    """
    text = series.astype(str).str.strip()
    out = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    formats = ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%d.%m.%Y"]
    if not dayfirst:
        formats = ["%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%b %d %Y", "%B %d %Y"] + formats
    for fmt in formats:
        missing = out.isna()
        if not missing.any():
            break
        out.loc[missing] = pd.to_datetime(text[missing], format=fmt, errors="coerce")
    return out.dt.normalize()


# ---------------------------------------------------------------- mapping guess
def guess_mapping(raw: pd.DataFrame) -> ColumnMapping:
    """Best-effort default mapping from header names, then from content."""
    cols = list(raw.columns)
    lower = {c: str(c).lower() for c in cols}

    def by_name(*words):
        for c in cols:
            if any(w in lower[c] for w in words):
                return c
        return None

    sample = raw.head(50)

    def date_score(c):
        return parse_dates(sample[c]).notna().mean() if len(sample) else 0

    def num_score(c):
        vals = sample[c].map(parse_amount_to_cents)
        return vals.notna().mean() if len(sample) else 0

    date_col = by_name("date") or max(cols, key=date_score)
    debit_col, credit_col = by_name("debit", "withdrawal"), by_name("credit", "deposit")
    balance_col = by_name("balance")
    amount_col = by_name("amount", "value")
    use_dc = amount_col is None and debit_col is not None and credit_col is not None and debit_col != credit_col
    if amount_col is None and not use_dc:
        numeric = [c for c in cols if c not in (date_col, balance_col) and num_score(c) > 0.8]
        amount_col = numeric[0] if numeric else (cols[1] if len(cols) > 1 else cols[0])
    taken = {date_col, amount_col, balance_col, debit_col if use_dc else None, credit_col if use_dc else None}
    desc_col = by_name("description", "narrative", "details", "merchant", "payee", "memo")
    if desc_col is None or desc_col in taken:
        others = [c for c in cols if c not in taken]
        desc_col = max(others, key=lambda c: sample[c].astype(str).str.len().mean()) if others else cols[0]
    # A headerless CommBank-style export has a running balance as the last numeric column.
    if balance_col is None and len(cols) >= 4:
        last = cols[-1]
        if last not in (date_col, amount_col, desc_col) and num_score(last) > 0.8:
            balance_col = last
    return ColumnMapping(
        date_col=date_col,
        desc_col=desc_col,
        amount_mode="debit_credit" if use_dc else "single",
        amount_col=amount_col,
        debit_col=debit_col,
        credit_col=credit_col,
        balance_col=balance_col,
    )


# ---------------------------------------------------------------- build
def build_transactions(raw: pd.DataFrame, m: ColumnMapping) -> ParseResult:
    """Convert raw CSV text into clean transactions plus a list of invalid rows."""
    n = len(raw)
    reasons = [[] for _ in range(n)]

    dates = parse_dates(raw[m.date_col], dayfirst=m.dayfirst)
    descriptions = raw[m.desc_col].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)

    if m.amount_mode == "debit_credit":
        # Plain lists, not Series.map: pandas would turn None into NaN and hide bad values.
        debit = [parse_amount_to_cents(v) for v in raw[m.debit_col]]
        credit = [parse_amount_to_cents(v) for v in raw[m.credit_col]]
        amounts = []
        for i, (d, c) in enumerate(zip(debit, credit)):
            d_val = abs(d) if d is not None else None
            c_val = abs(c) if c is not None else None
            if d_val and c_val:
                reasons[i].append("both debit and credit contain a value")
                amounts.append(None)
            elif d_val:
                amounts.append(-d_val)
            elif c_val:
                amounts.append(c_val)
            elif d is not None or c is not None:
                amounts.append(0)
            else:
                amounts.append(None)
    else:
        parsed = [parse_amount_to_cents(v) for v in raw[m.amount_col]]
        flip = -1 if m.sign_convention == SIGN_POSITIVE_OUT else 1
        amounts = [None if v is None else v * flip for v in parsed]

    for i in range(n):
        if pd.isna(dates.iloc[i]):
            reasons[i].append("date could not be read")
        if amounts[i] is None and not any("debit" in r for r in reasons[i]):
            reasons[i].append("amount could not be read")

    balances = [parse_amount_to_cents(v) for v in raw[m.balance_col]] if m.balance_col else [None] * n

    valid_mask = [len(r) == 0 for r in reasons]
    invalid = raw.loc[[not v for v in valid_mask]].copy()
    invalid.insert(0, "csv_row", [i + 1 for i, v in enumerate(valid_mask) if not v])
    invalid["problem"] = ["; ".join(r) for r, v in zip(reasons, valid_mask) if not v]

    tx = pd.DataFrame({
        "csv_row": range(1, n + 1),
        "date": dates,
        "description": descriptions,
        "amount_cents": pd.Series(amounts, dtype=object),  # object keeps exact ints (no float step)
        "balance_cents": balances,
    }).loc[valid_mask].reset_index(drop=True)
    tx["amount_cents"] = [int(a) for a in tx["amount_cents"]]
    tx["amount_cents"] = tx["amount_cents"].astype("int64")
    tx["balance_cents"] = pd.array(
        [None if (b is None or pd.isna(b)) else int(b) for b in tx["balance_cents"]], dtype="Int64"
    )
    tx["missing_description"] = tx["description"].eq("") | tx["description"].str.lower().isin(["nan", "none"])

    # Stable IDs: identical rows get an occurrence counter.
    date_text = tx["date"].dt.strftime("%Y-%m-%d")
    occ = tx.groupby([date_text, tx["description"], tx["amount_cents"]]).cumcount()
    tx["txn_id"] = [
        stable_txn_id(d, desc, int(a), int(o))
        for d, desc, a, o in zip(date_text, tx["description"], tx["amount_cents"], occ)
    ]

    tx = flag_duplicates(tx, has_balance=m.balance_col is not None)

    warnings = []
    if len(invalid):
        warnings.append(f"{len(invalid)} row(s) could not be read and are listed separately. They are not in any total.")
    return ParseResult(transactions=tx, invalid=invalid.reset_index(drop=True), warnings=warnings)


def flag_duplicates(tx: pd.DataFrame, has_balance: bool) -> pd.DataFrame:
    """Flag rows that look like duplicates. Nothing is removed automatically.

    Without a balance column, two identical rows may be two genuine purchases
    (two coffees on one day), so they are flagged for the user to decide.
    With a balance column, a genuine repeat purchase changes the running
    balance, so rows identical *including* balance are very likely duplicates.
    """
    keys = ["date", "description", "amount_cents"] + (["balance_cents"] if has_balance else [])
    key_frame = tx[keys].astype(str)
    dup = key_frame.duplicated(keep=False)
    tx = tx.copy()
    tx["possible_duplicate"] = dup.to_numpy()
    tx["duplicate_note"] = ""
    if dup.any():
        note = (
            "Identical date, description, amount and balance: very likely a duplicate row"
            if has_balance
            else "Identical date, description and amount: may be a duplicate or a genuine repeat purchase"
        )
        tx.loc[dup.to_numpy(), "duplicate_note"] = note
    return tx
