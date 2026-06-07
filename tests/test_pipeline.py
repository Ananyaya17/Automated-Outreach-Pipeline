from pipeline.outreach_pipeline import OutreachPipeline
from config.settings import Settings
import os


def test_pipeline_runs_dry(monkeypatch, tmp_path):
    # minimal smoke test: patch clients to avoid network
    class DummySettings(Settings):
        OCEAN_API_TOKEN = "x"
        PROSPEO_API_KEY = "x"
        BREVO_API_KEY = "x"
        BREVO_SENDER_EMAIL = "me@example.com"

    settings = DummySettings()
    pipeline = OutreachPipeline(settings)

    # stub methods
    monkeypatch.setattr(pipeline.ocean, "find_similar", lambda domain, limit=10: [])
    pipeline.run(seed_domain="example.com", dry_run=True)
