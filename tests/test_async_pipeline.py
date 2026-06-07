import pytest
import asyncio
from pipeline.outreach_pipeline import OutreachPipeline
from config.settings import Settings


@pytest.mark.asyncio
async def test_async_pipeline_runs_dry(monkeypatch):
    class DummySettings(Settings):
        OCEAN_API_TOKEN = "x"
        PROSPEO_API_KEY = "x"
        BREVO_API_KEY = "x"
        BREVO_SENDER_EMAIL = "me@example.com"

    settings = DummySettings()
    pipeline = OutreachPipeline(settings)

    # patch async clients to avoid network calls
    async def fake_find_similar(domain, limit=10):
        return []

    async def fake_find_contacts(domain):
        return []

    monkeypatch.setattr('services.async_clients.AsyncOceanClient.find_similar', fake_find_similar)
    monkeypatch.setattr('services.async_clients.AsyncProspeoClient.find_contacts', fake_find_contacts)

    await pipeline.run_async('example.com', dry_run=True)
