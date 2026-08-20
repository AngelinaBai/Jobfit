import pytest

from jobfit.config import Settings


def test_public_mode_requires_an_admin_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("PUBLIC_MODE", "true")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        Settings.from_env()


def test_public_mode_loads_admin_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("PUBLIC_MODE", "true")
    monkeypatch.setenv("ADMIN_USERNAME", "angelina")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password")
    settings = Settings.from_env()
    assert settings.public_mode is True
    assert settings.admin_username == "angelina"
    assert settings.admin_password == "test-password"
