import streamlit as st

from marwick.engine import weekly_net_spending
from .. import components as c
from .. import state
from ..theme import LOGO_WORDMARK, esc, logo_img, note, page_header, section


def welcome() -> None:
    st.markdown(
        f'<div class="mw-hero">{logo_img(LOGO_WORDMARK, 200, "Marwick")}'
        '<h1>Understand why your spending changes.</h1>'
        '<p>Upload a bank export and Marwick compares two periods, shows which categories drove the change, '
        'and links every figure to the transactions behind it.</p></div>', unsafe_allow_html=True)
    left, right = st.columns([3, 2], gap="large")
    with left:
        c.uploader("overview")
    with right:
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        st.button("Try with sample data", type="primary", on_click=state.load_sample, width="stretch")
        st.caption("A fictional three-month export, useful for exploring the app.")
    section("How it works")
    st.markdown(
        '<div class="mw-steps-how">'
        '<div class="mw-card"><div class="mw-how-n">01</div><div class="mw-how-t">Upload</div>'
        '<div class="mw-how-d">A CSV export with date, description and amount. Columns are detected automatically and you can adjust them.</div></div>'
        '<div class="mw-card"><div class="mw-how-n">02</div><div class="mw-how-t">Review</div>'
        '<div class="mw-how-d">Marwick suggests a type and category for each transaction and flags anything uncertain for you to confirm.</div></div>'
        '<div class="mw-card"><div class="mw-how-n">03</div><div class="mw-how-t">Compare</div>'
        '<div class="mw-how-d">See what changed between two periods, which categories drove it, and the evidence for each figure.</div></div>'
        '</div>', unsafe_allow_html=True)
    note("Your file is processed in this browser session's memory and is not saved. Closing the tab or "
         "choosing Clear session in Settings removes it.")


def render(d) -> None:
    if d is None:
        welcome()
        return
    if isinstance(d, str):
        page_header("Overview", "Spending overview")
        st.error(d)
        st.button("Check file settings", on_click=state.go, args=("Analyse Spending", "Upload"))
        return
    head, ctrl = st.columns([3, 1.4], vertical_alignment="bottom")
    with head:
        page_header("Overview", "Spending overview", f"{d.file_name} · amounts in {d.currency}")
    if d.error:
        st.error(d.error)
        st.button("Check column mapping", on_click=state.go, args=("Analyse Spending", "Map columns"))
        return
    with ctrl:
        c.preset_selector(d, "overview")
    c.periods_line(d)
    if d.period_errors:
        for e in d.period_errors:
            note(e, warn=True)
        st.button("Adjust periods", on_click=state.go, args=("Analyse Spending", "Periods"))
        return
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    c.comparison_warnings(d)
    c.kpi_row(d)
    c.quality_strip(d, "overview")

    left, right = st.columns([1.55, 1], gap="large")
    with left:
        section("Spending trend")
        c.trend_chart(d, weekly_net_spending(d.tx))
    with right:
        section("By category")
        c.category_chart(d, limit=7)

    section("Key insights")
    top = d.insights[:3]
    if not top:
        st.caption("No insights for these periods. Both periods need transactions to compare.")
    else:
        c.insight_grid(d, top, per_row=3, key="ov", show_evidence=False)
        st.button("See all insights and evidence", on_click=state.go, args=("Insights",))
