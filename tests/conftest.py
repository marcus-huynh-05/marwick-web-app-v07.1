import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from marwick.pipeline import prepare  # noqa: E402
from marwick.validators import ColumnMapping  # noqa: E402


def make_raw(rows):
    """rows: list of (date 'YYYY-MM-DD', amount text, description)."""
    return pd.DataFrame(rows, columns=["Date", "Amount", "Description"], dtype=str)


MAPPING = ColumnMapping(date_col="Date", desc_col="Description", amount_col="Amount")


@pytest.fixture
def build():
    def _build(rows, suffixes=None, overrides=None, mapping=MAPPING):
        return prepare(make_raw(rows), mapping, suffixes or [], overrides).transactions
    return _build


@pytest.fixture
def periods():
    return (date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 28))


@pytest.fixture
def sample_path():
    return ROOT / "sample_data" / "sample_transactions.csv"
