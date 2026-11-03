# Technical Audit

## Architecture

The project is a small Python monolith:

- `app.py` provides CLI argument parsing.
- `social_media_agent/generator.py` builds provider requests, parses responses, and implements local fallback.
- `social_media_agent/web.py` handles Flask routes, form validation, and uploads.
- `social_media_agent/scheduler.py` validates schedules, persists job state in SQLite, exposes lifecycle operations, and runs periodic generation/output loops.
- `social_media_agent/templates/index.html` renders the web UI.
- `tests/test_phase1_regressions.py` contains standard-library `unittest` regression coverage.

This architecture remains appropriate for a local prototype. Job state is durable, but workers are in-process and are not coordinated across multiple processes.

## Provider integration status

- **OpenAI:** Uses the current SDK `OpenAI` client and Chat Completions interface. Initialization and request failures are logged and fall back locally.
- **Hugging Face:** Uses HTTP requests with Bearer authentication, status checks, and response/error-payload handling. The configured model must be supported by the available inference service.
- **Cohere:** Uses the v2 Chat endpoint (`https://api.cohere.com/v2/chat`), Bearer authentication, user message payload, and JSON response format. The response parser reads text blocks from the v2 message.
- Provider behavior is covered with mocks. No live calls with credentials have been made, so credentials, account permissions, endpoint availability, and model compatibility remain unverified.

## Input and scheduling

The CLI and web app validate required topics and allowed choices. Interval/count parsing is shared in `scheduler.py`; the scheduler also guards its direct-call arguments. Web uploads have a 5 MB cap, allowlisted extensions/signature checks, and user-visible validation errors.

Remaining gaps:

- `scheduled_output` is a filesystem path supplied by the user; deployment scenarios need explicit path constraints.
- Web scheduled workers run in daemon threads and stop with the web process. SQLite records remain; manual recovery and an opt-in CLI supervisor are available. `scripts/register-scheduler-supervisor.ps1` provides optional Windows current-user logon startup, but the task must be registered explicitly.
- Per-job SQLite leases prevent concurrent workers sharing one database; separate databases are not coordinated. Unexpected generator exceptions receive bounded retries.

## Reliability and observability

Provider failures and API-level error responses are logged with fallback context. Web requests and scheduler lifecycle events also emit JSON records containing request/job IDs and non-sensitive status fields. `/metrics` exposes in-process request counters and duration histograms, and `/health` reports application liveness only. Tracing, log retention, and centralized error reporting are not implemented.

## Security and deployment

- Flask debug mode is disabled and the development server binds to localhost.
- API keys are read from environment variables or `.env`; a dedicated secret-management and rotation process is not included.
- There is no authentication, authorization, CSRF protection, or rate limiting.
- Upload checks match basic signatures to extensions and selected media type, but do not fully parse files or scan for malware. Uploaded files are limited to 5 MB and stored under random names outside Flask's static directory.
- No production WSGI deployment configuration, container image, CD deployment pipeline, or health/readiness endpoints are provided. A GitHub Actions CI workflow runs the test suite.

## Build and verification status

The regression suite runs with:

```bash
python -m unittest discover -s tests -v
```

The suite includes mocked provider success and failure cases, local fallback, CLI/scheduler validation, scheduler persistence and recovery, output files, and Flask route tests. GitHub Actions is configured for Python 3.10–3.12. Tests do not make real provider requests. Live provider validation requires credentials and is outstanding.

## Overall technical assessment

Phase 1 addresses provider compatibility and input-validation defects; Phase 2 adds CI, web/scheduler regression coverage, SQLite-backed local job lifecycle controls, per-job worker leases, bounded generation retries, and an opt-in scheduler supervisor. Production resilience and security remain incomplete. Treat the app as a local prototype until provider smoke tests, unattended supervisor startup, and deployment safeguards are in place.
