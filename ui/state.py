"""Session state and the per-run data pipeline for the Streamlit app.

Uploaded files live only in this browser session's memory (st.session_state).
Nothing is written to disk, and st.cache_data is deliberately not used, because
its cache is shared across sessions and outlives them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from marwick.classify import parse_suffixes
from marwick.engine import Comparison, compare_periods, validate_periods
from marwick.insights import Insight, generate_insights
from marwick.pipeline import Prepared, prepare
from marwick.utils import preset_periods
from marwick.validators import ColumnMapping, guess_mapping, read_csv_bytes

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "sample_transactions.csv"
CURRENCIES = ["AUD", "USD", "GBP", "EUR", "NZD", "VND"]
PRESETS = {
    "split_half": "Split file in half",
    "last_30": "Last 30 days vs previous 30",
    "last_month": "Latest month vs previous month",
    "last_7": "Last 7 days vs previous 7",
    "custom": "Custom dates",
}
PAGES = ["Overview", "Analyse Spending", "Transactions", "Insights", "Settings"]

DEFAULT_CFG = {
    "currency": "AUD",
    "suffixes_text": "",
    "has_header": True,
    "mapping": None,       # dict form of ColumnMapping, guessed on upload
    "preset": "split_half",
    "period_a": None,      # (start, end)
    "period_b": None,
}


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("cfg", dict(DEFAULT_CFG))
    ss.setdefault("file_name", None)
    ss.setdefault("file_bytes", None)
    ss.setdefault("overrides", {})
    ss.setdefault("editor_ver", 0)
    ss.setdefault("nav", "Overview")
    ss.setdefault("step", "Upload")


def cfg() -> dict:
    return st.session_state["cfg"]


# ---------------------------------------------------------------- widget binding
def bind(name: str, scope: str) -> str:
    """Return a widget key whose value persists in cfg[name] across pages.

    Streamlit forgets a widget's state when the widget is not drawn, so the
    real value lives in cfg and each widget copies it in and out.
    """
    wkey = f"_w_{scope}_{name}"
    if wkey not in st.session_state:
        st.session_state[wkey] = cfg()[name]
    return wkey


def sync(name: str, wkey: str) -> None:
    cfg()[name] = st.session_state[wkey]
    if name == "has_header":
        cfg()["mapping"] = None  # columns change, so the mapping must be re-guessed
        _forget_widgets("mapping")


def _forget_widgets(fragment: str = "") -> None:
    for k in [k for k in st.session_state if k.startswith("_w_") and fragment in k]:
        del st.session_state[k]


def go(page: str, step: str | None = None) -> None:
    st.session_state["nav"] = page
    if step:
        st.session_state["step"] = step


# ---------------------------------------------------------------- data loading
def load_file(name: str, data: bytes, suffixes_text: str | None = None) -> None:
    ss = st.session_state
    ss["file_name"], ss["file_bytes"] = name, data
    c = cfg()
    c["mapping"], c["period_a"], c["period_b"], c["preset"] = None, None, None, "split_half"
    if suffixes_text is not None:
        c["suffixes_text"] = suffixes_text
    ss["overrides"] = {}
    ss["editor_ver"] += 1
    _forget_widgets()


def load_sample() -> None:
    load_file("sample_transactions.csv", SAMPLE.read_bytes(), suffixes_text="1421")
    st.session_state["_toast"] = "Sample data loaded. Account xx1421 is set as one of your own accounts."


def clear_session() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_state()


def set_mapping(m: ColumnMapping) -> None:
    cfg()["mapping"] = asdict(m)


def current_mapping() -> ColumnMapping | None:
    d = cfg()["mapping"]
    return ColumnMapping(**d) if d else None


def apply_preset(preset: str, min_d: date, max_d: date) -> None:
    c = cfg()
    c["preset"] = preset
    res = preset_periods(min_d, max_d, preset)
    if res:
        c["period_a"], c["period_b"] = res


# ---------------------------------------------------------------- per-run bundle
@dataclass
class Data:
    file_name: str
    raw: pd.DataFrame
    mapping: ColumnMapping
    suffixes: list[str]
    prepared: Prepared
    min_date: date | None
    max_date: date | None
    period_a: tuple[date, date] | None
    period_b: tuple[date, date] | None
    period_errors: list[str] = field(default_factory=list)
    comparison: Comparison | None = None
    insights: list[Insight] = field(default_factory=list)
    error: str | None = None

    @property
    def tx(self) -> pd.DataFrame:
        return self.prepared.transactions

    @property
    def currency(self) -> str:
        return cfg()["currency"]

    @property
    def ready(self) -> bool:
        return self.comparison is not None


def get_data() -> Data | None | str:
    """Run the pipeline for this rerun. Returns None (no file), an error string, or Data."""
    ss = st.session_state
    if not ss.get("file_bytes"):
        return None
    c = cfg()
    try:
        raw = read_csv_bytes(ss["file_bytes"], c["has_header"])
    except Exception as exc:  # malformed file
        return f"Could not read this CSV: {exc}"
    if raw.empty or raw.shape[1] < 3:
        return "The CSV needs at least three columns: date, description and amount."
    m = current_mapping()
    cols = set(raw.columns)
    if m is None or not {m.date_col, m.desc_col}.issubset(cols) or (
        m.amount_mode == "single" and m.amount_col not in cols) or (
        m.amount_mode == "debit_credit" and not {m.debit_col, m.credit_col}.issubset(cols)):
        m = guess_mapping(raw)
        set_mapping(m)
    if m.balance_col and m.balance_col not in cols:
        m.balance_col = None
    suffixes = parse_suffixes(c["suffixes_text"])
    try:
        prepared = prepare(raw, m, suffixes, ss["overrides"])
    except Exception as exc:
        return f"These column settings could not be processed: {exc}. Check the mapping in Analyse Spending."
    tx = prepared.transactions
    data = Data(ss["file_name"], raw, m, suffixes, prepared, None, None, None, None)
    if tx.empty:
        data.error = "No valid transactions remain after reading the file. Check the header setting and column mapping."
        return data
    data.min_date, data.max_date = tx["date"].min().date(), tx["date"].max().date()
    if data.min_date == data.max_date:
        data.error = "The file only covers one date. Upload data that covers two periods to compare."
        return data
    if c["period_a"] is None or c["period_b"] is None:
        apply_preset(c["preset"] if c["preset"] != "custom" else "split_half", data.min_date, data.max_date)
    data.period_a, data.period_b = tuple(c["period_a"]), tuple(c["period_b"])
    data.period_errors = validate_periods(data.period_a, data.period_b)
    if not data.period_errors:
        data.comparison = compare_periods(tx, data.period_a, data.period_b)
        data.insights = generate_insights(tx, data.comparison, data.currency)
    return data
