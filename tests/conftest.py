"""pytest configuration and shared fixtures."""
import os

import pytest


@pytest.fixture(autouse=True)
def _override_settings(monkeypatch, tmp_path):
    """Point config at a test database and temp staging dir.

    Override POSTGRES_* vars with TEST_POSTGRES_* if set, so integration
    tests can target a dedicated test DB without touching production data.
    """
    for var in ("HOST", "PORT", "DB", "USER", "PASSWORD"):
        test_val = os.environ.get(f"TEST_POSTGRES_{var}")
        if test_val:
            monkeypatch.setenv(f"POSTGRES_{var}", test_val)

    monkeypatch.setenv("STAGING_DIR", str(tmp_path / "staging"))


@pytest.fixture()
def settings():
    from plinth.config import get_settings
    return get_settings()
