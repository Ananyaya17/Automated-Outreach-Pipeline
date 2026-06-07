import json
import os
import pytest
from dotenv import load_dotenv
import requests

load_dotenv()

PLACEHOLDER_TOKENS = {"your_ocean_token_here", "your_ocean_key_here", "api_LU74KK_ozuT5V4nLAiL3PyNDe5IPcLzlBWWcKnx"}

def is_placeholder(value: str) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized.startswith("your_") or normalized.endswith("example") or normalized in PLACEHOLDER_TOKENS


def test_ocean_connection():
    token = os.getenv("OCEAN_API_TOKEN") or os.getenv("OCEAN_API_KEY")
    if not token or is_placeholder(token):
        pytest.skip("OCEAN_API_TOKEN not configured or using placeholder token")

    url = "https://api.ocean.io/v3/search/companies"
    payload = {
        "size": 10,
        "companiesFilters": {
            "lookalikeDomains": ["salesforce.com"],
        },
    }
    headers = {
        "X-Api-Token": token,
        "Content-Type": "application/json",
    }

    print("Request URL:", url)
    print("Request payload:", json.dumps(payload, indent=2))
    print("Request headers includes X-Api-Token:", "X-Api-Token" in headers)

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    print("Response status code:", response.status_code)

    try:
        body = response.json()
        print("Response body:", json.dumps(body, indent=2))
    except ValueError:
        print("Response body is not valid JSON:", response.text)
        body = None

    if response.status_code != 200:
        pytest.fail(f"Ocean API request failed with {response.status_code}: {response.text}")

    items = []
    if body:
        items = body.get("companies") or body.get("results") or []

    print("Number of companies returned:", len(items))
    for company in items[:5]:
        print("Company:", company)

    assert response.status_code == 200
    assert isinstance(items, list)
