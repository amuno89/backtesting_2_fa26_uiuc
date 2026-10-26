import os
import pytest
from data import load_prices


@pytest.fixture(scope="session")
def approved_prices():
    """Load the approved local inputs once; tests work with their own derived tables."""
    folder = os.environ.get("BACKTEST_DATA")
    if not folder:
        pytest.skip("Set BACKTEST_DATA to the approved existing dataset folder.")
    return load_prices(folder)
