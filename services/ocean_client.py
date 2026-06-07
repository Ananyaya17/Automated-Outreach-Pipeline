from typing import List
from services.base_client import BaseClient
from models.company import Company
from utils.logger import get_logger

logger = get_logger(__name__)


class OceanClient(BaseClient):
    def __init__(self, base_url: str, api_key: str, name: str = "ocean"):
        super().__init__(base_url, api_key, name=name)
        self.session.headers.pop("Authorization", None)
        self.session.headers.update({"X-Api-Token": api_key})

    def find_similar(self, domain: str, limit: int = 10) -> List[Company]:
        payload = {
            "size": limit,
            "companiesFilters": {
                "lookalikeDomains": [domain],
            },
        }
        try:
            data = self._post("/v3/search/companies", json=payload)
        except Exception as e:
            logger.error("Ocean API failed for %s: %s", domain, e)
            return []

        items = data.get("companies") or data.get("results") or data.get("data") or []
        if not isinstance(items, list):
            items = []
        companies = []
        for it in items:
            company_data = it.get("company") if isinstance(it, dict) and "company" in it else it
            if not isinstance(company_data, dict):
                continue
            domain_value = company_data.get("domain") or company_data.get("website")
            name_value = company_data.get("name") or ""
            if not domain_value:
                continue
            try:
                companies.append(Company(domain=domain_value, company_name=name_value))
            except Exception as e:
                logger.debug("Skipping invalid company: %s", e)
        if limit and len(companies) > limit:
            companies = companies[:limit]
        return companies
