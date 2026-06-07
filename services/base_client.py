from typing import Any, Dict, Optional
import requests
from requests import Response
from utils.retry import retry_on_exceptions
from utils.logger import get_logger
import time

logger = get_logger(__name__)


class APIError(Exception):
    pass


class BaseClient:
    def __init__(self, base_url: str, api_key: str, name: str = "api"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = name
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/') }"

    @retry_on_exceptions()
    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._url(path)
        logger.debug("GET %s %s", url, params)
        resp = self.session.get(url, params=params, timeout=20)
        return self._handle_response(resp)

    @retry_on_exceptions()
    def _post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._url(path)
        logger.debug("POST %s %s", url, json)
        resp = self.session.post(url, json=json, timeout=30)
        return self._handle_response(resp)

    def _handle_response(self, resp: Response) -> Dict[str, Any]:
        logger.debug("%s %s -> %s", resp.request.method, resp.url, resp.status_code)
        if resp.status_code == 429:
            # rate limited
            retry_after = int(resp.headers.get("Retry-After", "1"))
            logger.warning("Rate limited, sleeping %s", retry_after)
            time.sleep(retry_after)
            raise requests.exceptions.RequestException("Rate limited")
        if not resp.ok:
            logger.error("API %s returned %s: %s", self.name, resp.status_code, resp.text)
            raise APIError(f"{self.name} API error: {resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            raise APIError("Invalid JSON response")
