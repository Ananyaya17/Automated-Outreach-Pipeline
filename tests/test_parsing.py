from models.company import Company


def test_company_domain_validation():
    c = Company(domain="EXAMPLE.COM", company_name="Ex")
    assert c.domain == "example.com"


def test_settings_normalizes_legacy_prospeo_url(monkeypatch):
    import os

    monkeypatch.setenv("PROSPEO_BASE_URL", "https://app.prospeo.io/api")
    monkeypatch.setenv("OCEAN_API_TOKEN", "x")
    monkeypatch.setenv("PROSPEO_API_KEY", "x")
    monkeypatch.setenv("BREVO_API_KEY", "x")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "x@example.com")

    from config.settings import Settings

    settings = Settings()
    assert settings.PROSPEO_BASE_URL == "https://api.prospeo.io"
