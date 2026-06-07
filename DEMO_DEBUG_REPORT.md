# Demo Mode Debug Report

## Root cause

The demo-mode failure was caused by CLI flag parsing in `main.py`. The Typer boolean options were defined with `is_flag=True` but without `flag_value=True`, which caused the `--demo-mode` flag to be parsed as `None` in this environment. As a result, the demo branch in `main.py` was never taken and the production async clients were used instead.

## File responsible

- `main.py`
- `pipeline/outreach_pipeline.py` (debug instrumentation only)

## Fix applied

- Updated `main.py` boolean flag options to include `flag_value=True` for:
  - `--dry-run`
  - `--async-run`
  - `--demo-mode`
- Added temporary debug output to `pipeline/outreach_pipeline.py` in the async run path to report:
  - retrieved companies
  - retrieved contacts
  - filtered leads
  - runtime object types for sanity checking

## Final successful output

Demo mode now runs correctly and returns non-zero metrics.

Example output:

```
Demo mode enabled: running fallback pipeline with sample data
Running demo dry-run (async) with sample JSON data
────────────────────────── Stage 1 (async): Find similar companies ───────────────────────────
DEBUG_COMPANIES: [Company(domain='example.com', company_name='Example Corp'), Company(domain='acme.com', company_name='Acme Inc'), Company(domain='widget.co', company_name='Widget Co')]
DEBUG_COMPANIES_TYPES: ['Company', 'Company', 'Company']
COMPANY_COUNT: 3
Found 3 similar companies
─────────────────────────── Stage 2 (async): Find decision makers ────────────────────────────
DEBUG_CONTACTS: [Contact(full_name='Alice Smith', title='CEO', linkedin_url='https://linkedin.com/in/alicesmith', email='alice@example.com', company_domain='example.com'), Contact(full_name='Bob Johnson', title='CTO', linkedin_url='https://linkedin.com/in/bobjohnson', email='bob@acme.com', company_domain='acme.com'), Contact(full_name='Cara Lee', title='VP Product', linkedin_url='https://linkedin.com/in/caralee', email='cara@widget.co', company_domain='widget.co')]
DEBUG_CONTACTS_TYPES: ['Contact', 'Contact', 'Contact']
CONTACT_COUNT: 3
──────────────────────── Stage 3 (async): Filter contacts with email ──────────────────
DEBUG_LEADS: [Contact(full_name='Alice Smith', title='CEO', linkedin_url='https://linkedin.com/in/alicesmith', email='alice@example.com', company_domain='example.com'), Contact(full_name='Bob Johnson', title='CTO', linkedin_url='https://linkedin.com/in/bobjohnson', email='bob@acme.com', company_domain='acme.com'), Contact(full_name='Cara Lee', title='VP Product', linkedin_url='https://linkedin.com/in/caralee', email='cara@widget.co', company_domain='widget.co')]
DEBUG_LEADS_TYPES: ['Contact', 'Contact', 'Contact']
LEAD_COUNT: 3
───────────────────────────────── Stage 4: Safety checkpoint ─────────────────────────────────
          Summary          
┏━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric          ┃ Value ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total Companies │ 3     │
│ Total Contacts  │ 3     │
│ Total Emails    │ 3     │
└─────────────────┴───────┘
──────────────────────────── Stage 5 (async): Send emails (Brevo) ────────────────────────────
 Would send to user@***.***
 Would send to user@***.***
 Would send to user@***.***
Exported leads to exports\leads.csv
────────────────────────────────────────── Summary ───────────────────────────────────────────
Emails sent: 0, failed: 0
Total failures: 0
Execution time: 0.03s
```
