# Real API Status Report

## Ocean.io

- Authentication status: Not fully verified.
  - A live request to `https://api.ocean.io/v3/search/companies` returned `403 Forbidden`.
  - Response message: `Current API token is not registered in our database`.
- Endpoint status: reachable, but authentication failed.
- Search results: none returned due auth failure.
- Validation:
  - Request URL: `https://api.ocean.io/v3/search/companies`
  - Payload structure: `{"size":10,"companiesFilters":{"lookalikeDomains":["salesforce.com"]}}`
  - Header validation: `X-Api-Token` is used correctly by the Ocean client.

## Prospeo

- Authentication status: Not validated in the current environment.
  - The default `PROSPEO_BASE_URL` is `https://api.prospeo.example`, which is a placeholder.
- Contact results: none verified.
- Email results: none verified.
- Notes:
  - The validation test will skip unless `PROSPEO_API_KEY` and `PROSPEO_BASE_URL` are set to real values.
  - Current code uses `GET /v1/search/contacts?domain=salesforce.com` with Bearer auth.

## Brevo

- Authentication status: client bug fixed.
  - Fixed Brevo sync and async clients to use `api-key` instead of `Authorization: Bearer`.
- Sender verification: not yet validated with real credentials.
- Account access: not verified.

## Pipeline

- End-to-end status: not completed in the current environment.
  - The pipeline reaches Stage 1 and fails at Ocean authentication with `403 Forbidden`.
- Remaining blockers:
  1. Provide a valid `OCEAN_API_TOKEN` / `OCEAN_API_KEY`.
  2. Provide a real `PROSPEO_API_KEY` and `PROSPEO_BASE_URL`.
  3. Provide a real `BREVO_API_KEY` and `BREVO_SENDER_EMAIL`.

## Summary

- Code is prepared for live API validation with the new connection tests.
- The only confirmed integration bug fixed is Brevo auth header handling.
- The current environment still needs valid credentials and real provider endpoints for full end-to-end validation.
