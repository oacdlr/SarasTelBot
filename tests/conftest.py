import pytest


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Point SARAS at a temporary vault; no real credentials needed."""
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    return tmp_path
