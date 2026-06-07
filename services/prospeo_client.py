import random
import threading
import time
from typing import Any, Dict, List, Optional

import requests
from services.base_client import APIError, BaseClient
from models.contact import Contact
from utils.logger import get_logger

logger = get_logger(__name__)


class RateLimitError(requests.exceptions.RequestException):
    pass


class ProspeoClient(BaseClient):
    TARGET_TITLES = ["CEO", "Founder", "CTO", "VP Engineering", "VP Product"]
    MAX_RETRIES = 3
    MAX_BACKOFF = 60
    MIN_PACING_SECONDS = 5.0
    MAX_PACING_SECONDS = 7.0
    MAX_DAILY_REQUESTS = 30

    def __init__(self, base_url: str, api_key: str, name: str = "prospeo"):
        super().__init__(base_url, api_key, name=name)
        self.session.headers.pop("Authorization", None)
        self.session.headers.update({"X-KEY": self.api_key, "Content-Type": "application/json"})
        self._lock = threading.Lock()
        self._last_request_time = 0.0
        self._daily_request_count = 0

    def _wait_for_slot(self) -> None:
        with self._lock:
            desired_delay = random.uniform(self.MIN_PACING_SECONDS, self.MAX_PACING_SECONDS)
            elapsed = time.time() - self._last_request_time
            if elapsed < desired_delay:
                wait_time = desired_delay - elapsed
                logger.debug("Waiting %.2fs before Prospeo request to respect pacing", wait_time)
                time.sleep(wait_time)
            self._last_request_time = time.time()

    def _send_post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._wait_for_slot()
        url = self._url(path)
        domain_list = json.get("filters", {}).get("company", {}).get("websites", {}).get("include", []) if isinstance(json, dict) else []
        logger.debug("DOMAIN: %s", domain_list)
        logger.debug("PAYLOAD: %s", json)
        logger.debug("POST %s", url)
        # Count daily requests and stop if we've hit the limit
        with self._lock:
            if self._daily_request_count >= self.MAX_DAILY_REQUESTS:
                logger.warning("Reached MAX_DAILY_REQUESTS (%s). Skipping request for %s", self.MAX_DAILY_REQUESTS, domain_list)
                return {}
            self._daily_request_count += 1
        resp = self.session.post(url, json=json, timeout=30)
        logger.debug("STATUS: %s", resp.status_code)
        try:
            body = resp.json()
            logger.debug("RESPONSE: %s", body)
        except ValueError:
            body = None
            logger.debug("RESPONSE (raw): %s", resp.text)
        if resp.status_code == 429:
            raise RateLimitError("Prospeo rate limited")
        return self._handle_response(resp)

    def _extract_contacts(self, data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(data, dict):
            return []
        if isinstance(data.get("contacts"), list):
            return data["contacts"]
        if isinstance(data.get("people"), list):
            return data["people"]
        if isinstance(data.get("results"), list):
            return data["results"]
        nested = data.get("data")
        if isinstance(nested, dict):
            return self._extract_contacts(nested)
        if isinstance(nested, list):
            return nested
        return []

    def find_contacts(self, domain: str) -> List[Contact]:
        payload = {
            "page": 1,
            "filters": {
                "company": {
                    "websites": {
                        "include": [domain]
                    }
                }
            }
        }
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                data = self._send_post("/search-person", json=payload)
                break
            except RateLimitError as e:
                if attempt == self.MAX_RETRIES:
                    logger.warning("Skipping domain due to rate limit after %s retries: %s", self.MAX_RETRIES, domain)
                    return []
                # Extra fixed wait before applying exponential backoff to reduce collision
                time.sleep(10)
                backoff = min(self.MAX_BACKOFF, 2 ** attempt)
                sleep_time = backoff + random.random()
                logger.warning(
                    "Prospeo rate limit detected for %s, retry attempt %s/%s after %.2fs",
                    domain,
                    attempt + 1,
                    self.MAX_RETRIES,
                    sleep_time,
                )
                time.sleep(sleep_time)
                continue
            except requests.exceptions.RequestException as e:
                logger.error("Prospeo request failed for %s: %s", domain, e)
                return []
            except APIError as e:
                logger.error("Prospeo API error for %s: %s", domain, e)
                return []
            except Exception as e:
                logger.error("Prospeo unexpected error for %s: %s", domain, e)
                return []

        items = self._extract_contacts(data)
        if not items:
            logger.info("No contacts found for %s", domain)
            return []

        contacts = []
        for it in items:
            if not isinstance(it, dict):
                continue
            # Some API responses wrap the person data under a key like 'person' or 'contact'
            if "person" in it and isinstance(it.get("person"), dict):
                it = it.get("person")
            elif "contact" in it and isinstance(it.get("contact"), dict):
                it = it.get("contact")
            fullname = it.get("name") or it.get("full_name") or it.get("first_name") or ""
            title = it.get("title") or it.get("position") or ""
            linkedin = it.get("linkedin") or it.get("linkedinUrl") or it.get("linkedin_url")
            email = it.get("email") or it.get("emailAddress")
            if not email and isinstance(it.get("emails"), list):
                email = next((e for e in it.get("emails") if isinstance(e, str) and e.strip()), None)
            if isinstance(email, str):
                email = email.strip() or None
            if not email and not fullname:
                continue
            try:
                contact = Contact(
                    full_name=fullname,
                    title=title,
                    linkedin_url=linkedin,
                    email=email,
                    company_domain=domain,
                )
                contacts.append(contact)
            except Exception as e:
                logger.debug("Skipping invalid contact: %s", e)
        logger.info("Prospeo returned %s contact objects for %s", len(contacts), domain)
        return contacts
