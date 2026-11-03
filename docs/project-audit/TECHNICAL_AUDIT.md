# Technical Audit

## Architecture

The project is a small Python monolith:

- `app.py` provides CLI argument parsing.
- `social_media_agent/generator.py` builds provider requests, parses responses, and implements local fallback.
- `social_media_agent/web.py` handles Flask routes, form validation, and uploads.
- `social_media_agent/scheduler.py` validates schedules and runs periodic generation/output loops.
- `social_media_agent/templates/index.html` renders the web UI.
- `tests/test_phase1_regressions.py` contains standard-library `unittest` regression coverage.

This architecture remains appropriate for a local prototype. It does not provide durable background jobs or multi-user operation.

## Provider integration status

- **OpenAI:** Uses the current SDK `OpenAI` client and Chat Completions interface. Initialization and request failures are logged and fall back locally.
- **Hugging Face:** Uses HTTP requests with Bearer authentication, status checks, and response/error-payload handling. The configured model must be supported by the available inference service.
- **Cohere:** Uses the v2 Chat endpoint (`https://api.cohere.com/v2/chat`), Bearer authentication, user message payload, and JSON response format. The response parser reads text blocks from the v2 message.
- Provider behavior is covered with mocks. No live calls with credentials have been made, so credentials, account permissions, endpoint availability, and model compatibility remain unverified.

## Input and scheduling

The CLI and web app validate required topics and allowed choices. Interval/count parsing is shared in `scheduler.py`; the scheduler also guards its direct-call arguments. Web upload checks are extension-based and user-visible errors are rendered as status messages.

Remaining gaps:

- No automated Flask test-client coverage for form submission and uploads.
- `scheduled_output` is a filesystem path supplied by the user; deployment scenarios need explicit path constraints.
- Scheduled work runs in a daemon thread and is not durable, inspectable, or recoverable across restarts.

## Reliability and observability

Provider failures and API-level error responses are logged with fallback context. The app does not yet provide structured request/job identifiers, scheduler lifecycle logs, metrics, tracing, retries, or centralized error reporting.

## Security and deployment

- Flask debug mode is disabled and the development server binds to localhost.
- API keys are read from environment variables or `.env`; a dedicated secret-management and rotation process is not included.
- There is no authentication, authorization, CSRF protection, or rate limiting.
- Upload checks rely on filename extensions, not content type inspection, malware scanning, or size limits.
- No production WSGI deployment configuration, container image, CI/CD pipeline, or health/readiness endpoints are provided.

## Build and verification status

The Phase 1 regression suite runs with:

```bash
python -m unittest discover -s tests -v
```

The suite includes mocked provider success and failure cases, local fallback, and CLI/scheduler validation. Python compilation was also checked. Tests do not make real provider requests or exercise Flask routes. Live provider validation requires credentials and is outstanding.

## Overall technical assessment

Phase 1 addresses the identified SDK, auth-header, response-failure, and basic input-validation defects. The implementation is more testable, but production resilience and security remain incomplete. Treat the app as a local prototype until provider smoke tests, web route tests, and deployment safeguards are in place.
