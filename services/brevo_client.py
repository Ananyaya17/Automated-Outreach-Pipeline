from typing import Dict, Any
from services.base_client import BaseClient
from utils.logger import get_logger

logger = get_logger(__name__)


class BrevoClient(BaseClient):
    def __init__(self, base_url: str, api_key: str, name: str = "brevo"):
        super().__init__(base_url, api_key, name=name)
        self.session.headers.pop("Authorization", None)
        self.session.headers.update({"api-key": api_key})

    def send_email(self, sender: str, to_email: str, subject: str, html_content: str) -> bool:
        payload = {
            "sender": {"email": sender},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_content,
        }
        try:
            self._post("/v3/smtp/email", json=payload)
            return True
        except Exception as e:
            logger.error("Brevo send failed to %s: %s", to_email, e)
            return False
