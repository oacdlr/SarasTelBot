import pytest


@pytest.fixture(autouse=True)
def vault(tmp_path, monkeypatch):
    """Point SARAS at a temporary vault; no real credentials needed.

    Autouse, so no test can read or write the real vault from .env.
    """
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    return tmp_path
