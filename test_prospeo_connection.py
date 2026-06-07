import json
import os
import pytest
from dotenv import load_dotenv
import requests
from services.prospeo_client import ProspeoClient

load_dotenv()

PLACEHOLDER_KEYS = {"your_prospeo_key_here", "your_prospeo_api_key_here"}


def is_placeholder(value: str) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized.startswith("your_") or normalized.endswith("example") or normalized in PLACEHOLDER_KEYS


def test_prospeo_connection():
    api_key = os.getenv("PROSPEO_API_KEY")
    if not api_key or is_placeholder(api_key):
        pytest.skip("PROSPEO_API_KEY not configured or using placeholder key")

    base_url = os.getenv("PROSPEO_BASE_URL", "https://api.prospeo.io").rstrip("/")
    if is_placeholder(base_url):
        pytest.skip("PROSPEO_BASE_URL not configured or is placeholder")
    url = f"{base_url}/search-person"
    payload = {
        "page": 1,
        "filters": {
            "company": {
                "websites": {
                    "include": ["salesforce.com"]
                }
            }
        }
    }
    headers = {"X-KEY": f"{api_key}", "Content-Type": "application/json"}

    print("Request URL:", url)
    print("Request payload:", payload)
    print("Request headers includes X-KEY:", "X-KEY" in headers)

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    print("Response status code:", response.status_code)

    try:
        body = response.json()
        print("Response body:", json.dumps(body, indent=2))
    except ValueError:
        print("Response body is not valid JSON:", response.text)
        body = None

    if response.status_code != 200:
        pytest.fail(f"Prospeo API request failed with {response.status_code}: {response.text}")

    items = body.get("contacts") if body and isinstance(body, dict) else []
    print("Raw contacts returned:", len(items))

    emails = []
    verified_emails = []
    for it in items:
        email = it.get("email") or it.get("emailAddress")
        if not email and isinstance(it.get("emails"), list):
            email = next((e for e in it.get("emails") if isinstance(e, str) and e.strip()), None)
        if email:
            emails.append(email)
            if it.get("verified") is True or it.get("isVerified") is True:
                verified_emails.append(email)

    print("Emails found:", len(emails))
    print("Verified emails found:", len(verified_emails))
    print("Example results:")
    for contact in items[:5]:
        print(contact)

    client = ProspeoClient(base_url, api_key)
    filtered_contacts = client.find_contacts("salesforce.com")
    print("Filtered contact objects returned by ProspeoClient:", len(filtered_contacts))
    for contact in filtered_contacts[:5]:
        print(contact)

    assert response.status_code == 200
    assert isinstance(items, list)
