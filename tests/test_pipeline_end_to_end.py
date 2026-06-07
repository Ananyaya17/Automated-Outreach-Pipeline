from pipeline.outreach_pipeline import OutreachPipeline
from config.settings import Settings
from models.company import Company
from models.contact import Contact
import os


def test_pipeline_end_to_end_creates_csv(monkeypatch, tmp_path):
    class DummySettings(Settings):
        OCEAN_API_TOKEN = "x"
        PROSPEO_API_KEY = "x"
        BREVO_API_KEY = "x"
        BREVO_SENDER_EMAIL = "me@example.com"

    settings = DummySettings()
    pipeline = OutreachPipeline(settings)

    # create fake companies
    companies = [Company(domain="example.com", company_name="Example"), Company(domain="acme.com", company_name="Acme")]

    # fake contacts per domain
    def fake_find_similar(domain, limit=10):
        return companies

    def fake_find_contacts(domain):
        if domain == "example.com":
            return [Contact(full_name="Alice Ex", title="CEO", linkedin_url="", email="alice@example.com", company_domain=domain)]
        if domain == "acme.com":
            return [Contact(full_name="Bob Acme", title="CTO", linkedin_url="", email="bob@acme.com", company_domain=domain)]
        return []

    monkeypatch.setattr(pipeline.ocean, "find_similar", fake_find_similar)
    monkeypatch.setattr(pipeline.prospeo, "find_contacts", fake_find_contacts)

    # run in temporary directory so exports go to tmp_path
    monkeypatch.chdir(tmp_path)

    pipeline.run(seed_domain="seed.com", dry_run=True, limit=10, export_csv=True)

    csv_file = tmp_path / "exports" / "leads.csv"
    assert csv_file.exists(), "CSV file should be created when leads exist"

    content = csv_file.read_text(encoding="utf-8")
    assert "alice@example.com" in content
    assert "bob@acme.com" in content
