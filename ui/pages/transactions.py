import streamlit as st

from marwick.classify import TRANSACTION_TYPES
from .. import components as c
from .. import state
from ..theme import chips, page_header

STATUSES = ["All", "Needs review", "Reviewed", "OK", "Excluded"]


def render(d) -> None:
    page_header("Transactions", "Transactions",
                "Every transaction in your file. Correct a type or category directly in the table; "
                "changes update all totals immediately and are kept for this session.")
    if not isinstance(d, state.Data):
        st.info("Upload a file on the Overview page to see transactions.")
        st.button("Go to Overview", on_click=state.go, args=("Overview",))
        return
    tx = d.tx
    counts = tx["review_status"].value_counts()
    chips([(f"{len(tx):,} total", "on")] + [(f"{s}: {int(counts.get(s, 0))}", "warn" if s == "Needs review" else "")
                                          for s in STATUSES[1:] if counts.get(s, 0)])
    a, b, s = st.columns([2, 2, 3], vertical_alignment="bottom")
    with a:
        q = st.text_input("Search description", placeholder="e.g. woolworths", key="tx_search")
    with b:
        types = st.multiselect("Transaction type", TRANSACTION_TYPES, key="tx_types", placeholder="All types")
    with s:
        status = st.segmented_control("Review status", STATUSES, default="All", key="tx_status")
    view = tx
    if q:
        view = view[view["description"].str.contains(q, case=False, regex=False)]
    if types:
        view = view[view["transaction_type"].isin(types)]
    if status and status != "All":
        view = view[view["review_status"] == status]
    st.caption(f"Showing {len(view):,} of {len(tx):,}. Newest first.")
    view = view.sort_values(["date", "csv_row"], ascending=[False, True])
    c.transaction_editor(d, view, "all", height=620)
    inv = d.prepared.invalid
    if len(inv):
        with st.expander(f"Unreadable rows ({len(inv)}) · not in any total"):
            st.dataframe(inv, hide_index=True, width="stretch")
