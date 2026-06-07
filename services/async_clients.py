"""Async versions of the API clients using httpx."""
from typing import Any, Dict, List, Optional
import asyncio
import random
import time

import httpx
from models.company import Company
from models.contact import Contact
from services.base_client import APIError
from utils.logger import get_logger

logger = get_logger(__name__)


class AsyncOceanClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        try:
            import httpx
            self.client = httpx.AsyncClient(headers={"X-Api-Token": self.api_key}, timeout=20.0)
        except Exception as exc:
            raise RuntimeError("AsyncOceanClient requires httpx and a functional AsyncClient") from exc
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def find_similar(self, domain: str, limit: int = 10) -> List[Company]:
        url = f"{self.base_url}/v3/search/companies"
        payload = {
            "size": limit,
            "companiesFilters": {
                "lookalikeDomains": [domain],
            },
        }
        logger.debug("Async POST %s %s", url, payload)
        try:
            r = await self.client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            items = data.get("companies") or data.get("results") or data.get("data") or []
            if not isinstance(items, list):
                items = []
            companies: List[Company] = []
            for it in items[:limit]:
                company_data = it.get("company") if isinstance(it, dict) and "company" in it else it
                if not isinstance(company_data, dict):
                    continue
                domain_value = company_data.get("domain") or company_data.get("website")
                name_value = company_data.get("name") or ""
                if not domain_value:
                    continue
                try:
                    companies.append(Company(domain=domain_value, company_name=name_value))
                except Exception as exc:
                    logger.debug("Skipping invalid company: %s", exc)
            return companies
        except Exception as e:
            logger.error("Async Ocean error: %s", e)
            return []


class AsyncProspeoClient:
    TARGET_TITLES = ["CEO", "Founder", "CTO", "VP Engineering", "VP Product"]
    MAX_RETRIES = 5
    MAX_BACKOFF = 60
    MIN_PACING_SECONDS = 1.0
    MAX_PACING_SECONDS = 2.0

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        try:
            self.client = httpx.AsyncClient(headers={"X-KEY": self.api_key, "Content-Type": "application/json"}, timeout=20.0)
        except Exception as exc:
            raise RuntimeError("AsyncProspeoClient requires httpx and a functional AsyncClient") from exc
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _wait_for_slot(self) -> None:
        async with self._lock:
            desired_delay = random.uniform(self.MIN_PACING_SECONDS, self.MAX_PACING_SECONDS)
            elapsed = time.time() - self._last_request_time
            if elapsed < desired_delay:
                wait_time = desired_delay - elapsed
                logger.debug("Waiting %.2fs before Async Prospeo request to respect pacing", wait_time)
                await asyncio.sleep(wait_time)
            self._last_request_time = time.time()

    async def _post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self._wait_for_slot()
        url = f"{self.base_url}/{path.lstrip('/')}"
        logger.debug("Async POST %s %s", url, json)
        r = await self.client.post(url, json=json)
        logger.debug("STATUS: %s", r.status_code)
        try:
            body = r.json()
            logger.debug("RESPONSE: %s", body)
        except ValueError:
            logger.debug("RESPONSE (raw): %s", r.text)
        if r.status_code == 429:
            raise httpx.RequestError("Async Prospeo rate limited")
        if r.status_code >= 400:
            logger.error("Async Prospeo API error %s: %s", r.status_code, r.text)
            raise APIError(f"Async Prospeo API error: {r.status_code}")
        try:
            return r.json()
        except ValueError as exc:
            raise APIError("Invalid JSON response") from exc

    def _extract_email(self, email_field: object) -> Optional[str]:
        if not email_field:
            return None
        if isinstance(email_field, dict):
            for key in ("email", "emailAddress", "value"):
                val = email_field.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            return None
        if isinstance(email_field, list):
            for it in email_field:
                if isinstance(it, str) and it.strip():
                    return it.strip()
            return None
        if isinstance(email_field, str):
            return email_field.strip() or None
        return None

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

    async def find_contacts(self, domain: str) -> List[Contact]:
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
                data = await self._post("/search-person", json=payload)
                break
            except httpx.RequestError as e:
                if getattr(e, 'request', None) is not None and e.request:
                    status_code = getattr(e, 'response', None) and getattr(e.response, 'status_code', None)
                else:
                    status_code = None
                if status_code == 429 or 'rate limited' in str(e).lower():
                    if attempt == self.MAX_RETRIES:
                        logger.warning("Skipping domain due to rate limit after %s retries: %s", self.MAX_RETRIES, domain)
                        return []
                    backoff = min(self.MAX_BACKOFF, 2 ** attempt)
                    delay = backoff + random.random()
                    logger.warning(
                        "Async Prospeo rate limit detected for %s, retry attempt %s/%s after %.2fs",
                        domain,
                        attempt + 1,
                        self.MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error("Async Prospeo request failed for %s: %s", domain, e)
                return []
            except APIError as e:
                logger.error("Async Prospeo API error for %s: %s", domain, e)
                return []
            except Exception as e:
                logger.error("Async Prospeo unexpected error for %s: %s", domain, e)
                return []

        items = self._extract_contacts(data)
        if not items:
            logger.info("No contacts found for %s", domain)
            return []

        contacts = []
        for it in items:
            if not isinstance(it, dict):
                continue
            if "person" in it and isinstance(it.get("person"), dict):
                it = it.get("person")
            elif "contact" in it and isinstance(it.get("contact"), dict):
                it = it.get("contact")
            fullname = it.get("name") or it.get("full_name") or it.get("first_name") or ""
            title = it.get("title") or it.get("position") or ""
            linkedin = it.get("linkedin") or it.get("linkedinUrl") or it.get("linkedin_url")
            email = self._extract_email(it.get("email") or it.get("emailAddress") or it.get("emails"))
            if not email and isinstance(it.get("emails"), list):
                email = self._extract_email(it.get("emails"))
            if not email and not fullname:
                continue
            try:
                contacts.append(Contact(full_name=fullname, title=title, linkedin_url=linkedin, email=email, company_domain=domain))
            except Exception as exc:
                logger.debug("Skipping invalid contact: %s", exc)
        logger.info("Async Prospeo returned %s contact objects for %s", len(contacts), domain)
        return contacts
class AsyncBrevoClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        try:
            import httpx
            self.client = httpx.AsyncClient(headers={"api-key": self.api_key, "Content-Type": "application/json"}, timeout=30.0)
        except Exception as exc:
            raise RuntimeError("AsyncBrevoClient requires httpx and a functional AsyncClient") from exc
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def send_email(self, sender: str, to_email: str, subject: str, html_content: str) -> bool:
        url = f"{self.base_url}/v3/smtp/email"
        payload = {
            "sender": {"email": sender},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_content,
        }
        try:
            r = await self.client.post(url, json=payload)
            r.raise_for_status()
            return True
        except Exception as e:
            logger.error("Async Brevo send failed: %s", e)
            return False
