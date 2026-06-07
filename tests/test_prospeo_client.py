import requests
import random
from services.prospeo_client import ProspeoClient


def test_prospeo_client_search_person_request(monkeypatch):
    captured = {}

    def fake_post(self, url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = dict(self.headers)

        class FakeResponse:
            def __init__(self, url):
                self.status_code = 200
                self.ok = True
                self._url = url
                class R:
                    method = "POST"
                self.request = R()
                self.url = url
            def json(self):
                return {"contacts": []}
        return FakeResponse(url)

    monkeypatch.setattr("requests.sessions.Session.post", fake_post)

    client = ProspeoClient("https://api.prospeo.io", "testkey")
    contacts = client.find_contacts("example.com")

    assert contacts == []
    assert captured["url"] == "https://api.prospeo.io/search-person"
    assert captured["json"] == {
        "page": 1,
        "filters": {
            "company": {
                "websites": {
                    "include": ["example.com"]
                }
            }
        }
    }
    assert captured["headers"]["X-KEY"] == "testkey"
    assert captured["headers"]["Content-Type"] == "application/json"


def test_prospeo_client_retries_and_skips_on_rate_limit(monkeypatch):
    post_calls = []
    sleep_calls = []

    def fake_post(self, url, json=None, timeout=None):
        post_calls.append(url)

        class FakeResponse:
            def __init__(self, url):
                self.status_code = 429
                self.ok = False
                self.text = "rate limited"
                class R:
                    method = "POST"
                self.request = R()
                self.url = url
            def json(self):
                return {}

        return FakeResponse(url)

    monkeypatch.setattr("requests.sessions.Session.post", fake_post)
    monkeypatch.setattr("services.prospeo_client.ProspeoClient._wait_for_slot", lambda self: None)
    monkeypatch.setattr("services.prospeo_client.random.random", lambda: 0.0)
    monkeypatch.setattr("time.sleep", lambda delay: sleep_calls.append(delay))

    client = ProspeoClient("https://api.prospeo.io", "testkey")
    contacts = client.find_contacts("example.com")

    assert contacts == []
    assert len(post_calls) == client.MAX_RETRIES + 1
    assert sleep_calls == [1.0, 2.0, 4.0, 8.0, 16.0]


def test_prospeo_client_preserves_contacts_without_title_filter(monkeypatch):
    def fake_post(self, url, json=None, timeout=None):
        class FakeResponse:
            def __init__(self, url):
                self.status_code = 200
                self.ok = True
                class R:
                    method = "POST"
                self.request = R()
                self.url = url
            def json(self):
                return {
                    "contacts": [
                        {
                            "name": "Alice Example",
                            "title": "Marketing Manager",
                            "email": "alice@example.com",
                            "linkedin": "https://linkedin.com/in/alice",
                        }
                    ]
                }
        return FakeResponse(url)

    monkeypatch.setattr("requests.sessions.Session.post", fake_post)
    client = ProspeoClient("https://api.prospeo.io", "testkey")
    contacts = client.find_contacts("example.com")
    assert len(contacts) == 1
    assert contacts[0].email == "alice@example.com"
    assert contacts[0].full_name == "Alice Example"
