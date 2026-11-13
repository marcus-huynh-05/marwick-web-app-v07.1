import re

import pandas as pd
import streamlit as st

from marwick.classify import EXPENSE, MASKED_ACCOUNT, REFUND, TRANSACTION_TYPES, TRANSFER_TERMS
from marwick.engine import weekly_net_spending
from marwick.utils import cents_to_float
from marwick.validators import SIGN_NEGATIVE_OUT, SIGN_POSITIVE_OUT
from .. import components as c
from .. import state
from ..theme import chips, esc, note, page_header, section

STEPS = ["Upload", "Map columns", "Accounts", "Types", "Categories", "Periods", "Results"]
STEP_KEY = "_w_analyse_step"


def _set_step(step: str) -> None:
    st.session_state["step"] = step
    st.session_state.pop(STEP_KEY, None)


def _stepper(has_data: bool) -> str:
    if STEP_KEY not in st.session_state:
        st.session_state[STEP_KEY] = st.session_state.get("step", "Upload")

    def _sync():
        v = st.session_state[STEP_KEY]
        if v is None:  # clicking the active segment deselects it; keep the current step
            st.session_state[STEP_KEY] = st.session_state["step"]
        else:
            st.session_state["step"] = v

    options = STEPS if has_data else STEPS[:1]
    if st.session_state[STEP_KEY] not in options:
        st.session_state[STEP_KEY] = options[0]
    st.segmented_control("Workflow step", options, key=STEP_KEY, on_change=_sync, label_visibility="collapsed",
                         format_func=lambda s: f"{STEPS.index(s) + 1}  {s}", width="stretch")
    return st.session_state[STEP_KEY] or "Upload"


def _nav_buttons(step: str, can_next: bool = True) -> None:
    i = STEPS.index(step)
    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
    left, _, right = st.columns([1, 3, 1])
    with left:
        if i > 0:
            st.button("Back", key=f"back_{step}", on_click=_set_step, args=(STEPS[i - 1],), width="stretch")
    with right:
        if i < len(STEPS) - 1:
            st.button(f"Next: {STEPS[i + 1]}", key=f"next_{step}", type="primary", disabled=not can_next,
                      on_click=_set_step, args=(STEPS[i + 1],), width="stretch")


# ---------------------------------------------------------------- steps
def step_upload(d) -> None:
    section("Transaction file")
    if st.session_state.get("file_name"):
        chips([(f"Loaded: {st.session_state['file_name']}", "on")])
        with st.expander("Replace with another file"):
            c.uploader("analyse")
    else:
        c.uploader("analyse")
        st.button("Use sample data instead", on_click=state.load_sample)
    if not st.session_state.get("file_name"):
        return
    key = state.bind("has_header", "analyse")
    st.radio("Does the first row contain column names?", [True, False], key=key, horizontal=True,
             format_func=lambda v: "Yes, it has a header row" if v else "No, it starts with a transaction",
             on_change=state.sync, args=("has_header", key))
    if isinstance(d, str):
        st.error(d)
        return
    section("Preview")
    st.dataframe(d.raw.head(8), hide_index=True, width="stretch")
    st.caption(f"{len(d.raw):,} rows · {d.raw.shape[1]} columns. Showing the first 8 rows exactly as read.")
    _nav_buttons("Upload")


def _mapping_widget(kind, label, field, options, d, **kw):
    m = state.cfg()["mapping"]
    key = f"_w_mapping_{field}"
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key] = m.get(field) if m.get(field) in options else options[0]

    def _sync():
        state.cfg()["mapping"][field] = st.session_state[key]
    return kind(label, options, key=key, on_change=_sync, **kw)


def step_map(d) -> None:
    cols = list(d.raw.columns)
    m = state.cfg()["mapping"]
    section("Required columns")
    a, b = st.columns(2)
    with a:
        _mapping_widget(st.selectbox, "Date", "date_col", cols, d)
    with b:
        _mapping_widget(st.selectbox, "Description", "desc_col", cols, d)
    _mapping_widget(st.radio, "How does your file record amounts?", "amount_mode", ["single", "debit_credit"], d,
                    horizontal=True, format_func=lambda v: "One amount column" if v == "single"
                    else "Separate debit and credit columns")
    if m["amount_mode"] == "single":
        a, b = st.columns(2)
        with a:
            _mapping_widget(st.selectbox, "Amount", "amount_col", cols, d)
        with b:
            _mapping_widget(st.selectbox, "Sign convention", "sign_convention", [SIGN_NEGATIVE_OUT, SIGN_POSITIVE_OUT], d,
                            format_func=lambda v: "Negative = money out (most banks)" if v == SIGN_NEGATIVE_OUT
                            else "Positive = money out (some card exports)")
    else:
        a, b = st.columns(2)
        with a:
            _mapping_widget(st.selectbox, "Debit (money out)", "debit_col", cols, d)
        with b:
            _mapping_widget(st.selectbox, "Credit (money in)", "credit_col", cols, d)
    section("Optional")
    a, b = st.columns(2)
    with a:
        _mapping_widget(st.selectbox, "Running balance", "balance_col", [None] + cols, d,
                        format_func=lambda v: "Not available" if v is None else v,
                        help="Reference only, never counted as income or spending. Improves duplicate detection.")
    with b:
        _mapping_widget(st.selectbox, "Date format", "dayfirst", [True, False], d,
                        format_func=lambda v: "Day first (31/12/2026)" if v else "Month first (12/31/2026)")

    section("Result")
    tx, inv = d.tx, d.prepared.invalid
    items = [(f"{len(tx):,} valid transactions", "on")]
    if len(inv): items.append((f"{len(inv)} unreadable rows (not in any total)", "warn"))
    if tx["possible_duplicate"].any(): items.append((f"{int(tx['possible_duplicate'].sum())} possible duplicates", "warn"))
    if d.min_date: items.append((f"{d.min_date:%d %b %Y} to {d.max_date:%d %b %Y}", ""))
    chips(items)
    if d.error:
        st.error(d.error)
    if len(inv):
        with st.expander(f"Unreadable rows ({len(inv)})", expanded=len(inv) > 0.2 * max(len(d.raw), 1)):
            st.dataframe(inv, hide_index=True, width="stretch")
            st.caption("These rows are listed for transparency and are excluded from every total. "
                       "Many unreadable rows usually means the header setting or a column choice is wrong.")
    if not tx.empty:
        prev = pd.DataFrame({"Date": tx["date"].dt.date.head(6), "Description": tx["description"].head(6),
                             "Amount": tx["amount_cents"].head(6).map(cents_to_float)})
        st.dataframe(prev, hide_index=True, width="stretch",
                     column_config={"Amount": st.column_config.NumberColumn(f"Amount ({d.currency})", format="%.2f"),
                                    "Date": st.column_config.DateColumn(format="DD/MM/YYYY")})
        st.caption("Check the signs: money you spent should be negative here.")
    _nav_buttons("Map columns", can_next=not tx.empty)


def _detected_accounts(d) -> pd.DataFrame:
    rows = {}
    pat = re.compile("|".join(TRANSFER_TERMS))
    for desc in d.tx["description"]:
        low = desc.lower()
        for suf in MASKED_ACCOUNT.findall(low):
            r = rows.setdefault(suf, {"mentions": 0, "transfers": 0})
            r["mentions"] += 1
            r["transfers"] += bool(pat.search(low))
    return pd.DataFrame([{"Account": f"xx{s}", "Transfer descriptions": v["transfers"], "All mentions": v["mentions"],
                          "In My Accounts": s in d.suffixes} for s, v in sorted(rows.items())])


def step_accounts(d) -> None:
    section("Currency")
    key = state.bind("currency", "analyse")
    st.selectbox("Currency of this file", state.CURRENCIES, key=key, on_change=state.sync, args=("currency", key),
                 help="One currency per file. No conversion is performed.")
    section("My Accounts")
    st.markdown('<div class="mw-sub" style="margin-top:-4px">Enter the last digits of <b>your own</b> accounts as they '
                'appear in masked transfer descriptions (for example <b>xx1421</b>). Only transfers mentioning these '
                'accounts become Internal Transfers. A transfer to a person or business stays an Expense.</div>',
                unsafe_allow_html=True)
    key = state.bind("suffixes_text", "analyse")
    st.text_input("My account suffixes", key=key, on_change=state.sync, args=("suffixes_text", key),
                  placeholder="e.g. 1421, 2939")
    det = _detected_accounts(d)
    if det.empty:
        st.caption("No masked account numbers (like xx1234) were found in this file's descriptions.")
    else:
        st.markdown("**Masked accounts found in this file**")
        st.dataframe(det, hide_index=True, width="stretch")
        st.caption("Add an account above only if it belongs to you. Unknown accounts are flagged for review.")
    _nav_buttons("Accounts")


def step_types(d) -> None:
    tx = d.tx
    counts = tx["transaction_type"].value_counts()
    chips([(f"{t}: {int(counts.get(t, 0))}", "on") for t in TRANSACTION_TYPES])
    note("Transaction Type decides how money is treated: Expenses count as spending, Refunds reduce it, "
         "Income is external money in, and Internal Transfers between your own accounts count as neither.")
    show = st.segmented_control("Show", ["Needs review", "All"], default="Needs review", key="types_filter")
    view = tx[tx["needs_review"]] if show != "All" else tx
    if show != "All" and view.empty:
        st.success("Nothing needs review. Switch to All to check any transaction.")
    c.transaction_editor(d, view, "types")
    _nav_buttons("Types")


def step_categories(d) -> None:
    tx = d.tx
    spend = tx[tx["transaction_type"].isin([EXPENSE, REFUND])]
    counts = spend["spending_category"].value_counts()
    chips([(f"{k}: {int(v)}", "warn" if k == "Uncategorised" else "on") for k, v in counts.items()])
    note("Spending Category explains what an Expense was for. Refunds keep the category of the purchase they "
         "relate to, so category totals stay accurate.")
    show = st.segmented_control("Show", ["Uncategorised", "All expenses and refunds"], default="Uncategorised",
                                key="cats_filter")
    view = spend[spend["spending_category"] == "Uncategorised"] if show != "All expenses and refunds" else spend
    if show != "All expenses and refunds" and view.empty:
        st.success("Every expense has a category.")
    c.transaction_editor(d, view, "cats")
    _nav_buttons("Categories")


def step_periods(d) -> None:
    section("Choose a preset or set your own dates")
    c.preset_selector(d, "analyse")
    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    c.custom_period_inputs(d)
    st.caption(f"Your file covers {d.min_date:%d %b %Y} to {d.max_date:%d %b %Y}. Period A is the reference; "
               "Period B is compared against it.")
    if d.period_errors:
        for e in d.period_errors:
            note(e, warn=True)
    else:
        c.periods_line(d)
        if d.comparison.warnings:
            c.comparison_warnings(d)
    _nav_buttons("Periods", can_next=not d.period_errors)


def step_results(d) -> None:
    if not d.ready:
        note("Fix the periods first.", warn=True)
        _nav_buttons("Results")
        return
    c.periods_line(d)
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    c.comparison_warnings(d)
    c.kpi_row(d)
    c.quality_strip(d, "results")
    section("Category contribution")
    c.category_table(d)
    left, right = st.columns([1.55, 1], gap="large")
    with left:
        section("Weekly trend")
        c.trend_chart(d, weekly_net_spending(d.tx))
    with right:
        section("By category")
        c.category_chart(d)
    section("Insights and supporting evidence")
    if d.insights:
        c.insight_grid(d, d.insights, per_row=2, key="res")
    else:
        st.caption("No insights: both periods need transactions to compare.")
    section("Other money movements")
    for label, types in (("Income and refunds", ["Income", "Refund"]), ("Internal transfers", ["Internal Transfer"])):
        in_periods = d.tx[d.tx["transaction_type"].isin(types)]
        dd = in_periods["date"].dt.date
        in_periods = in_periods[((dd >= d.period_a[0]) & (dd <= d.period_a[1])) | ((dd >= d.period_b[0]) & (dd <= d.period_b[1]))]
        with st.expander(f"{label} in these periods ({len(in_periods)})"):
            if in_periods.empty:
                st.caption("None.")
            else:
                c.evidence_table(d, in_periods["txn_id"].tolist())
    _nav_buttons("Results")


def render(d) -> None:
    page_header("Analyse Spending", "Analyse your spending",
                "Seven steps from raw export to a verified comparison. Every step can be revisited; "
                "your corrections are kept for this session.")
    has_data = isinstance(d, state.Data)
    step = _stepper(has_data)
    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    if step == "Upload" or not has_data:
        step_upload(d)
        return
    {"Map columns": step_map, "Accounts": step_accounts, "Types": step_types, "Categories": step_categories,
     "Periods": step_periods, "Results": step_results}[step](d)
