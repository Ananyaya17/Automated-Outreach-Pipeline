# Production Checklist for Outreach Pipeline

Use this checklist to verify the system is production-ready before full deployment.

## Pre-Deployment

- [ ] All API keys are configured in `.env` and verified valid
- [ ] `.env` is added to `.gitignore` (no credentials in version control)
- [ ] Placeholder base URLs are replaced with real provider endpoints
- [ ] HTTPS is enforced for all API endpoints
- [ ] All dependencies are pinned in `requirements.txt`
- [ ] Python 3.8+ is available (tested on Python 3.14)

## Core Functionality

### Sync Pipeline
- [ ] Dry-run mode works: `python main.py --dry-run` → Enter seed domain → Completes without errors
- [ ] Real execution works: `python main.py` → Enter seed domain → Completes to safety checkpoint
- [ ] Confirmation prompt blocks until user responds
- [ ] CSV export is created at `exports/leads.csv` with correct columns
- [ ] Metrics are printed to console (companies, contacts, emails sent, failures)
- [ ] Execution time is calculated and displayed

### Async Pipeline
- [ ] Dry-run async works: `python main.py --dry-run --async-run` → Completes without errors
- [ ] Real async execution works: `python main.py --async-run` → Prompts user before sending
- [ ] Async clients are properly closed (no hanging connections)
- [ ] CSV export is created with same schema as sync mode
- [ ] Metrics are identical in structure to sync mode

### API Integration
- [ ] Ocean API: Company lookup returns valid domain and name
- [ ] Prospeo API: Contact finding returns titles, LinkedIn URLs, and email addresses when available
- [ ] Brevo API: Email sending returns success or error status
- [ ] Rate limiting: Pipeline respects Retry-After headers and backs off

## Error Handling

- [ ] Invalid API keys are caught early with clear error message
- [ ] Network timeouts (>30s) are caught and logged
- [ ] Partial failures (e.g., 1 of 10 contacts fails) allow pipeline to continue
- [ ] Malformed responses are caught and logged with context
- [ ] No unhandled exceptions crash the pipeline
- [ ] All errors are logged to `logs/outreach.log`

## Logging & Monitoring

- [ ] Logs are written to `logs/outreach.log` (or configured path)
- [ ] Email addresses are masked as `user@***.***` in logs (no plain email exposure)
- [ ] Debug logs show API endpoints and parameters (without auth keys)
- [ ] Error logs include exception traceback
- [ ] Pipeline completion logs include final metrics
- [ ] Log file rotation is configured (optional: check logger.py)

## CSV Export

- [ ] CSV file is created at `exports/leads.csv`
- [ ] CSV has headers: `company_domain`, `contact_name`, `title`, `linkedin_url`, `email`
- [ ] All rows have matching column count
- [ ] Email addresses are included in the CSV
- [ ] No PII is exposed outside the CSV (only masked in logs/console)
- [ ] CSV can be imported into CRM or email service

## Concurrency & Performance

- [ ] Sync mode uses ThreadPoolExecutor without blocking the event loop
- [ ] Async mode uses asyncio.gather() to parallelize calls
- [ ] No deadlocks or race conditions occur
- [ ] Memory usage remains reasonable for 100+ contacts
- [ ] Execution time is logged

## Security

- [ ] API keys are never logged or printed to console
- [ ] No credentials are hardcoded in source files
- [ ] All HTTP requests use HTTPS (verify no http:// in code)
- [ ] Sensitive data (emails) is masked in logs
- [ ] `.env` is not committed (check `.gitignore`)
- [ ] No temporary files are left with PII

## Testing

- [ ] All tests pass: `pytest -q`
- [ ] Sync pipeline test passes
- [ ] Async pipeline test passes
- [ ] Email generation test passes
- [ ] Domain validation test passes
- [ ] No test dependencies on external APIs (all mocked)

## Dependency Injection (Testing Support)

- [ ] `OutreachPipeline` accepts optional client instances in constructor
- [ ] Tests can pass mock clients without monkeypatching modules
- [ ] Async clients support context managers (`async with`)
- [ ] Demo runner works with monkeypatched clients: `python demo_runner.py`

## Edge Cases

- [ ] Domain normalization works: `EXAMPLE.COM` → `example.com`
- [ ] Email deduplication works: duplicate emails are merged
- [ ] Empty contact lists are handled (pipeline continues)
- [ ] Rate limiting retries work and don't crash
- [ ] Very long execution (>1 hour) is logged correctly
- [ ] Unicode characters in names/titles are handled

## Documentation

- [ ] README.md is up-to-date with setup and usage instructions
- [ ] Architecture diagram is included or described
- [ ] API configuration section documents each provider
- [ ] Environment variables are documented with examples
- [ ] Troubleshooting section covers common issues
- [ ] Logging section explains PII masking strategy

## Deployment

- [ ] Code is committed to version control with clean history
- [ ] No secrets are in commit history (use git-secrets or similar)
- [ ] README is reviewed and complete
- [ ] Team is trained on dry-run vs. production mode
- [ ] On-call runbook is prepared for failures
- [ ] Monitoring/alerting is configured for error logs
- [ ] Rollback plan exists (previous version can be deployed)

## Post-Deployment Verification

- [ ] Dry-run on production API keys completes without sending emails
- [ ] Real execution on production sends test emails successfully
- [ ] CSV export contains expected leads
- [ ] Email delivery is confirmed in provider dashboard
- [ ] Logs are ingested into logging system (if applicable)
- [ ] Alerts are fired if pipeline fails

## Sign-Off

- [ ] Development team sign-off: _______________  Date: _______
- [ ] QA team sign-off: _______________  Date: _______
- [ ] Product/Business sign-off: _______________  Date: _______

---

## Notes

- This checklist is non-exhaustive. Adapt based on your team's standards.
- Use this as a gate before production deployment.
- Update this checklist as new features are added.
