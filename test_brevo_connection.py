import json
import os
import pytest
from dotenv import load_dotenv
import requests

load_dotenv()

PLACEHOLDER_KEYS = {"your_brevo_key_here", "xkeysib-eee0ad9a7ed49a9c33b01d650649315a997688f4n1cda6b5c5803ac4394d8ace-9IxMdJ5BRIjeyOcg"}


def is_placeholder(value: str) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized.startswith("your_") or normalized.endswith("example") or normalized in PLACEHOLDER_KEYS


def test_brevo_connection():
    api_key = os.getenv("BREVO_API_KEY")
    sender = os.getenv("BREVO_SENDER_EMAIL")
    if not api_key or not sender or is_placeholder(api_key) or is_placeholder(sender):
        pytest.skip("BREVO_API_KEY or BREVO_SENDER_EMAIL not configured or using placeholder values")

    base_url = os.getenv("BREVO_BASE_URL", "https://api.brevo.com").rstrip("/")
    headers = {"api-key": api_key, "Content-Type": "application/json"}

    account_url = f"{base_url}/v3/account"
    print("Account request URL:", account_url)
    response = requests.get(account_url, headers=headers, timeout=30)
    print("Account response status:", response.status_code)
    try:
        account_body = response.json()
        print("Account response body:", json.dumps(account_body, indent=2))
    except ValueError:
        print("Account response body is not valid JSON:", response.text)
        account_body = None

    if response.status_code != 200:
        pytest.fail(f"Brevo account request failed with {response.status_code}: {response.text}")

    sender_url = f"{base_url}/v3/smtp/verified-senders"
    print("Verified senders request URL:", sender_url)
    sender_resp = requests.get(sender_url, headers=headers, timeout=30)
    print("Verified senders response status:", sender_resp.status_code)
    try:
        sender_body = sender_resp.json()
        print("Verified senders response body:", json.dumps(sender_body, indent=2))
    except ValueError:
        print("Verified senders response body is not valid JSON:", sender_resp.text)
        sender_body = None

    if sender_resp.status_code not in (200, 404):
        pytest.fail(f"Brevo verified senders request failed with {sender_resp.status_code}: {sender_resp.text}")

    verified = False
    if sender_body and isinstance(sender_body, dict):
        for item in sender_body.get("senders", []) or sender_body.get("verifiedSenders", []):
            if item.get("email") == sender:
                verified = True
                break

    print("BREVO_SENDER_EMAIL:", sender)
    print("Sender verified:", verified)
    print("Account auth status: OK")

    assert response.status_code == 200
