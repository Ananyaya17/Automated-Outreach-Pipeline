# Workflow Documentation

This document describes the end-to-end data flow, decision points, and data transformations at each stage of the pipeline.

---

## High-Level Stages

```
Stage 1: Company Discovery → Stage 2: Contact Finding → Stage 3: Email Validation 
→ Stage 4: Safety Checkpoint → Stage 5: Email Delivery → CSV Export
```

---

## Stage 1: Company Discovery (Ocean.io)

### Purpose
Find 10 firmographically similar companies based on a seed domain.

### Input
- **User Input:** Single company domain (e.g., `salesforce.com`)
- **Validation:** Domain must contain a dot, no spaces, no protocol
- **Fallback:** User re-enters domain if invalid

### Processing

1. **API Call**
   ```
   GET https://api.ocean.io/companies/similar?domain=salesforce.com&limit=10
   Headers: Authorization: Bearer {OCEAN_API_KEY}
   ```

2. **Response Parsing**
   ```json
   {
     "data": [
       {
         "website": "hubspot.com",
         "name": "HubSpot",
         "industry": "Software"
       },
       ...
     ]
   }
   ```

3. **Validation**
   - Check: `website` field present (or fallback to `domain`)
   - Check: `name` field present
   - Normalize: `domain.lower().strip()`
   - Create: `Company(domain, name)` object

4. **Error Handling**
   - **API Error (5xx):** Retry with exponential backoff (1s, 2s, 4s)
   - **Rate Limit (429):** Sleep for `Retry-After` header + retry
   - **Timeout:** Retry
   - **Invalid Response:** Log warning, return empty list

### Output
- **Success:** List of `Company` objects (typically 10)
- **Failure:** Empty list; pipeline continues with warning
- **Metrics:** `companies_found` counter incremented

### Example Output
```python
[
    Company(domain="hubspot.com", company_name="HubSpot"),
    Company(domain="marketo.com", company_name="Marketo"),
    Company(domain="pardot.com", company_name="Pardot"),
    # ... 7 more companies
]
```

### Side Effects
- **Logging:** `[INFO] Stage 1: Found 10 similar companies for seed salesforce.com`
- **Timing:** ~2 seconds

---

## Stage 2: Contact Finding (Prospeo)

### Purpose
Extract C-suite and VP-level decision makers from each company.

### Input
- **Upstream:** List of `Company` objects from Stage 1
- **Iteration:** Process each company domain sequentially

### Processing Per Domain

1. **API Call**
   ```
   GET https://api.prospeo.io/api/v3/people?domain=hubspot.com
   Headers: Authorization: Bearer {PROSPEO_API_KEY}
   ```

2. **Response Parsing**
   ```json
   {
     "data": [
       {
         "name": "John Smith",
         "title": "VP Sales",
         "email": "john@hubspot.com",
         "linkedin": "https://www.linkedin.com/in/john-smith"
       },
       {
         "name": "Jane Doe",
         "title": "VP Marketing",
         "email": {
           "email": "jane@hubspot.com"
         },
         "linkedin": "https://www.linkedin.com/in/jane-doe"
       },
       # ... more contacts, some with missing emails
     ]
   }
   ```

3. **Per-Contact Validation**
   - Check: `name` present and valid
   - Check: `title` present (may be empty string, that's OK)
   - Extract: `email` (see Stage 3 for normalization)
   - Extract: `linkedin` URL
   - Create: `Contact(name, title, linkedin, email, company_domain)`

4. **Rate Limiting**
   - After each domain: `sleep(2)` (ensures 30 requests/min max)
   - Hardcoded delay (not from API response)
   - Respects API terms of service

5. **Error Handling**
   - **Per-Domain API Error:** Log error, increment `failed` counter, continue to next domain
   - **Timeout:** Retry (same retry logic)
   - **Invalid Response Type:** Log warning, treat as empty list for that domain
   - **No Contacts for Domain:** Log info, continue (empty result OK)

### Output
- **Success:** Accumulated list of `Contact` objects across all domains
- **Typical:** 5-10 contacts per domain × 10 domains = 50-100 contacts total
- **Metrics:** `contacts_found` counter incremented

### Example Output
```python
[
    Contact("John Smith", "VP Sales", "https://...", "john@hubspot.com", "hubspot.com"),
    Contact("Jane Doe", "VP Marketing", "https://...", {"email": "jane@hubspot.com"}, "hubspot.com"),
    Contact("Bob Johnson", "CEO", "https://...", None, "hubspot.com"),
    # ... 47 more contacts from other domains
]
```

### Side Effects
- **Logging per domain:** `[INFO] [hubspot.com] -> 5 contacts, 4 with email`
- **Logging summary:** `[INFO] Stage 2: Completed 10 API calls, returned 47 contacts`
- **Timing:** ~20 seconds (10 domains × 2s delay)

### Data Quality Notes
- **Email Field Inconsistency:** Prospeo returns email as string, dict, or list (see Stage 3)
- **Missing Titles:** Some contacts may have empty title (OK, logged)
- **Duplicate People:** Same person may appear in multiple domain searches (dedup in Stage 3)
- **Missing LinkedIn:** Some contacts have no LinkedIn URL (OK, not required)

---

## Stage 3: Email Validation & Deduplication

### Purpose
Normalize email fields, filter out contacts without valid emails, and deduplicate by email.

### Input
- **Upstream:** List of `Contact` objects from Stage 2

### Processing

1. **Email Field Normalization**
   
   The `_extract_email()` method handles various email shapes:
   
   | Input Shape | Example | Output |
   |------------|---------|--------|
   | String | `"john@hubspot.com"` | `"john@hubspot.com"` |
   | Dict | `{"email": "john@hubspot.com"}` | `"john@hubspot.com"` |
   | Dict (alt) | `{"emailAddress": "john@hubspot.com"}` | `"john@hubspot.com"` |
   | List | `["john@hubspot.com", "john.doe@hubspot.com"]` | `"john@hubspot.com"` (first) |
   | None | `None` | `None` |
   | Invalid | `123` (number) | `None` |

   **Algorithm:**
   ```python
   def _extract_email(email_field):
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

2. **Email Filtering**
   
   ```python
   leads = [contact for contact in contacts 
            if _extract_email(contact.email)]
   ```
   
   **Result:** Removes contacts with `email=None`

3. **Deduplication by Lowercase Email**
   
   ```python
   unique = {}
   for c in leads:
       e = _extract_email(c.email)
       if not e:
           continue
       unique[e.lower()] = c  # Last occurrence wins
   leads = list(unique.values())
   ```
   
   **Why Lowercase?** Email addresses are case-insensitive (user@domain = USER@DOMAIN)
   
   **Last Occurrence Wins:** If same person appears twice, later record overwrites (may have better data)

### Output
- **Success:** Deduplicated list of `Contact` objects with valid emails
- **Typical:** 40-50 leads from 100 contacts (40-50% have valid emails)
- **Metrics:** `emails_resolved` counter incremented

### Example Output
```python
[
    Contact("John Smith", "VP Sales", "https://...", "john@hubspot.com", "hubspot.com"),
    Contact("Jane Doe", "VP Marketing", "https://...", "jane@hubspot.com", "hubspot.com"),
    Contact("Alice Chen", "CFO", "https://...", "alice@hubspot.com", "hubspot.com"),
    # ... 47 more unique contacts
]
```

### Side Effects
- **Logging:** `[INFO] Stage 3: Leads after email filter = 48`
- **Logging warning (if all contacts missing email):** `[WARNING] Stage 2 returned no contacts for any domain`
- **Timing:** < 1 second (CPU only, no I/O)

### Early Exit
- **If `leads` is empty:** Pipeline exits gracefully with summary; no Stage 4-5
- **Message:** "No valid leads found, skipping email send and CSV export."

---

## Stage 4: Safety Checkpoint

### Purpose
Human review and approval before sending live emails.

### Input
- **Upstream:** List of `Contact` objects from Stage 3

### Processing

1. **Summary Report**
   
   Printed as formatted table:
   ```
   ┏━━━━━━━━━━━━━┳━━━━━━━┓
   ┃ Metric      ┃ Value ┃
   ┡━━━━━━━━━━━━━╇━━━━━━━┩
   │ Total Companies │ 10  │
   │ Total Contacts  │ 47  │
   │ Total Emails    │ 48  │
   └─────────────────────┘
   ```

2. **User Confirmation (Sync Mode Only)**
   
   - **Dry Run (`--dry-run`):** Automatic approval (no prompt)
   - **Live Run:** Interactive prompt
     ```
     Proceed with sending emails? (y/n): _
     ```
   - **User Enters:** `y` or `n`

3. **Decision Logic**
   
   ```python
   if dry_run:
       proceed = True  # Skip confirmation
   else:
       resp = console.input("Proceed with sending emails? (y/n): ").strip().lower()
       proceed = (resp == "y")
   ```

### Output
- **Success:** Proceed to Stage 5
- **Abort:** Exit pipeline gracefully; no emails sent, no CSV export
- **Dry Run:** Always proceeds (Stage 5 marked as `[dry-run]`)

### Side Effects
- **Logging:** Checkpoint decision logged
- **Timing:** ~5 seconds (human decision)

---

## Stage 5: Email Delivery (Brevo)

### Purpose
Send personalized outreach emails to all approved leads.

### Input
- **Upstream:** List of approved `Contact` objects from Stage 4
- **User Decision:** Approval to proceed (from Stage 4)
- **Flag:** `dry_run` (if True, emails not actually sent)

### Processing Per Contact

1. **Email Generation**
   
   ```python
   template = generate_email(lead, lead.company_domain)
   # Returns: {"subject": "...", "body": "..."}
   ```
   
   **Personalization Variables:**
   - `{first_name}`: `lead.first_name` (e.g., "John")
   - `{title}`: `lead.title` (e.g., "VP Sales")
   - `{company_domain}`: `lead.company_domain` (e.g., "hubspot.com")
   
   **Example Generated Email:**
   ```
   Subject: Quick thought for John at HubSpot
   
   Body:
   Hi John,
   
   I noticed you're VP Sales at hubspot.com and have built an impressive...
   ```

2. **Dry Run Branch**
   
   ```python
   if dry_run:
       console.print("[dry-run] Would send to user@***.***")
       ok = True
   ```
   
   **Side Effect:** Prints to console (email not sent)

3. **Live Send**
   
   ```python
   ok = brevo.send_email(
       from_addr=self.settings.BREVO_SENDER_EMAIL,
       to_addr=lead.email,
       subject=template["subject"],
       body=template["body"]
   )
   ```
   
   **API Call:**
   ```
   POST https://api.brevo.com/v3/smtp/email
   Headers: Authorization: Bearer {BREVO_API_KEY}
   Body: {
     "sender": {"email": "sender@company.com"},
     "to": [{"email": "prospect@prospect.com"}],
     "subject": "...",
     "htmlContent": "..."
   }
   ```

4. **Response Handling**
   
   - **Success (messageId present):** `ok = True`; increment `emails_sent`
   - **Failure (error dict returned):** `ok = False`; increment `failed`
   - **Invalid Schema:** Raise `APIError`; increment `failed`

5. **Error Handling**
   
   - **Per-Email Send Failure:** Log error, continue to next email
   - **Brevo API Error (5xx):** Retry (handled by BaseClient)
   - **Rate Limit (429):** Retry (handled by BaseClient)
   - **Timeout:** Retry
   - **Total Failure:** After max retries, count as failure; continue

### Async Mode Differences

**Sync Mode:** Process contacts sequentially
```python
for lead in leads:
    ok = brevo.send_email(...)
    if ok: successes += 1
    else: failed += 1
```

**Async Mode:** Process concurrently
```python
tasks = [
    abrevo.send_email(...) 
    for lead in leads
]
results = await asyncio.gather(*tasks, return_exceptions=True)
successes = sum(1 for r in results if r is True)
failed = len(results) - successes
```

**Performance:**
- Sync: 50 emails × 1s each = 50s
- Async: 50 emails concurrently = 5s (10x faster)

### Output
- **Metrics:** `emails_sent` and `failed` counters updated
- **CSV Export:** (see below)
- **Summary:** Printed to console

### Side Effects
- **Logging per success:** `[INFO] Email sent to john@hubspot.com`
- **Logging per failure:** `[ERROR] Email send failed: john@hubspot.com - reason`
- **Timing:** 50 seconds (sync), 5 seconds (async)

---

## CSV Export

### Purpose
Audit trail and CRM integration.

### Input
- **Upstream:** List of sent `Contact` objects from Stage 5

### Processing

1. **Filter Valid Rows**
   
   ```python
   valid_lead_rows = [
       l for l in leads 
       if l.full_name or l.email
   ]
   ```
   
   Ensures at least name or email present.

2. **File Creation**
   
   ```
   exports/leads.csv
   ```
   
   **Directory Creation:** Auto-creates `exports/` folder if missing

3. **CSV Writing**
   
   ```python
   writer.writerow([
       "company_domain",
       "contact_name",
       "title",
       "linkedin_url",
       "email"
   ])
   
   for l in valid_lead_rows:
       writer.writerow([
           l.company_domain,
           l.full_name,
           l.title,
           str(l.linkedin_url) if l.linkedin_url else "",
           l.email or ""
       ])
   ```

### Output Example

```csv
company_domain,contact_name,title,linkedin_url,email
hubspot.com,John Smith,VP Sales,https://www.linkedin.com/in/john-smith,john@hubspot.com
hubspot.com,Jane Doe,VP Marketing,https://www.linkedin.com/in/jane-doe,jane@hubspot.com
marketo.com,Bob Johnson,CEO,https://www.linkedin.com/in/bob-johnson,bob@marketo.com
```

### Side Effects
- **Logging:** `[INFO] Exported 48 leads to exports/leads.csv`
- **File Encoding:** UTF-8 (supports special characters)

---

## Final Summary & Metrics

### Metrics Summary

```
┌────────────────────────────────────────────────┐
│ Emails sent: 48, failed: 0                     │
│ Total failures: 2                              │
│ Execution time: 127.45s                        │
└────────────────────────────────────────────────┘
```

### Metric Breakdown

| Metric | Definition | Example |
|--------|-----------|---------|
| `companies_found` | Stage 1 result count | 10 |
| `contacts_found` | Stage 2 result count (before dedup) | 47 |
| `emails_resolved` | Stage 3 result count (dedup + valid) | 48 |
| `emails_sent` | Stage 5 success count | 48 |
| `failed` | Total failure count across all stages | 2 |
| Execution time | Total pipeline duration | 127.45s |

---

## Error Recovery Strategies

### Per-Domain Prospeo Failure
- **What Happens:** Domain returns error or timeout
- **Recovery:** Logged, failed counter incremented, pipeline continues to next domain
- **Impact:** Loss of contacts from that one domain only

### Email Send Failure
- **What Happens:** Brevo returns error or timeout
- **Recovery:** Logged, failed counter incremented, CSV still contains contact info for retry
- **Impact:** Email not sent, but contact data preserved

### Network Timeout
- **What Happens:** Connection hangs > 20 seconds
- **Recovery:** Automatic retry (up to 3 times) with exponential backoff
- **Impact:** Minimal, transparent to user

### Rate Limit (429)
- **What Happens:** API says "too many requests"
- **Recovery:** Automatic sleep for `Retry-After` duration + retry
- **Impact:** Minimal, pipeline slows down slightly

### No Valid Leads
- **What Happens:** After Stage 3, zero contacts with valid emails
- **Recovery:** Pipeline exits gracefully, no Stage 4-5
- **Impact:** User sees warning and can debug API issues

---

## Troubleshooting Guide

### Pipeline Hangs on Stage 2
- **Cause:** Prospeo rate limit causing repeated retries
- **Diagnosis:** Check logs for `Rate limited, sleeping` messages
- **Fix:** Upgrade Prospeo plan or increase sleep duration (contact support)

### High Failure Rate in Stage 5
- **Cause 1:** `BREVO_SENDER_EMAIL` not verified
- **Diagnosis:** See error logs; Brevo will return "sender not verified"
- **Fix:** Verify email in Brevo dashboard

- **Cause 2:** API key invalid or expired
- **Diagnosis:** Check `.env` file; logs show `Authorization failed`
- **Fix:** Regenerate API key in service dashboard

### No Contacts Found in Stage 2
- **Cause 1:** Company domain not recognized by Prospeo
- **Diagnosis:** Check logs; warning logged per domain
- **Fix:** Try different company domains

- **Cause 2:** API plan doesn't include required data
- **Diagnosis:** API returns `{"error": "insufficient credits"}`
- **Fix:** Upgrade plan

### CSV Export Encoding Issues
- **Cause:** Non-ASCII characters (é, ü, 中文) in contact names
- **Diagnosis:** CSV file corrupted or unreadable
- **Fix:** Already fixed in code; ensure `encoding="utf-8"` in CSV writer

---

## Validation Rules Summary

| Field | Validation | Error Handling |
|-------|-----------|----------------|
| Domain (Stage 1 input) | Must contain dot, no spaces | User re-enters |
| Company domain (Ocean) | Must not be empty | Logged, skipped |
| Contact name (Prospeo) | Must not be empty | Logged, skipped |
| Contact email | Any shape (str/dict/list) | Normalized; if None, filtered |
| Sender email (Brevo) | Must be valid format | Validated at startup |
| API key | Must not be empty | Validated at startup |

