"""Visual system: colours, CSS, logo helpers and small HTML components.

All user-supplied text placed into HTML goes through `esc()` first, because a
CSV description could otherwise inject markup into the page.
"""
from __future__ import annotations

import base64
import html
from functools import lru_cache
from pathlib import Path

import altair as alt
import streamlit as st

ASSETS = Path(__file__).resolve().parents[1] / "assets"
LOGO_WORDMARK = ASSETS / "marwick_logo.png"      # diamond + MARWICK, 267x86
LOGO_SYMBOL = ASSETS / "marwick_symbol.png"      # double diamond, 1080x1080

BG = "#0E1117"
BG_2 = "#151922"
CARD = "#1B2029"
BORDER = "#262C38"
TEXT = "#FFFFFF"
MUTED = "#A1A7B3"
FAINT = "#6B7280"
POS = "#6FCF97"   # subtle green: favourable change
NEG = "#E5847F"   # subtle red: unfavourable change
GREY_A = "#5B6270"  # Period A in charts
WHITE_B = "#E6E8EC"  # Period B in charts

FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif'


def esc(text) -> str:
    return html.escape(str(text), quote=True)


@lru_cache(maxsize=4)
def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def logo_img(path: Path, width_px: int, alt_text: str = "Marwick") -> str:
    """Logo as an <img>; width only, so the original proportions are kept."""
    return (f'<img src="data:image/png;base64,{_b64(path)}" alt="{esc(alt_text)}" '
            f'style="width:{width_px}px;height:auto;display:block;" />')


CSS = f"""
<style>
:root {{ --mw-bg:{BG}; --mw-bg2:{BG_2}; --mw-card:{CARD}; --mw-border:{BORDER};
        --mw-text:{TEXT}; --mw-muted:{MUTED}; --mw-faint:{FAINT}; --mw-pos:{POS}; --mw-neg:{NEG}; }}
html, body, .stApp, .stMarkdown, button, input, textarea, select {{ font-family:{FONT}; }}
.stApp {{ background:var(--mw-bg); }}
.block-container {{ padding-top:2.2rem; padding-bottom:4rem; max-width:1240px; }}
.stAppDeployButton, [data-testid="stStatusWidget"] {{ display:none; }}
header[data-testid="stHeader"] {{ background:transparent; }}
h1, h2, h3, h4 {{ letter-spacing:-0.01em; font-weight:600; }}
hr {{ border-color:var(--mw-border) !important; }}

/* Sidebar */
section[data-testid="stSidebar"] {{ border-right:1px solid var(--mw-border); }}
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] > div {{ padding-top:0.6rem; }}
.mw-brand {{ display:flex; align-items:center; gap:10px; margin:0 0 6px -6px; }}
.mw-brand-name {{ font-weight:600; letter-spacing:0.22em; font-size:0.95rem; color:var(--mw-text); }}
.mw-brand-ver {{ font-size:0.72rem; color:var(--mw-faint); letter-spacing:0.04em; margin:0 0 18px 2px; }}
.mw-side-label {{ font-size:0.68rem; text-transform:uppercase; letter-spacing:0.14em; color:var(--mw-faint);
                 margin:18px 0 6px 2px; }}

/* Sidebar navigation (a radio group restyled as a menu). Selectors cover current Streamlit markup. */
section[data-testid="stSidebar"] div[data-testid="stRadio"], section[data-testid="stSidebar"] div[data-testid="stRadio"] > div {{ width:100%; }}
section[data-testid="stSidebar"] div[role="radiogroup"] {{ gap:2px; width:100%; display:flex; flex-direction:column; }}
section[data-testid="stSidebar"] div[role="radiogroup"] > div {{ width:100%; margin:0 !important; padding:0 !important; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
  width:100%; max-width:100%; display:flex; margin:0 !important; padding:7px 12px; border-radius:6px;
  border:1px solid transparent; cursor:pointer; box-sizing:border-box;
  transition:background .12s ease; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) {{ display:none; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {{ background:var(--mw-bg2); }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:has(input:checked) {{
  background:var(--mw-card); border-color:var(--mw-border); }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div {{ width:100%; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {{ color:var(--mw-muted); font-size:0.92rem; margin:0; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:has(input:checked) p {{ color:var(--mw-text); font-weight:600; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p span[role="img"] {{ margin-right:6px; font-size:1.1rem; }}

/* Buttons */
.stButton > button, .stDownloadButton > button {{ border-radius:6px; font-weight:500; }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background:#FFFFFF; color:#0E1117; border:1px solid #FFFFFF; }}
.stButton > button[kind="primary"]:hover {{ background:#E6E8EC; border-color:#E6E8EC; color:#0E1117; }}
.stButton > button[kind="primary"] p {{ color:#0E1117; }}
.stButton > button[kind="secondary"] {{ background:transparent; border:1px solid var(--mw-border); color:var(--mw-text); }}
.stButton > button[kind="secondary"]:hover {{ border-color:#3A4150; background:var(--mw-bg2); }}

/* Containers, expanders, inputs */
div[data-testid="stVerticalBlockBorderWrapper"] {{ border-color:var(--mw-border) !important; }}
div[data-testid="stExpander"] details {{ border:1px solid var(--mw-border); border-radius:6px; background:var(--mw-bg); }}
div[data-testid="stExpander"] summary p {{ color:var(--mw-muted); font-size:0.88rem; }}
div[data-testid="stFileUploaderDropzone"] {{ background:var(--mw-bg2); border:1px dashed #333A47; border-radius:6px; }}
div[data-testid="stAlert"] {{ border-radius:6px; }}

/* Page header */
.mw-eyebrow {{ font-size:0.72rem; letter-spacing:0.16em; text-transform:uppercase; color:var(--mw-faint); margin-bottom:6px; }}
.mw-title {{ font-size:1.9rem; font-weight:600; letter-spacing:-0.02em; line-height:1.15; margin:0; color:var(--mw-text); }}
.mw-sub {{ color:var(--mw-muted); font-size:0.98rem; margin:8px 0 0 0; max-width:720px; line-height:1.5; }}
.mw-header {{ margin-bottom:22px; }}
.mw-section {{ font-size:0.78rem; letter-spacing:0.14em; text-transform:uppercase; color:var(--mw-muted);
              margin:28px 0 12px 0; font-weight:600; }}

/* KPI grid */
.mw-kpis {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(165px, 1fr)); gap:12px; margin:4px 0 8px 0; }}
.mw-kpi {{ background:var(--mw-card); border:1px solid var(--mw-border); border-radius:8px; padding:16px 18px 14px; }}
.mw-kpi.primary {{ border-color:#3A4150; }}
.mw-kpi-label {{ font-size:0.74rem; text-transform:uppercase; letter-spacing:0.12em; color:var(--mw-muted); }}
.mw-kpi-value {{ font-size:1.55rem; font-weight:600; margin-top:8px; font-variant-numeric:tabular-nums; letter-spacing:-0.01em; }}
.mw-kpi-delta {{ font-size:0.82rem; margin-top:6px; font-variant-numeric:tabular-nums; color:var(--mw-muted); }}
.mw-kpi-delta.good {{ color:var(--mw-pos); }} .mw-kpi-delta.bad {{ color:var(--mw-neg); }}
.mw-kpi-foot {{ font-size:0.78rem; color:var(--mw-faint); margin-top:4px; font-variant-numeric:tabular-nums; }}

/* Cards and chips */
.mw-card {{ background:var(--mw-card); border:1px solid var(--mw-border); border-radius:8px; padding:18px 20px; }}
.mw-card-title {{ font-size:0.95rem; font-weight:600; margin:0 0 2px 0; }}
.mw-card-sub {{ font-size:0.82rem; color:var(--mw-muted); margin:0 0 6px 0; }}
.mw-insight-kind {{ font-size:0.68rem; letter-spacing:0.14em; text-transform:uppercase; color:var(--mw-faint); }}
.mw-insight-title {{ font-size:1.05rem; font-weight:600; margin:6px 0 4px 0; }}
.mw-insight-value {{ font-size:1.35rem; font-weight:600; font-variant-numeric:tabular-nums; margin:2px 0 8px 0; }}
.mw-insight-text {{ font-size:0.9rem; color:var(--mw-muted); line-height:1.5; }}
.mw-chip {{ display:inline-block; font-size:0.74rem; padding:3px 9px; border-radius:999px; border:1px solid var(--mw-border);
           color:var(--mw-muted); margin:0 6px 6px 0; background:var(--mw-bg2); }}
.mw-chip.on {{ color:var(--mw-text); border-color:#3A4150; }}
.mw-chip.warn {{ color:#E8C27A; border-color:#4A4130; }}
.mw-planned {{ background:transparent; border:1px dashed #2E3441; border-radius:8px; padding:16px 18px; height:100%; }}
.mw-planned .mw-insight-title {{ color:var(--mw-muted); }}
.mw-note {{ font-size:0.86rem; color:var(--mw-muted); border-left:2px solid #3A4150; padding:2px 0 2px 12px; margin:8px 0; line-height:1.5; }}
.mw-note.warn {{ border-left-color:#8A6D3B; }}
.mw-periods {{ font-size:0.88rem; color:var(--mw-muted); font-variant-numeric:tabular-nums; }}
.mw-periods b {{ color:var(--mw-text); font-weight:600; }}
.mw-foot {{ margin-top:48px; padding-top:16px; border-top:1px solid var(--mw-border); font-size:0.78rem; color:var(--mw-faint); line-height:1.6; }}
.mw-steps-how {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin-top:8px; }}
.mw-how-n {{ font-size:0.72rem; color:var(--mw-faint); letter-spacing:0.12em; }}
.mw-how-t {{ font-weight:600; margin:6px 0 4px 0; }}
.mw-how-d {{ font-size:0.86rem; color:var(--mw-muted); line-height:1.5; }}
.mw-hero {{ padding:8px 0 10px 0; }}
.mw-hero h1 {{ font-size:2.4rem; font-weight:600; letter-spacing:-0.025em; margin:26px 0 10px 0; line-height:1.1; }}
.mw-hero p {{ color:var(--mw-muted); font-size:1.05rem; max-width:620px; line-height:1.55; }}

@media (max-width: 640px) {{
  .mw-title {{ font-size:1.5rem; }} .mw-hero h1 {{ font-size:1.8rem; }} .mw-kpi-value {{ font-size:1.3rem; }}
  .block-container {{ padding-left:1rem; padding-right:1rem; }}
}}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(eyebrow: str, title: str, subtitle: str | None = None) -> None:
    sub = f'<p class="mw-sub">{esc(subtitle)}</p>' if subtitle else ""
    st.markdown(f'<div class="mw-header"><div class="mw-eyebrow">{esc(eyebrow)}</div>'
                f'<h1 class="mw-title">{esc(title)}</h1>{sub}</div>', unsafe_allow_html=True)


def section(title: str) -> None:
    st.markdown(f'<div class="mw-section">{esc(title)}</div>', unsafe_allow_html=True)


def note(text: str, warn: bool = False) -> None:
    st.markdown(f'<div class="mw-note{" warn" if warn else ""}">{esc(text)}</div>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(
        '<div class="mw-foot">Marwick v0.7 prototype · Rule-based classification and deterministic calculations; '
        'no AI or bank connection is integrated. Files are processed in memory for this session only and are '
        'not saved. Secure deletion and session isolation have not been independently verified. '
        'This is not financial advice.</div>', unsafe_allow_html=True)


def kpi_card(label: str, value: str, delta: str | None = None, tone: str = "", foot: str | None = None,
             primary: bool = False) -> str:
    d = f'<div class="mw-kpi-delta {tone}">{esc(delta)}</div>' if delta else ""
    f = f'<div class="mw-kpi-foot">{esc(foot)}</div>' if foot else ""
    return (f'<div class="mw-kpi{" primary" if primary else ""}"><div class="mw-kpi-label">{esc(label)}</div>'
            f'<div class="mw-kpi-value">{esc(value)}</div>{d}{f}</div>')


def kpi_grid(cards: list[str]) -> None:
    st.markdown(f'<div class="mw-kpis">{"".join(cards)}</div>', unsafe_allow_html=True)


def chips(items: list[tuple[str, str]]) -> None:
    """items: (text, style) with style '' | 'on' | 'warn'."""
    st.markdown("".join(f'<span class="mw-chip {s}">{esc(t)}</span>' for t, s in items), unsafe_allow_html=True)


# ---------------------------------------------------------------- charts
def _altair_theme():
    return {"config": {
        "background": "transparent",
        "view": {"stroke": None},
        "font": FONT,
        "axis": {"domain": False, "labelColor": MUTED, "titleColor": MUTED, "gridColor": "#1F2430",
                 "tickColor": "#1F2430", "labelFontSize": 11, "titleFontSize": 11, "titleFontWeight": 500},
        "legend": {"labelColor": MUTED, "titleColor": MUTED, "orient": "top", "labelFontSize": 11,
                   "titleFontSize": 11, "symbolType": "square"},
        "title": {"color": TEXT},
    }}


def enable_chart_theme() -> None:
    try:
        alt.theme.register("marwick", enable=True)(_altair_theme)
    except AttributeError:  # older Altair (<5.5)
        alt.themes.register("marwick", _altair_theme)
        alt.themes.enable("marwick")
