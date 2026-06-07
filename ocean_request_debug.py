import json
import os
from dotenv import load_dotenv
import requests
from config.settings import Settings


def redact_token(token: str) -> str:
    if not token:
        return ""
    return f"{token[:6]}...{token[-4:]}"


def main():
    load_dotenv()
    token = None
    try:
        settings = Settings()
        token = settings.OCEAN_API_TOKEN
        base_url = settings.OCEAN_BASE_URL
    except Exception as exc:
        print("Settings load error:", exc)
        token = os.getenv("OCEAN_API_TOKEN") or os.getenv("OCEAN_API_KEY")
        base_url = os.getenv("OCEAN_BASE_URL", "https://api.ocean.io")

    if not token:
        print("No Ocean token found in OCEAN_API_TOKEN or OCEAN_API_KEY")
        return

    token = str(token).strip()
    print("Token length:", len(token))
    print("Token preview:", redact_token(token))
    print("Token contains whitespace:", bool(token.strip() != token))

    url = f"{base_url.rstrip('/')}/v3/search/companies"
    payload = {
        "size": 10,
        "companiesFilters": {"lookalikeDomains": ["salesforce.com"]},
    }
    headers = {
        "X-Api-Token": token,
        "Content-Type": "application/json",
    }

    print("Request URL:", url)
    print("Request headers contains X-Api-Token:", "X-Api-Token" in headers)
    print("Request headers contains Authorization:", "Authorization" in headers)
    print("Final request headers:", json.dumps({k: (v if k != "X-Api-Token" else redact_token(v)) for k, v in headers.items()}, indent=2))
    print("Request payload:", json.dumps(payload, indent=2))

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print("Response status code:", response.status_code)
        try:
            body = response.json()
            print("Response body:", json.dumps(body, indent=2))
        except ValueError:
            print("Response body is not valid JSON:", response.text)
            body = None
        if response.status_code != 200:
            print("Ocean API issue detected: token may be invalid or account access denied.")
    except Exception as exc:
        print("Request failed:", exc)


if __name__ == "__main__":
    main()
