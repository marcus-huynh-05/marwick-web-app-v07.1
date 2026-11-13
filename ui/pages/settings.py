import streamlit as st

from marwick import __version__
from .. import state
from ..theme import chips, note, page_header, section


def render(d) -> None:
    page_header("Settings", "Settings", "Preferences for this session. Nothing is saved after you close the tab.")
    section("Currency")
    key = state.bind("currency", "settings")
    st.selectbox("Currency of the current file", state.CURRENCIES, key=key, on_change=state.sync,
                 args=("currency", key), help="Labels only. Marwick does not convert currencies.")
    section("My Accounts")
    key = state.bind("suffixes_text", "settings")
    st.text_input("Last digits of your own accounts", key=key, on_change=state.sync, args=("suffixes_text", key),
                  placeholder="e.g. 1421, 2939",
                  help="Transfers that mention these masked accounts (xx1421) are treated as Internal Transfers.")
    if isinstance(d, state.Data) and d.suffixes:
        chips([(f"xx{s}", "on") for s in d.suffixes])

    section("Session data")
    ss = st.session_state
    if ss.get("file_name"):
        n_corr = len(ss.get("overrides", {}))
        chips([(f"File: {ss['file_name']}", "on"), (f"{n_corr} manual correction(s)", "")])
    else:
        st.caption("No file loaded.")
    note("Uploaded data is held only in this session's memory. Clearing removes the file, your corrections and "
         "all settings from the session.")
    if st.button("Clear session data", disabled=not ss.get("file_name")):
        state.clear_session()
        st.rerun()

    section("About this version")
    st.markdown(
        f"**Marwick v{__version__}** · prototype\n\n"
        "- Calculations are deterministic and use integer cents.\n"
        "- Classification uses rules plus your corrections. No AI model is used.\n"
        "- No bank connection, user accounts or stored history.\n"
        "- Secure deletion and session isolation have not been independently verified. "
        "Avoid uploading highly sensitive data.\n"
        "- Not financial advice.")
