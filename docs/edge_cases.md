# Edge Cases & Error Handling

This document details edge cases the pipeline handles and the recovery strategies employed.

---

## Data Quality Edge Cases

### 1. Malformed Domain Input

**Scenario:**
```
User input: "example" (missing TLD)
User input: "https://example.com" (includes protocol)
User input: "example .com" (contains space)
```

**Detection:**
```python
# In Company.__post_init__
if not self.domain or " " in self.domain or "." not in self.domain:
    raise ValueError("Invalid domain")
```

**Handling:**
- Raises `ValueError` immediately
- Caught by CLI error handler
- User sees: `Error: Invalid domain`
- **Recovery:** User is prompted to re-enter domain

**Code Path:**
```
main.py → Pipeline.run(domain) → Company(domain) → __post_init__ raises ValueError
```

---

### 2. Email Field Format Inconsistency

**Scenario:**
Prospeo returns email in different shapes for different contacts:

```json
{
  "contact1": {
    "email": "john@company.com"
  },
  "contact2": {
    "email": {
      "email": "jane@company.com"
    }
  },
  "contact3": {
    "email": ["alice@company.com", "alice.brown@company.com"]
  },
  "contact4": {
    "email": null
  },
  "contact5": {
    "email": 123
  }
}
```

**Detection:**
```python
# In OutreachPipeline._extract_email()
def _extract_email(self, email_field):
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
```

**Handling:**
| Input | Output | Notes |
|-------|--------|-------|
| `"john@company.com"` | `"john@company.com"` | String: returned as-is |
| `{"email": "jane@company.com"}` | `"jane@company.com"` | Dict: extract from `email` key |
| `["alice@company.com", "alice.brown@..."]` | `"alice@company.com"` | List: take first valid |
| `None` | `None` | Null: return None |
| `123` | `None` | Invalid type: return None |

**Recovery:**
- All shapes normalized to string or None
- Contacts with None are filtered in Stage 3
- **User Impact:** Transparent; no errors

---

### 3. Duplicate Contacts Across Domains

**Scenario:**
Same person appears in multiple domain searches:
```
Domain A: John Smith (VP Sales) → john@company.com
Domain B: John Smith (VP Sales) → john@company.com
Domain C: John Smith (VP Sales) → john@company.com
```

**Detection:**
```python
# In OutreachPipeline.run() Stage 3
unique = {}
for c in leads:
    e = self._extract_email(c.email)
    if not e:
        continue
    unique[e.lower()] = c  # Lowercase key ensures case-insensitivity
leads = list(unique.values())
```

**Handling:**
- Email normalized to lowercase: `john@company.com` → `john@company.com`
- Key collision: later occurrence overwrites
- Result: 1 John Smith in final list (not 3)

**Why This Matters:**
- Prevents duplicate outreach (save email quota)
- Prevents multiple same emails in CSV
- Prevents user confusion

**Recovery:**
- Automatic deduplication
- Last occurrence wins (may have better/fresher data)
- No user action required

---

### 4. Missing Required Contact Fields

**Scenario:**
```json
{
  "contact1": {
    "name": "John Smith",
    "title": ""
  },
  "contact2": {
    "name": "",
    "title": "VP Sales"
  },
  "contact3": {
    "name": null,
    "title": null
  }
}
```

**Detection:**
```python
# In Validation.validate_prospeo_contact()
name = data.get("name") or data.get("full_name", "")
title = data.get("title", "")

if not name or not isinstance(name, str):
    raise ValidationError(f"Invalid name in contact record: {data}")
```

**Handling:**
| Case | Handling | Impact |
|------|----------|--------|
| Empty title | Accepted; Contact created with title="" | OK, not required for email |
| Empty name | Rejected; Contact skipped | Contact lost |
| Null name | Rejected; Contact skipped | Contact lost |

**Recovery:**
- Contacts without names filtered out
- Contacts without titles still included (title not required for personalization)
- Email generator has fallback: `{title}` → empty string if missing

**Code Path:**
```
Prospeo response → Validation → Skip invalid → Pipeline continues
```

---

### 5. Special Characters in Contact Names

**Scenario:**
```
"José García"
"François Müller"
"李明"
"José (Joe) Smith"
```

**Detection:**
Handled transparently by Python 3 (native Unicode support).

**Handling:**
- CSV writer configured with `encoding="utf-8"`
- Special characters preserved in exports

**Recovery:**
- No errors; characters preserved
- If CSV opens in Excel: Select UTF-8 encoding on import

---

### 6. LinkedIn URL Format Variations

**Scenario:**
```json
{
  "linkedin": "https://www.linkedin.com/in/john-smith"
}
```

or

```json
{
  "linkedin": null
}
```

or

```json
{
  "linkedin": "john-smith"
}
```

**Detection:**
No validation on LinkedIn URL; accepted as-is.

**Handling:**
- Stored as string in Contact object
- Exported to CSV as-is
- Used for enrichment/research by user

**Recovery:**
- Optional field; no error if missing or malformed
- User can validate manually in CRM

---

## API Error Edge Cases

### 7. HTTP 429 - Rate Limit

**Scenario:**
```
API receives 31 requests in 1 minute
Prospeo rate limit: 30 requests/minute
Response: HTTP 429 Too Many Requests
Header: Retry-After: 60
```

**Detection:**
```python
# In BaseClient._handle_response()
if resp.status_code == 429:
    retry_after = int(resp.headers.get("Retry-After", "1"))
    logger.warning("Rate limited, sleeping %s", retry_after)
    time.sleep(retry_after)
    raise requests.exceptions.RequestException("Rate limited")
```

**Handling:**
1. Extract `Retry-After` header (sleep duration)
2. Sleep for specified duration
3. Raise exception to trigger retry logic (up to 3 retries)
4. On success: Continue pipeline

**Recovery:**
- Automatic retry with proper backoff
- Transparent to user (no error message)
- **Mitigation in pipeline:** Hardcoded 2-second delay between Prospeo requests prevents 429 in normal operation

---

### 8. HTTP 5xx - Server Error

**Scenario:**
```
Server error: HTTP 500 Internal Server Error
Server error: HTTP 502 Bad Gateway
Server error: HTTP 503 Service Unavailable
```

**Detection:**
```python
# In BaseClient._handle_response()
if not resp.ok:
    logger.error("API %s returned %s: %s", self.name, resp.status_code, resp.text)
    raise APIError(f"{self.name} API error: {resp.status_code}")
```

**Handling:**
```python
# In BaseClient._get() and _post() decorated with @retry_on_exceptions()
@retry_on_exceptions()  # max 3 retries with exponential backoff
def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    resp = self.session.get(url, params=params, timeout=20)
    return self._handle_response(resp)
```

**Retry Delays:**
- Attempt 1: Immediate
- Attempt 2: After 1 second
- Attempt 3: After 2 seconds
- Attempt 4: After 4 seconds (fails if all 3 retries exhausted)

**Recovery:**
- Automatic retry with exponential backoff
- Transparent to user if succeeded on retry
- Logged error if all retries exhausted

**Impact:**
- **Per-Domain (Stage 2):** Domain skipped, failed counter incremented, continue to next domain
- **Per-Email (Stage 5):** Email skipped, failed counter incremented, continue to next email

---

### 9. HTTP 401/403 - Authentication Error

**Scenario:**
```
Invalid API key: HTTP 401 Unauthorized
API key expired: HTTP 403 Forbidden
```

**Detection:**
```python
# In BaseClient._handle_response()
if not resp.ok:
    logger.error("API %s returned %s: %s", self.name, resp.status_code, resp.text)
    raise APIError(f"{self.name} API error: {resp.status_code}")
```

**Handling:**
1. Raises `APIError` immediately (no retry)
2. Logged with full error details
3. Caught by pipeline error handler
4. **Pipeline stops** (cannot continue without valid auth)

**Recovery:**
- User must:
  1. Verify API key in `.env`
  2. Check if API key expired in service dashboard
  3. Regenerate key if necessary
  4. Update `.env` and restart pipeline

---

### 10. Network Timeout

**Scenario:**
```
Connection hangs > 20 seconds (configured timeout)
Network latency spike
Server not responding
```

**Detection:**
```python
# In BaseClient._get() and _post()
resp = self.session.get(url, params=params, timeout=20)
# timeout=20 triggers requests.Timeout if no response in 20s
```

**Handling:**
```python
@retry_on_exceptions()  # Retries on RequestException (includes Timeout)
def _get(self, path: str, params: Optional[Dict[str, Any]] = None):
    # ...timeout=20 raises Timeout if exceeded
    # @retry_on_exceptions catches and retries
```

**Recovery:**
- Automatic retry (up to 3 times)
- Exponential backoff (1s, 2s, 4s)
- Transparent if succeeded on retry

---

### 11. Invalid JSON Response

**Scenario:**
```
Server returns HTML error page instead of JSON
Server returns truncated response
```

**Detection:**
```python
# In BaseClient._handle_response()
try:
    return resp.json()
except ValueError:
    raise APIError("Invalid JSON response")
```

**Handling:**
- Raises `APIError` (not retried; indicates server issue)
- Logged with error message
- Caught by pipeline error handler

**Recovery:**
- **Per-Domain:** Skipped, failed counter incremented
- **Per-Email:** Skipped, failed counter incremented

---

## Pipeline Logic Edge Cases

### 12. Empty Results at Any Stage

**Scenario A: Stage 1 Returns Zero Companies**
```
Ocean API returns: {"data": []}
Result: companies_found = 0
```

**Handling:**
```python
console.print(f"Found {len(companies)} similar companies")  # 0
# Pipeline continues to Stage 2
# Stage 2 loop: for c in []: (no iterations)
# Result: zero contacts
```

**Recovery:**
- Pipeline continues with empty company list
- Stage 2 finds zero contacts
- Stage 3 filters zero leads
- **Output:** CSV with zero rows (just header)

**User Action:**
- Review logs; ensure seed domain is correct
- Try different seed domain

---

**Scenario B: Stage 2 Returns Zero Contacts**
```
All 10 companies processed; none return contacts
Result: contacts_found = 0
```

**Handling:**
```python
# In Stage 2
console.print(f"Stage 2: Completed {len(companies)} API calls, returned {len(contacts)} contacts")
logger.info("Stage 2 returned no contacts for any domain: %s", list(per_domain_counts.keys()))

# After Stage 2
if companies and len(contacts) == 0:
    console.print("[bold yellow]Warning:[/bold yellow] Stage 2 is returning empty results...")
```

**Recovery:**
- Warning logged
- Pipeline continues to Stage 3
- Stage 3 filters zero leads
- **Output:** CSV with zero rows

**User Action:**
- Check Prospeo API plan (may be insufficient)
- Try different seed domain
- Contact Prospeo support

---

**Scenario C: Stage 3 Filters All Contacts (No Valid Emails)**
```
After deduplication: 50 contacts, but 0 have valid emails
Result: leads = []
```

**Handling:**
```python
if not leads:
    console.print("No valid leads found, skipping email send and CSV export.")
    console.rule("Summary")
    console.print(f"Emails sent: 0, failed: 0")
    console.print(f"Total failures: {self.metrics['failed']}")
    total_time = time.time() - self.metrics["start_time"]
    console.print(f"Execution time: {total_time:.2f}s")
    logger.info("Pipeline finished: %s", self.metrics)
    return  # Exit early
```

**Recovery:**
- Pipeline exits gracefully
- No CSV exported
- User sees summary with 0 emails sent
- **User Action:** Review if Prospeo API plan includes email data

---

### 13. User Aborts at Stage 4 Checkpoint

**Scenario:**
```
Pipeline prompts: "Proceed with sending emails? (y/n):"
User types: "n"
```

**Handling:**
```python
resp = console.input("Proceed with sending emails? (y/n): ").strip().lower()
proceed = resp == "y"

if not proceed:
    console.print("Exiting without sending emails.")
    return  # Exit early
```

**Recovery:**
- No emails sent
- No CSV exported
- Pipeline exits cleanly
- **User Action:** Can re-run with `--dry-run` to review, or modify contacts manually

---

### 14. Partial Failure in Async Email Send

**Scenario:**
```
Async mode: Send 50 emails concurrently
Result: 48 succeed, 2 timeout/fail
```

**Handling:**
```python
tasks = [abrevo.send_email(...) for lead in leads]
results = await asyncio.gather(*tasks, return_exceptions=True)
successes = sum(1 for r in results if r is True)
failed = len(results) - successes
self.metrics["failed"] += failed
self.metrics["emails_sent"] = successes
```

**Recovery:**
- Successful emails counted
- Failed emails counted
- CSV exported with all contacts (even failed ones)
- **User Action:** Can manually retry failed emails from CSV

---

### 15. Task Cancellation (Ctrl+C)

**Scenario:**
```
User presses Ctrl+C during Stage 5
Partial results: 20 emails sent, 30 pending
```

**Handling:**
```python
# Python asyncio automatically cancels pending tasks on Ctrl+C
# KeyboardInterrupt raised; process exits
# Metrics logged before exit (partially)
```

**Recovery:**
- **Async Mode:** CSV exported for already-sent emails; pending tasks cancelled
- **Sync Mode:** CSV may not be exported (partial state)
- **User Action:** Re-run pipeline; dedup logic prevents re-sending already-sent emails

---

## Configuration Edge Cases

### 16. Missing API Key in .env

**Scenario:**
```
.env file:
OCEAN_API_KEY=
PROSPEO_API_KEY=pk_xxxxx
BREVO_API_KEY=xkeysib_xxxxx
```

**Detection:**
```python
# In Settings.__init__()
self.OCEAN_API_TOKEN = self._load_env("OCEAN_API_TOKEN", aliases=["OCEAN_API_KEY"])

# In _validate_required_settings()
missing = [name for name in ["OCEAN_API_TOKEN", "PROSPEO_API_KEY", ...] 
           if not getattr(self, name)]
if missing:
    raise ValueError(f"Missing required settings: {', '.join(missing)}")
```

**Handling:**
- Raises `ValueError` at startup
- Pipeline never starts
- User sees: `Error: Missing required settings: OCEAN_API_TOKEN`

**Recovery:**
- User must populate `.env` file with valid keys
- Restart pipeline

---

### 17. Invalid BREVO_SENDER_EMAIL Format

**Scenario:**
```
.env:
BREVO_SENDER_EMAIL=not-an-email
```

**Detection:**
```python
# In Settings._validate_required_settings()
if "@" not in self.BREVO_SENDER_EMAIL:
    raise ValueError("BREVO_SENDER_EMAIL must be a valid email address")
```

**Handling:**
- Raises `ValueError` at startup
- Pipeline never starts
- User sees: `Error: BREVO_SENDER_EMAIL must be a valid email address`

**Recovery:**
- User updates `.env` with valid email format
- Restart pipeline

---

### 18. Malformed PROSPEO_BASE_URL

**Scenario:**
```
.env:
PROSPEO_BASE_URL=https://app.prospeo.io  (legacy endpoint)
```

or

```
PROSPEO_BASE_URL=http://localhost:8000  (local test URL)
```

**Detection:**
```python
# In Settings._normalize_prospeo_base_url()
lower = self.PROSPEO_BASE_URL.lower()
if "app.prospeo.io" in lower or lower.endswith("/api"):
    logger.warning("Detected legacy or incorrect PROSPEO_BASE_URL '%s'; ...")
    self.PROSPEO_BASE_URL = PROSPEO_API_BASE_URL
```

**Handling:**
- Logs warning
- **Auto-corrects** to correct endpoint (`https://api.prospeo.io`)
- Pipeline continues (no error)

**User Impact:**
- Transparent; warning logged but no failure

**Recovery:**
- Automatic; no user action needed
- User can see correction in logs

---

## File System Edge Cases

### 19. Export Directory Missing

**Scenario:**
```
Pipeline tries to write to: exports/leads.csv
Directory: exports/ doesn't exist
```

**Detection:**
```python
# In OutreachPipeline.run() Stage 5
outp = Path("exports")
outp.mkdir(exist_ok=True)  # Create if missing
```

**Handling:**
- Auto-creates `exports/` directory
- Writes CSV file

**Recovery:**
- Transparent; directory created automatically

---

### 20. Permission Denied on File Write

**Scenario:**
```
exports/ directory exists but is read-only
Pipeline tries to write leads.csv
```

**Detection:**
```python
# Python raises PermissionError on file write
```

**Handling:**
- Exception propagates up
- Logged as error
- Pipeline crashes

**Recovery:**
- User must:
  1. Fix directory permissions: `chmod 755 exports`
  2. Restart pipeline

---

### 21. Disk Space Exhausted

**Scenario:**
```
Disk full; CSV write fails
```

**Detection:**
```python
# Python raises OSError: [Errno 28] No space left on device
```

**Handling:**
- Exception propagates up
- Logged as error
- Pipeline crashes

**Recovery:**
- User must:
  1. Free up disk space
  2. Restart pipeline

---

## Testing Edge Cases

### 22. Unit Test: Invalid Email Extraction

**Test Case:**
```python
def test_extract_email_various_formats():
    pipeline = OutreachPipeline(settings)
    
    assert pipeline._extract_email("john@example.com") == "john@example.com"
    assert pipeline._extract_email({"email": "jane@example.com"}) == "jane@example.com"
    assert pipeline._extract_email(["alice@example.com"]) == "alice@example.com"
    assert pipeline._extract_email(None) is None
    assert pipeline._extract_email(123) is None
    assert pipeline._extract_email({"email": None}) is None
```

**Expected:** All assertions pass

---

### 23. Integration Test: Mock Prospeo Timeout

**Test Case:**
```python
def test_prospeo_timeout_retry():
    mock_prospeo = MagicMock()
    mock_prospeo.find_contacts.side_effect = [
        requests.Timeout("Connection timeout"),
        requests.Timeout("Connection timeout"),
        [Contact(...), Contact(...)],  # Success on 3rd retry
    ]
    
    pipeline = OutreachPipeline(settings, prospeo=mock_prospeo)
    pipeline.run("example.com")
    
    assert pipeline.metrics["contacts_found"] == 2
    assert mock_prospeo.find_contacts.call_count == 3
```

**Expected:** Retry logic succeeds after timeouts

---

## Summary: Edge Case Categories

| Category | Count | Severity | Handling |
|----------|-------|----------|----------|
| Data Quality | 6 | Low | Validation + filtering |
| API Errors | 5 | Medium | Retry + error logging |
| Pipeline Logic | 5 | Medium | Graceful degradation |
| Configuration | 3 | High | Validation at startup |
| File System | 3 | Low | Auto-creation + error logging |
| Testing | 2 | Low | Unit + integration tests |
| **Total** | **24** | — | — |

