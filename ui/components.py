"""Reusable UI pieces shared by several pages."""
from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from marwick.classify import ALL_CATEGORY_OPTIONS, TRANSACTION_TYPES
from marwick.insights import Insight
from marwick.utils import cents_to_float, format_money, format_pct, period_days, MINUS
from . import state
from .theme import (GREY_A, WHITE_B, chips, esc, kpi_card, kpi_grid, note, section)

UP, DOWN = "\u25B2", "\u25BC"
EDIT_COLS = {"Type": "transaction_type", "Category": "spending_category",
             "Reviewed": "reviewed", "Exclude": "excluded"}


# ---------------------------------------------------------------- upload
def uploader(scope: str) -> None:
    f = st.file_uploader("Upload a transaction CSV", type=["csv"], key=f"upl_{scope}_{st.session_state['editor_ver']}",
                         help="Exported from your bank. Processed in memory for this session only.")
    if f is not None and (f.name != st.session_state.get("file_name") or f.getvalue() != st.session_state.get("file_bytes")):
        state.load_file(f.name, f.getvalue())
        st.rerun()


# ---------------------------------------------------------------- periods
def fmt_range(p: tuple[date, date]) -> str:
    s, e = p
    left = f"{s.day} {s:%b}" if s.year == e.year else f"{s.day} {s:%b %Y}"
    return f"{left} – {e.day} {e:%b %Y}"


def periods_line(d: state.Data) -> None:
    a, b = d.period_a, d.period_b
    st.markdown(
        f'<div class="mw-periods">Period A <b>{esc(fmt_range(a))}</b> ({period_days(*a)} days)'
        f' &nbsp;→&nbsp; Period B <b>{esc(fmt_range(b))}</b> ({period_days(*b)} days)</div>',
        unsafe_allow_html=True)


def preset_selector(d: state.Data, scope: str, label_visibility: str = "visible") -> None:
    key = f"_w_{scope}_preset"
    if key not in st.session_state:
        st.session_state[key] = state.cfg()["preset"]

    def _on_change():
        p = st.session_state[key]
        if p == "custom":
            state.cfg()["preset"] = "custom"
        else:
            state.apply_preset(p, d.min_date, d.max_date)
        for k in [k for k in st.session_state if k.startswith("_w_") and "_date_" in k]:
            del st.session_state[k]

    st.selectbox("Comparison", list(state.PRESETS), format_func=state.PRESETS.get, key=key,
                 on_change=_on_change, label_visibility=label_visibility)


def custom_period_inputs(d: state.Data) -> None:
    c = state.cfg()
    cols = st.columns(2)
    for col, name, label in ((cols[0], "period_a", "Period A · reference"), (cols[1], "period_b", "Period B · comparison")):
        with col:
            st.markdown(f"**{label}**")
            key = f"_w_date_{name}"
            if key not in st.session_state:
                st.session_state[key] = tuple(c[name])

            def _sync(n=name, k=key):
                v = st.session_state[k]
                if isinstance(v, (tuple, list)) and len(v) == 2:
                    c[n] = (v[0], v[1])
                    c["preset"] = "custom"
                    st.session_state.pop("_w_analyse_preset", None)
                    st.session_state.pop("_w_overview_preset", None)
            st.date_input("Date range", key=key, min_value=d.min_date, max_value=d.max_date, on_change=_sync,
                          format="DD/MM/YYYY", label_visibility="collapsed")


# ---------------------------------------------------------------- KPIs
def _delta(a: int, b: int, cur: str, higher_is: str) -> tuple[str, str]:
    """higher_is: 'bad' (spending), 'good' (income) or 'neutral'."""
    diff = b - a
    if diff == 0:
        return "No change vs Period A", ""
    arrow = UP if diff > 0 else DOWN
    tone = "" if higher_is == "neutral" else (("bad" if diff > 0 else "good") if higher_is == "bad" else
                                               ("good" if diff > 0 else "bad"))
    return f"{arrow} {format_money(abs(diff), cur)} vs Period A", tone


def kpi_row(d: state.Data) -> None:
    c, cur = d.comparison, d.currency
    a, b = c.a, c.b
    arrow = UP if c.net_change > 0 else DOWN
    net_delta = (f"{arrow} {format_money(abs(c.net_change), cur)}"
                 + (f" · {format_pct(c.pct)}" if c.pct is not None else "") + " vs Period A") if c.net_change else "No change vs Period A"
    net_tone = "" if c.net_change == 0 else ("bad" if c.net_change > 0 else "good")
    cards = [
        kpi_card("Net spending", format_money(b.net_spending, cur), net_delta, net_tone,
                 f"Period A {format_money(a.net_spending, cur)}", primary=True),
        kpi_card("Gross spending", format_money(b.gross_spending, cur), *_delta(a.gross_spending, b.gross_spending, cur, "bad"),
                 foot=f"{b.expense_count} expenses"),
        kpi_card("Refunds", format_money(b.refunds, cur), *_delta(a.refunds, b.refunds, cur, "neutral"),
                 foot=f"{b.refund_count} refunds"),
        kpi_card("Income", format_money(b.income, cur), *_delta(a.income, b.income, cur, "good"),
                 foot="External income only"),
        kpi_card("Transfers out", format_money(b.transfer_out, cur),
                 f"{format_money(b.transfer_in, cur)} transferred in", "",
                 foot="Own accounts · not spending or income"),
    ]
    kpi_grid(cards)
    if c.pct is None and c.pct_note and not a.is_empty:
        note(c.pct_note + ".")


def quality_strip(d: state.Data, scope: str) -> None:
    tx = d.tx
    n_review = int(tx["needs_review"].sum())
    n_dup = int(tx["possible_duplicate"].sum())
    n_invalid = len(d.prepared.invalid)
    n_excl = int(tx["excluded"].sum())
    items = [(f"{len(tx):,} transactions", "on")]
    if n_review: items.append((f"{n_review} need review", "warn"))
    if n_dup: items.append((f"{n_dup} possible duplicates", "warn"))
    if n_invalid: items.append((f"{n_invalid} unreadable rows", "warn"))
    if n_excl: items.append((f"{n_excl} excluded by you", ""))
    if not n_review: items.append(("All transactions reviewed or confident", ""))
    cols = st.columns([5, 1.3], vertical_alignment="center")
    with cols[0]:
        chips(items)
    with cols[1]:
        if n_review:
            st.button("Review now", key=f"review_{scope}", on_click=state.go, args=("Transactions",),
                      width="stretch")


# ---------------------------------------------------------------- charts
def _week_period(monday, a, b) -> str:
    """Which period a Monday-to-Sunday week overlaps."""
    sunday = monday + timedelta(days=6)
    in_a = monday <= a[1] and sunday >= a[0]
    in_b = monday <= b[1] and sunday >= b[0]
    if in_a and in_b:
        return "Spans both"
    return "Period A" if in_a else "Period B" if in_b else "Outside periods"


def trend_chart(d: state.Data, weekly: pd.DataFrame) -> None:
    if weekly.empty:
        st.caption("No spending to chart.")
        return
    a, b = d.period_a, d.period_b
    w = weekly.copy()
    w["Net"] = w["net"].map(cents_to_float)
    wd = w["week_start"].dt.date
    w["Period"] = [_week_period(x, a, b) for x in wd]
    w["Week"] = [f"{x.day} {x:%b}" for x in wd]
    ch = alt.Chart(w).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("Week:O", sort=None, title="Week starting", axis=alt.Axis(labelAngle=0, labelOverlap=True)),
        y=alt.Y("Net:Q", title=f"Net spending ({d.currency})", axis=alt.Axis(format=",.0f", tickCount=5)),
        color=alt.Color("Period:N", scale=alt.Scale(domain=["Period A", "Period B", "Spans both", "Outside periods"],
                                                    range=[GREY_A, WHITE_B, "#9AA1AD", "#2A303B"]),
                        legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("Week:N", title="Week starting"),
                 alt.Tooltip("Net:Q", format=",.2f", title=f"Net ({d.currency})"), alt.Tooltip("Period:N")],
    ).properties(height=260)
    st.altair_chart(ch, width="stretch")
    st.caption("Net spending per week (gross minus refunds), weeks starting Monday. Weeks at the start and end "
               "of the file may be partial. Large spikes are usually rent or one-off purchases.")


def category_chart(d: state.Data, limit: int = 8) -> None:
    """Period B as bars, Period A as a tick on the same row: change reads at a glance."""
    cats = d.comparison.categories.copy()
    if cats.empty:
        st.caption("No expense categories in these periods.")
        return
    cats = cats.assign(_size=cats[["net_a", "net_b"]].max(axis=1)).sort_values("_size", ascending=False).head(limit)
    cats = cats.reset_index()
    frame = pd.DataFrame({"Category": cats["category"], "Period B": cats["net_b"].map(cents_to_float),
                          "Period A": cats["net_a"].map(cents_to_float),
                          "Change": cats["net_change"].map(cents_to_float)})
    order = frame["Category"].tolist()
    tip = ["Category:N", alt.Tooltip("Period A:Q", format=",.2f"), alt.Tooltip("Period B:Q", format=",.2f"),
           alt.Tooltip("Change:Q", format="+,.2f")]
    base = alt.Chart(frame).encode(y=alt.Y("Category:N", sort=order, title=None,
                                             axis=alt.Axis(labelLimit=130, labelPadding=8)))
    bars = base.mark_bar(color=WHITE_B, height=12, cornerRadiusEnd=2).encode(
        x=alt.X("Period B:Q", title=f"Net spending ({d.currency})", axis=alt.Axis(format=",.0f", tickCount=4)),
        tooltip=tip)
    ticks = base.mark_tick(color="#8A92A0", thickness=2, size=22).encode(x="Period A:Q", tooltip=tip)
    st.altair_chart((bars + ticks).properties(height=alt.Step(30)), width="stretch")
    st.markdown('<div class="mw-periods" style="font-size:0.8rem">'
                f'<span style="display:inline-block;width:10px;height:10px;background:{WHITE_B};margin-right:6px"></span>Period B'
                '&nbsp;&nbsp;&nbsp;<span style="display:inline-block;width:2px;height:12px;background:#8A92A0;'
                'margin-right:6px;vertical-align:-1px"></span>Period A</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- tables
def category_table(d: state.Data) -> None:
    c = d.comparison
    t = c.categories.reset_index()
    show = pd.DataFrame({
        "Category": t["category"],
        "Period A net": t["net_a"].map(cents_to_float),
        "Period B net": t["net_b"].map(cents_to_float),
        "Change": t["net_change"].map(cents_to_float),
        "Txns A": t["count_a"], "Txns B": t["count_b"],
        "Avg A": pd.to_numeric(t["avg_a"].map(cents_to_float)), "Avg B": pd.to_numeric(t["avg_b"].map(cents_to_float)),
        "Refunds A": t["refunds_a"].map(cents_to_float), "Refunds B": t["refunds_b"].map(cents_to_float),
    })
    money = st.column_config.NumberColumn(format="%.2f")
    cfg = {k: money for k in ["Period A net", "Period B net", "Change", "Avg A", "Avg B", "Refunds A", "Refunds B"]}
    cfg["Avg A"] = st.column_config.NumberColumn(format="%.2f", help="Average expense value; blank when there were none")
    st.dataframe(show, hide_index=True, width="stretch", column_config=cfg)
    if c.reconciles:
        st.caption(f":material/check_circle: Category totals add up exactly to net spending "
                   f"({format_money(c.a.net_spending, d.currency)} and {format_money(c.b.net_spending, d.currency)}). "
                   f"Amounts in {d.currency}; averages are per expense transaction.")
    else:
        st.error("Category totals do not reconcile with net spending. Please report this as a bug.")


def evidence_table(d: state.Data, ids: list[str]) -> None:
    tx = d.tx.set_index("txn_id").loc[ids].reset_index()
    a, b = d.period_a, d.period_b
    dd = tx["date"].dt.date
    out = pd.DataFrame({
        "Period": ["A" if a[0] <= x <= a[1] else "B" for x in dd],
        "Date": dd,
        "Description": tx["description"],
        "Amount": tx["amount_cents"].map(cents_to_float),
        "Type": tx["transaction_type"],
        "Category": tx["spending_category"],
    }).sort_values(["Period", "Date"])
    st.dataframe(out, hide_index=True, width="stretch", column_config={
        "Amount": st.column_config.NumberColumn(f"Amount ({d.currency})", format="%.2f"),
        "Date": st.column_config.DateColumn(format="DD/MM/YYYY")})


# ---------------------------------------------------------------- insights
KIND_LABEL = {"net_change": "Headline", "category_increase": "Increase", "category_decrease": "Decrease",
              "new_category": "New this period", "stopped_category": "Stopped this period"}


def insight_card(d: state.Data, ins: Insight, key: str, show_evidence: bool = True) -> None:
    cur = d.currency
    value = format_money(ins.change, cur, signed=True) if ins.change is not None else ""
    with st.container(border=True):
        st.markdown(
            f'<div class="mw-insight-kind">{esc(KIND_LABEL.get(ins.kind, ins.kind))}</div>'
            f'<div class="mw-insight-title">{esc(ins.title)}</div>'
            f'<div class="mw-insight-value">{esc(value)}</div>'
            f'<div class="mw-insight-text">{esc(ins.statement)}</div>', unsafe_allow_html=True)
        if show_evidence and ins.evidence_ids:
            with st.expander(f"Supporting transactions ({len(ins.evidence_ids)})"):
                evidence_table(d, ins.evidence_ids)


def insight_grid(d: state.Data, insights: list[Insight], per_row: int = 3, key: str = "g",
                 show_evidence: bool = True) -> None:
    for i in range(0, len(insights), per_row):
        cols = st.columns(per_row)
        for j, ins in enumerate(insights[i:i + per_row]):
            with cols[j]:
                insight_card(d, ins, f"{key}_{i + j}", show_evidence)


def comparison_warnings(d: state.Data) -> None:
    for w in d.comparison.warnings:
        note(w, warn=True)


# ---------------------------------------------------------------- transaction editor
def _apply_edits(key: str, ids: list[str]) -> None:
    edits = st.session_state.get(key, {}).get("edited_rows", {})
    ov = st.session_state["overrides"]
    for pos, changes in edits.items():
        tid = ids[int(pos)]
        entry = ov.setdefault(tid, {})
        for col, val in changes.items():
            field = EDIT_COLS.get(col)
            if field:
                entry[field] = val
    st.session_state["editor_ver"] += 1  # fresh editor next run, built from the saved corrections


def transaction_editor(d: state.Data, view: pd.DataFrame, name: str, height: int | None = None) -> None:
    """Editable table. Corrections are saved by stable transaction ID, so they
    survive filtering, navigation and settings changes."""
    if view.empty:
        st.caption("No transactions match.")
        return
    ids = view["txn_id"].tolist()
    frame = pd.DataFrame({
        "Date": view["date"].dt.date,
        "Description": view["description"].where(view["description"] != "", "(no description)"),
        "Amount": view["amount_cents"].map(cents_to_float),
        "Status": view["review_status"],
        "Type": view["transaction_type"],
        "Category": view["spending_category"],
        "Why": [" · ".join(r) if r else ("Corrected or confirmed by you." if e or rv else s)
                for r, s, e, rv in zip(view["review_reasons"], view["suggestion_reason"], view["user_edited"],
                                       view["reviewed"])],
        "Reviewed": view["reviewed"].astype(bool),
        "Exclude": view["excluded"].astype(bool),
    })
    key = f"editor_{name}_{st.session_state['editor_ver']}"
    st.data_editor(
        frame, key=key, hide_index=True, width="stretch", num_rows="fixed",
        height=min(35 * (len(frame) + 1) + 3, height or 560),
        disabled=["Date", "Description", "Amount", "Status", "Why"],
        on_change=_apply_edits, args=(key, ids),
        column_config={
            "Date": st.column_config.DateColumn(format="DD/MM/YYYY", width="small"),
            "Description": st.column_config.TextColumn(width="medium"),
            "Amount": st.column_config.NumberColumn("Amount", format="%.2f", width="small",
                                                    help=f"In {d.currency}. Negative = money out."),
            "Type": st.column_config.SelectboxColumn("Transaction type", options=TRANSACTION_TYPES, required=True),
            "Category": st.column_config.SelectboxColumn("Spending category", options=ALL_CATEGORY_OPTIONS, required=True),
            "Status": st.column_config.TextColumn("Status", width="medium"),
            "Why": st.column_config.TextColumn("Why / what to check", width="large"),
            "Reviewed": st.column_config.CheckboxColumn("Reviewed", help="Confirms an uncertain suggestion or a possible duplicate."),
            "Exclude": st.column_config.CheckboxColumn("Exclude", help="Removes the row from all totals; it stays listed as excluded."),
        },
    )


def signed_amount_text(cents: int, cur: str) -> str:
    return format_money(cents, cur).replace(MINUS, "-")
