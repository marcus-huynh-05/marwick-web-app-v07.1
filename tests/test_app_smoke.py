"""Headless smoke tests: every page and every Analyse step renders without an exception.

Uses Streamlit's built-in AppTest, so no browser or server is needed.
"""
from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = str(Path(__file__).resolve().parents[1] / "app.py")
PAGES = ["Overview", "Analyse Spending", "Transactions", "Insights", "Settings"]


@pytest.fixture
def app():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    return at


def test_every_page_renders_without_data(app):
    for page in PAGES:
        app.radio(key="nav").set_value(page).run()
        assert not app.exception, page


def test_sample_data_every_page_and_step(app):
    next(b for b in app.button if b.label == "Try with sample data").click().run()
    assert not app.exception and not app.error
    assert app.session_state["file_name"] == "sample_transactions.csv"
    for page in PAGES:
        app.radio(key="nav").set_value(page).run()
        assert not app.exception, page
    app.radio(key="nav").set_value("Analyse Spending").run()
    prev = "Upload"
    for step in ["Map columns", "Accounts", "Types", "Categories", "Periods", "Results"]:
        app.button(key=f"next_{prev}").click().run()
        assert not app.exception, step
        prev = step


def test_clear_session_removes_file(app):
    next(b for b in app.button if b.label == "Try with sample data").click().run()
    app.radio(key="nav").set_value("Settings").run()
    next(b for b in app.button if b.label == "Clear session data").click().run()
    assert not app.exception
    assert app.session_state["file_bytes"] is None
