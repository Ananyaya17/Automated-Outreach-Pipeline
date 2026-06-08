# Architecture Documentation

## System Overview

The Automated Outreach Pipeline is a modular, multi-stage system designed to orchestrate API calls across three external services (Ocean.io, Prospeo, Brevo) to automate the discovery and outreach to potential B2B prospects.

### Core Principles

1. **Stage-based Processing:** Each stage is independent and encapsulated
2. **Synchronous & Asynchronous Modes:** Support both blocking and non-blocking execution
3. **Defensive Validation:** Validate all external API responses before use
4. **Graceful Degradation:** Fail loudly but safely; never silently drop data
5. **Audit Trail:** Log all major operations for debugging and compliance

---

## Module Structure

```
project/
├── config/
│   └── settings.py          # Configuration management and validation
├── models/
│   ├── company.py           # Company dataclass with validation
│   └── contact.py           # Contact dataclass with utilities
├── services/
│   ├── base_client.py       # HTTP client base class with retry logic
│   ├── ocean_client.py      # Ocean.io API client
│   ├── prospeo_client.py    # Prospeo API client
│   ├── brevo_client.py      # Brevo email API client
│   ├── async_clients.py     # Async versions of above clients
│   ├── email_generator.py   # Email template personalization
│   └── validation.py        # API response validators
├── pipeline/
│   └── outreach_pipeline.py # Main orchestrator (sync & async)
├── utils/
│   ├── logger.py            # Structured logging setup
│   ├── pii_logger.py        # Redaction of sensitive data
│   └── retry.py             # Retry decorator with exponential backoff
├── tests/
│   └── test_*.py            # Unit and integration tests
└── main.py                  # CLI entry point
```

---

## Detailed Component Responsibilities

### Config Module (`config/settings.py`)

**Responsibility:** Load and validate environment configuration at startup.

**Key Functions:**
- `__init__()`: Load all API keys from environment; validate required settings
- `_load_env()`: Fetch environment variable with aliases and defaults
- `_validate_required_settings()`: Ensure all critical keys are present and valid
- `_normalize_prospeo_base_url()`: Handle legacy/malformed Prospeo URLs

**Error Handling:**
- Raises `ValueError` if required settings missing or invalid
- Logs warnings for placeholder/test URLs
- Exits early before any API calls

**Design Note:** Settings are loaded once at startup. To reload after env changes, restart the process.

---

### Models Module

#### Company (`models/company.py`)

**Dataclass representing a company entity.**

```python
@dataclass
class Company:
    domain: str         # e.g., "salesforce.com"
    company_name: str   # e.g., "Salesforce"
```

**Validation Rules (in `__post_init__`):**
- `domain` must not be empty, contain spaces, or lack a dot
- `domain` is lowercased and stripped

**Usage:** Returned by Ocean.io API client; passed to Prospeo client.

#### Contact (`models/contact.py`)

**Dataclass representing a prospect contact.**

```python
@dataclass
class Contact:
    full_name: str              # e.g., "John Smith"
    title: str                  # e.g., "VP Sales"
    linkedin_url: Optional[str] # LinkedIn profile URL
    email: Optional[str]        # Work email (may be dict/list/str)
    company_domain: str         # Domain of employer
```

**Computed Properties:**
- `first_name`: Extracted from full_name (first word)

**Validation Rules:**
- `company_domain` is lowercased and stripped

**Usage:** Returned by Prospeo API client; filtered and deduplicated by pipeline.

---

### Services Module

#### BaseClient (`services/base_client.py`)

**Abstract HTTP client for all API interactions.**

**Key Methods:**
- `_get(path, params)`: GET request with retry logic
- `_post(path, json)`: POST request with retry logic
- `_handle_response(resp)`: Parse and validate HTTP response

**Retry Strategy:**
- Decorated with `@retry_on_exceptions()` (max 3 attempts)
- On 429 (rate limit): Sleep for `Retry-After` header, then retry
- On 5xx (server error): Exponential backoff (1s, 2s, 4s)
- On timeout/connection error: Exponential backoff

**Headers:**
- `Authorization: Bearer {api_key}`
- `Content-Type: application/json`

#### OceanClient (`services/ocean_client.py`)

**Wrapper for Ocean.io company discovery API.**

**Key Methods:**
- `find_similar(seed_domain: str, limit: int) -> List[Company]`

**Behavior:**
- Calls `/companies/similar?domain={seed}&limit={limit}`
- Validates each company with `validate_ocean_company()`
- Returns list of Company objects
- Logs domain name, not full response (for privacy)

**Rate Limits:** Typically 100-500 calls/month depending on plan

#### ProspeoClient (`services/prospeo_client.py`)

**Wrapper for Prospeo decision maker and email lookup API.**

**Key Methods:**
- `find_contacts(domain: str) -> List[Contact]`

**Behavior:**
- Calls `/api/v3/people?domain={domain}`
- Validates each contact with `validate_prospeo_contact()`
- Returns list of Contact objects
- Email format may vary (string, dict, list); client normalizes in pipeline

**Rate Limits:** Typically 30-60 calls/min (hardcoded 2s delay in pipeline)

#### BrevoClient (`services/brevo_client.py`)

**Wrapper for Brevo email sending API.**

**Key Methods:**
- `send_email(from_addr: str, to_addr: str, subject: str, body: str) -> bool`

**Behavior:**
- Calls `/v3/smtp/email`
- Returns True if email accepted (messageId present)
- Returns False if Brevo returns error dict
- Raises APIError on invalid response schema

**Rate Limits:** Depends on plan; free tier ~300/hour

#### AsyncClients (`services/async_clients.py`)

**Async versions of OceanClient, ProspeoClient, BrevoClient.**

**Key Differences:**
- Use `aiohttp.ClientSession` instead of `requests.Session`
- Methods are `async def` and must be called with `await`
- Wrapped in async context managers (`async with`)
- Same retry logic as sync clients

**Concurrency:**
- Ocean and Prospeo still called sequentially to respect rate limits
- Brevo calls run concurrently via `asyncio.gather(..., return_exceptions=True)`

#### EmailGenerator (`services/email_generator.py`)

**Personalizes email templates based on contact attributes.**

**Function:**
- `generate_email(contact: Contact, company_domain: str) -> Dict[str, str]`

**Returns:**
```python
{
    "subject": "Quick thought for John at Salesforce",
    "body": "Hi John,\n\nI noticed you're VP Sales at Salesforce..."
}
```

**Personalization Variables:**
- `{first_name}`: Contact.first_name
- `{title}`: Contact.title
- `{company_domain}`: Company domain
- Fallbacks to empty string if missing

#### Validation (`services/validation.py`)

**API response schema validators.**

**Functions:**
- `validate_ocean_company(data: Dict) -> Dict`: Validates company schema
- `validate_prospeo_contact(data: Dict) -> Dict`: Validates contact schema
- `validate_brevo_send(data: Dict) -> bool`: Validates email send response

**Behavior:**
- Raises `ValidationError` if required fields missing or wrong type
- Returns normalized data on success
- Used by API clients after parsing JSON

---

### Pipeline Module (`pipeline/outreach_pipeline.py`)

**Main orchestrator; coordinates all stages.**

**Key Methods:**

1. **`run(seed_domain, dry_run=False, limit=10, export_csv=True)`**
   - Synchronous execution
   - Stages 1-5 in sequence
   - Returns None; side effects: CSV export, metrics logging

2. **`run_async(seed_domain, dry_run=False, limit=10, export_csv=True)`**
   - Asynchronous execution
   - Async context managers for clients
   - Same side effects as sync

3. **`_extract_email(email_field)`**
   - Normalizes email field (string, dict, list, None)
   - Called after each Prospeo API response

**Stage Responsibilities:**

| Stage | Input | Output | Side Effects |
|-------|-------|--------|--------------|
| 1 | Seed domain | Company list | Logs companies |
| 2 | Company list | Contact list | Logs contacts per domain |
| 3 | Contact list | Deduplicated with valid emails | Logs lead count |
| 4 | Leads | User confirmation | Prints summary table |
| 5 | Approved leads | Sent email count | CSV export, metrics |

**Error Handling:**
- Stage 1 failure: Returns empty list; pipeline continues
- Stage 2 API error per domain: Increments failed counter; continues
- Stage 3 no results: Exits gracefully
- Stage 5 email send failure: Increments failed counter; continues

**Metrics Tracking:**
```python
self.metrics = {
    "start_time": None,
    "companies_found": 0,
    "contacts_found": 0,
    "emails_resolved": 0,
    "emails_sent": 0,
    "failed": 0,
}
```

---

### Utils Module

#### Logger (`utils/logger.py`)

**Structured logging to file and console.**

**Configuration:**
- **File Handler:** `logs/outreach.log` (RotatingFileHandler, 5MB max, 3 backups)
- **Console Handler:** INFO level (excludes DEBUG logs)
- **Format:** `%(asctime)s [%(levelname)s] %(name)s: %(message)s`

**Usage:**
```python
from utils.logger import get_logger
logger = get_logger(__name__)
logger.info("Stage 1: Found %s companies", len(companies))
logger.warning("Rate limited, sleeping %s seconds", retry_after)
logger.error("API error: %s", error_message)
```

#### PII Logger (`utils/pii_logger.py`)

**Utility to redact sensitive data before logging.**

**Use Cases:**
- Mask email addresses: `user@example.com` → `u***@example.com`
- Mask API keys: `sk_live_xxxxx` → `sk_live_*****`
- Never log full email addresses in production

#### Retry (`utils/retry.py`)

**Exponential backoff retry decorator.**

**Decorator:** `@retry_on_exceptions(max_retries=3, base_delay=1)`

**Behavior:**
- Retries on: `requests.exceptions.RequestException`, `requests.Timeout`, `APIError`
- Delays: 1s, 2s, 4s (exponential backoff)
- Logs each retry attempt with delay
- Raises exception after max retries exhausted

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ main.py (CLI Entry)                                         │
│ - Parse arguments (domain, --dry-run, --async-run)          │
│ - Load .env                                                 │
│ - Create Settings (validates)                               │
│ - Create OutreachPipeline                                   │
│ - Call pipeline.run() or pipeline.run_async()               │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ OutreachPipeline.run(seed_domain="salesforce.com")          │
└─────────────────────────────────────────────────────────────┘
        │
        ├─▶ Stage 1: ocean.find_similar(seed_domain, limit=10)
        │   ├─ Request: GET /api/v1/companies/similar?...
        │   ├─ Response: [Company, Company, ...] (10 companies)
        │   └─ Metrics: companies_found = 10
        │
        ├─▶ Stage 2: for company in companies: prospeo.find_contacts(company.domain)
        │   ├─ Request: GET /api/v3/people?domain=salesforce.com
        │   ├─ Response: [Contact, Contact, ...] (~5 contacts per domain)
        │   ├─ sleep(2)  # rate limit
        │   └─ Metrics: contacts_found = ~50
        │
        ├─▶ Stage 3: filter contacts with _extract_email()
        │   ├─ Normalize email field (dict/list/str → str)
        │   ├─ Filter: contact.email not None
        │   ├─ Deduplicate: by lowercase email
        │   └─ Metrics: emails_resolved = ~45
        │
        ├─▶ Stage 4: Safety checkpoint
        │   ├─ Print summary table (companies, contacts, emails)
        │   ├─ Prompt: "Proceed with sending emails? (y/n):"
        │   └─ User responds
        │
        └─▶ Stage 5: for lead in leads: brevo.send_email(...)
            ├─ Request: POST /v3/smtp/email
            ├─ Response: {"messageId": 12345}
            ├─ Metrics: emails_sent += 1 (or failed += 1)
            ├─ CSV Export: writes leads.csv with all contacts
            └─ Return: metrics summary
```

---

## Error Handling Strategy

### Validation Layer

**Where:** API client response → Validation → Pipeline

**Logic:**
1. API client gets HTTP response
2. BaseClient parses JSON
3. Validation function schema-checks
4. On error: Raise ValidationError (caught by pipeline)
5. On success: Return normalized data

### Retry Layer

**Where:** HTTP request level (BaseClient)

**Logic:**
1. Request fails (timeout, 5xx, etc.)
2. @retry_on_exceptions() sleeps and retries
3. On success: Continue
4. On max retries: Raise APIError (caught by pipeline)

### Graceful Degradation

**Where:** Pipeline level

**Logic:**
- **Stage 1-2 per-domain failure:** Log warning, increment failed counter, continue with next domain
- **Stage 3 no results:** Log warning, exit gracefully with summary
- **Stage 5 email send failure:** Log error, increment failed counter, continue with next email
- **Rate limit (429):** Automatic sleep + retry (handled by BaseClient)

### No Silent Failures

**Principle:** Never silently drop data. Always:
1. Log the failure (with context)
2. Increment a failure counter
3. Continue processing remaining items
4. Report summary at the end

---

## Concurrency & Async Design

### Sync Mode (`pipeline.run()`)

```
Domain → Ocean → Prospeo (sequential, 2s delays) → Brevo (sequential) → CSV
```

**Characteristics:**
- Simpler to understand and debug
- Suitable for small runs (1-10 domains)
- ~72 seconds for typical run

### Async Mode (`pipeline.run_async()`)

```
Domain → Ocean → Prospeo (sequential, 2s delays) → Brevo (concurrent) → CSV
```

**Characteristics:**
- Ocean & Prospeo still sequential (rate limit respect)
- Brevo calls concurrent: `asyncio.gather(*tasks, return_exceptions=True)`
- Suitable for large runs (50+ domains, 500+ contacts)
- ~27 seconds for same typical run (63% faster)

**Why Not Fully Concurrent?**
- Prospeo rate limit (30-60 requests/min) enforced by 2s delay
- Even with async, delay is present; true concurrency won't help

**Exception Handling in Async:**
- `return_exceptions=True`: Capture exceptions as results
- Count successes separately: `sum(1 for r in results if r is True)`
- Log failures for debugging

---

## Configuration & Secrets Management

### Secrets (`.env` file)

**Never version-controlled.** Contains:
```
OCEAN_API_KEY=sk_...
PROSPEO_API_KEY=pk_...
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=sender@domain.com
```

**Validation:**
- Settings class loads at startup
- Raises error if any key missing or invalid
- No partial runs with invalid config

### Environment Variable Overrides

**Supported Aliases:**
- `OCEAN_API_KEY` or `OCEAN_API_TOKEN` (backwards compatibility)
- `OCEAN_BASE_URL`, `PROSPEO_BASE_URL`, `BREVO_BASE_URL` (optional, with defaults)

---

## Testability & Mocking

### Dependency Injection in OutreachPipeline

```python
def __init__(self, settings: Settings, ocean=None, prospeo=None, brevo=None):
    self.ocean = ocean or OceanClient(...)
    self.prospeo = prospeo or ProspeoClient(...)
    self.brevo = brevo or BrevoClient(...)
```

**Benefits:**
- Pass mock clients for testing
- No API calls in tests
- Fast test execution

### Example Test

```python
def test_run_with_mocked_clients(monkeypatch):
    mock_ocean = MagicMock()
    mock_ocean.find_similar.return_value = [
        Company("salesforce.com", "Salesforce"),
        Company("hubspot.com", "HubSpot"),
    ]
    
    pipeline = OutreachPipeline(settings, ocean=mock_ocean)
    pipeline.run("github.com", dry_run=True)
    
    assert pipeline.metrics["companies_found"] == 2
    mock_ocean.find_similar.assert_called_once_with("github.com", limit=10)
```

---

## Performance Considerations

### Memory Usage

- **Sync Mode:** ~1MB per 100 contacts
- **Async Mode:** Slightly higher (maintains TCP connections)
- **Typical Run:** < 100MB total

### Network Latency

- **Ocean.io:** 1-2 seconds per request
- **Prospeo:** 1-2 seconds per domain request
- **Brevo:** 100-500ms per email (highly variable)
- **Sync Bottleneck:** Sequential Brevo calls (50ms × 50 emails = 2.5s)
- **Async Benefit:** Concurrent Brevo calls (50ms × 50 emails = 500ms parallelized)

### CPU Usage

- Email generation (regex for first_name): Negligible
- CSV writing: Negligible for < 10k rows
- Overall: CPU not a bottleneck

---

## Future Architecture Improvements

1. **Job Queue System:** Celery + Redis for distributed multi-domain campaigns
2. **Database Persistence:** PostgreSQL for audit trail and historical analytics
3. **Event Streaming:** Kafka/RabbitMQ for pipeline events (stage start/end, failures)
4. **Monitoring & Alerting:** Prometheus metrics + Grafana dashboards
5. **API Rate Limit Management:** Shared rate limit state across instances
6. **Template Management:** Database-backed templates instead of hardcoded strings
