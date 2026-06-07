from services.email_generator import generate_email
from models.contact import Contact


def test_generate_email_basic():
    contact = Contact(full_name="Alice Smith", title="CEO", linkedin_url=None, email=None, company_domain="acme.com")
    mail = generate_email(contact, "Acme Inc")
    assert "Helping" in mail["subject"]
    assert "Hi Alice" in mail["body"]
