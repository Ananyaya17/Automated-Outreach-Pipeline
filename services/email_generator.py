from jinja2 import Template
from models.contact import Contact
from utils.logger import get_logger

logger = get_logger(__name__)

SUBJECT_TPL = "Helping {{ company_name }} scale outreach"
BODY_TPL = """
Hi {{ first_name }},

I came across {{ company_name }} and was impressed by your work.

I thought this might be relevant and would love to share a quick note about how we help teams scale outreach.

Best,
Your Name
"""


def generate_email(contact: Contact, company_name: str) -> dict:
    subject = Template(SUBJECT_TPL).render(company_name=company_name)
    body = Template(BODY_TPL).render(first_name=contact.first_name, company_name=company_name)
    logger.debug("Generated email for %s", contact.full_name)
    return {"subject": subject, "body": body}
