from app.core.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "test-host")
    settings = Settings()
    assert settings.postgres_host == "test-host"


def test_settings_defaults():
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "openai"
