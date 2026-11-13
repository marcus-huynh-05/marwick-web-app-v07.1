"""Marwick v0.7 - Streamlit entry point.

This file only routes between pages. All financial logic lives in the
`marwick` package; all presentation lives in the `ui` package.
Run with:  python -m streamlit run app.py
"""
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ui.theme import LOGO_SYMBOL, enable_chart_theme, esc, footer, inject_css, logo_img

st.set_page_config(page_title="Marwick", page_icon=str(LOGO_SYMBOL), layout="wide",
                   initial_sidebar_state="auto")

from marwick import __version__  # noqa: E402
from ui import state  # noqa: E402
from ui.pages import analyse, insights, overview, settings, transactions  # noqa: E402

ICONS = {"Overview": ":material/space_dashboard:", "Analyse Spending": ":material/query_stats:",
         "Transactions": ":material/receipt_long:", "Insights": ":material/insights:",
         "Settings": ":material/settings:"}
RENDER = {"Overview": overview.render, "Analyse Spending": analyse.render, "Transactions": transactions.render,
          "Insights": insights.render, "Settings": settings.render}

state.init_state()
inject_css()
enable_chart_theme()

data = state.get_data()

with st.sidebar:
    st.markdown(f'<div class="mw-brand">{logo_img(LOGO_SYMBOL, 64, "Marwick")}</div>'
                f'<div class="mw-brand-ver">MARWICK · v{__version__} prototype</div>', unsafe_allow_html=True)
    st.radio("Navigation", state.PAGES, key="nav", label_visibility="collapsed",
             format_func=lambda p: f"{ICONS[p]} {p}")
    if isinstance(data, state.Data):
        tx = data.tx
        n_review = int(tx["needs_review"].sum())
        st.markdown('<div class="mw-side-label">Current file</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:0.86rem;color:#FFFFFF;word-break:break-all">{esc(data.file_name)}</div>'
                    f'<div style="font-size:0.8rem;color:#A1A7B3;margin-top:2px">{len(tx):,} transactions'
                    f'{f" · {n_review} need review" if n_review else ""}</div>', unsafe_allow_html=True)
    st.markdown('<div class="mw-side-label">Privacy</div>'
                '<div style="font-size:0.78rem;color:#6B7280;line-height:1.5">Files stay in this session\'s '
                'memory and are never saved.</div>', unsafe_allow_html=True)

toast = st.session_state.pop("_toast", None)
if toast:
    st.toast(toast)

RENDER[st.session_state["nav"]](data)
footer()
