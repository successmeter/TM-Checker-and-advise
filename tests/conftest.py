import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest


@pytest.fixture(autouse=True)
def full_check_results(monkeypatch, tmp_path):
    """Most tests look at the full check; the free summary has its own tests."""
    monkeypatch.setenv("TM_FREE_FULL", "1")
    monkeypatch.setenv("TM_DB", str(tmp_path / "orders.sqlite"))
    monkeypatch.setenv("TM_SECRET", "test-secret")
    monkeypatch.setenv("TM_REPORTS_DIR", str(tmp_path / "reports"))
    for name in ("STRIPE_SECRET_KEY", "RESEND_API_KEY", "TM_DEV_FREE_REPORTS", "TM_REVIEW_REPORTS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    from tm_advisor import api
    api._hits.clear()
