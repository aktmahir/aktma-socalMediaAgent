# Issues and Risks

## Issue inventory

| ID | Severity | Status | File(s) | Summary / evidence |
| --- | --- | --- | --- | --- |
| ISS-001 | P0 | Implemented; mock-tested | `social_media_agent/generator.py` | OpenAI uses the current SDK client API. Live credentials have not been tested. |
| ISS-002 | P0 | Implemented; mock-tested | `social_media_agent/generator.py` | Hugging Face and Cohere use Bearer authentication; Cohere was moved to v2 Chat. Live endpoint/model access remains unverified. |
| ISS-003 | P0 | Implemented for core cases | `app.py`, `social_media_agent/web.py`, `social_media_agent/scheduler.py` | Topic, core choice, interval, and count validation is present. Flask route-level tests and comprehensive abuse validation remain outstanding. |
| ISS-004 | P1 | Partially addressed | `tests/` | Standard-library regression tests exist and run locally; no CI workflow and no Flask route tests exist yet. |
| ISS-005 | P1 | Open | `social_media_agent/scheduler.py` | Schedules run in process and have no persistent state, lifecycle controls, or restart recovery. |
| ISS-006 | P1 | Open | Web application | No authentication or authorization. Intended for local use only. |
| ISS-007 | P1 | Open | Project configuration | No production deployment configuration, health checks, or environment separation beyond `.env`. |
| ISS-008 | P2 | Open | `social_media_agent/web.py` | Uploads are stored by extension-allowlist; their contents are not analyzed or scanned. |
| ISS-009 | P2 | Partially addressed | `social_media_agent/generator.py` | Provider errors are logged, but structured operational logging, metrics, and monitoring are absent. |
| ISS-010 | P2 | Implemented for local runner | `social_media_agent/web.py` | Debug mode is off and the development runner binds to localhost; this does not replace production server configuration. |

## Remaining risks

### Provider verification

Mock tests validate request shape, auth header construction, parsing, and fallback behavior. They cannot verify real credentials, provider entitlements, endpoint availability, rate limits, or configured model access.

### Scheduler lifecycle

The scheduler is an in-process loop. It has no persistent queue or status store, and web schedules run in daemon threads that stop with the web process.

### Web exposure and uploads

The Flask app has no user authentication, CSRF protection, or rate limiting. Upload validation is extension-based and does not provide file-content verification, malware scanning, or size limits. Keep the web app local unless appropriate controls are added.

### Operations

Provider failures are logged, but operational visibility is limited. There is no structured scheduler history, monitoring, health endpoint, or deployment automation.

## Mitigation priorities

1. Run credentialed provider smoke tests and document verified model configuration.
2. Add Flask test-client coverage for valid and invalid submissions.
3. Decide whether durable scheduling is in scope; add persistence and lifecycle controls if required.
4. Add deployment, access control, CSRF/rate-limit, and upload safeguards before any shared exposure.
5. Add CI and operational monitoring.
