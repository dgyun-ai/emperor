"""Session store profile path consistency."""

from constants import normalize_profile
from session.store import SessionStore


def test_for_profile_none_matches_default(monkeypatch, tmp_path):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    none_store = SessionStore.for_profile(None)
    default_store = SessionStore.for_profile("default")
    assert none_store.db_path == default_store.db_path
    assert "profiles" in str(none_store.db_path)
    assert normalize_profile(None) == "default"
