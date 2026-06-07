import json
from pathlib import Path
import asyncio
from pipeline.outreach_pipeline import OutreachPipeline
from config.settings import Settings
from models.company import Company
from models.contact import Contact

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "demo_data.json"


class DummySettings(Settings):
    OCEAN_API_TOKEN = "demo"
    PROSPEO_API_KEY = "demo"
    BREVO_API_KEY = "demo"
    BREVO_SENDER_EMAIL = "demo@example.com"


def load_demo_data():
    if DATA_FILE.exists():
        with DATA_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return {
        "companies": [
            {"domain": "example.com", "company_name": "Example Corp"},
            {"domain": "acme.com", "company_name": "Acme Inc"},
            {"domain": "widget.co", "company_name": "Widget Co"},
        ],
        "contacts": [
            {"full_name": "Alice Smith", "title": "CEO", "linkedin_url": "https://linkedin.com/in/alicesmith", "email": "alice@example.com", "company_domain": "example.com"},
            {"full_name": "Bob Johnson", "title": "CTO", "linkedin_url": "https://linkedin.com/in/bobjohnson", "email": "bob@acme.com", "company_domain": "acme.com"},
            {"full_name": "Cara Lee", "title": "VP Product", "linkedin_url": "https://linkedin.com/in/caralee", "email": "cara@widget.co", "company_domain": "widget.co"},
        ],
    }


class DummyOceanClient:
    def __init__(self, *a, **k):
        self.demo_data = load_demo_data()

    async def find_similar(self, domain, limit=10):
        companies = [Company(**item) for item in self.demo_data.get("companies", [])]
        return companies[:limit]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class DummyProspeoClient:
    def __init__(self, *a, **k):
        self.demo_data = load_demo_data()

    async def find_contacts(self, domain):
        return [Contact(**item) for item in self.demo_data.get("contacts", []) if item.get("company_domain") == domain]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class DummyBrevoClient:
    def __init__(self, *a, **k):
        pass

    async def send_email(self, sender, to_email, subject, html_content):
        print(f"[dummy send] {sender} -> {to_email}: {subject}")
        return True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def main():
    settings = DummySettings()
    pipeline = OutreachPipeline(settings)

    import services.async_clients as sac
    sac.AsyncOceanClient = DummyOceanClient
    sac.AsyncProspeoClient = DummyProspeoClient
    sac.AsyncBrevoClient = DummyBrevoClient

    import pipeline.outreach_pipeline as op
    op.AsyncOceanClient = DummyOceanClient
    op.AsyncProspeoClient = DummyProspeoClient
    op.AsyncBrevoClient = DummyBrevoClient

    print("Running demo dry-run (async) with sample JSON data")
    asyncio.run(pipeline.run_async("salesforce.com", dry_run=True, limit=10, export_csv=True))


if __name__ == '__main__':
    main()
