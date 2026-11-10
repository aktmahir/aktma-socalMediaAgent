# Missing Features and Incomplete Functionality

## Inventory

| ID | Feature | Status | Priority | Notes |
| --- | --- | --- | --- | --- |
| MF-001 | OpenAI SDK compatibility | Implemented; mock-tested | P0 | Current OpenAI client path is used; live access remains unverified. |
| MF-002 | Hugging Face/Cohere authentication and request handling | Implemented; mock-tested | P0 | Bearer auth and fallback behavior are tested; real provider/model availability is not. |
| MF-003 | Core input and schedule validation | Implemented; tested | P0 | CLI, scheduler, and Flask test-client tests cover core invalid inputs and valid generation. |
| MF-004 | Automated tests and CI | Implemented; one intermittent local Windows test issue | P1 | The current suite discovers 81 `unittest` cases covering scheduler lifecycle, Flask routes, metrics, readiness, error reporting, and provider mocks. In the latest run 80 passed; one scheduler recovery test hit an intermittent SQLite temporary-directory cleanup race but passed when isolated. GitHub Actions last passed Python 3.10–3.12 on commit `80d1215` (48 tests at that revision). |
| MF-005 | Persistent schedule state | Implemented for local use | P1 | SQLite records jobs and generated outputs; CLI supports lifecycle operations and an opt-in supervisor. A PowerShell script can register current-user Windows logon startup; task registration remains an explicit operator action. |
| MF-006 | Authentication and authorization | Missing | P1 | Keep deployment local until access control is added. |
| MF-007 | Production deployment configuration | Partial | P1 | `/ready` checks writable local dependencies, stable secret, secure cookies, disabled debug mode, and shared limiter storage, but production WSGI configuration, environment separation, and deployment pipeline are absent. |
| MF-008 | Actual media analysis | Partial | P2 | Bounded local image/video metadata and visual observations are implemented, with optional ClamAV scanning and opt-in OpenAI vision descriptions. Parsing is not exhaustive and ClamAV may be unavailable. |
| MF-009 | Operational logging and monitoring | Partial | P2 | Request metrics and bounded error metadata persist in SQLite; unhandled exceptions are logged with request-correlated tracebacks. External reporting, log retention, alerting, and monitoring remain absent. |
| MF-010 | Operational security hardening | Partial | P1 | CSRF protection and per-IP rate limits are implemented. Authentication, shared limiter storage by default, dedicated secret management, and malware scanning remain absent. |

## Remaining work

### Provider verification

The adapters now use current request patterns and have mock tests for response parsing, authentication headers, and failure fallback. Credentialed smoke tests are still needed to verify provider-side permissions, model availability, and live response shapes.

### Web test coverage

The form performs basic validation and displays status feedback. Flask test-client coverage includes valid generation/scheduling, invalid schedule input, upload size boundaries, signature/media-type checks, unique storage names, and rejected uploads.

### Durable scheduling

Scheduling writes files through local process workers and persists job records, attempts, and generated outputs in SQLite. CLI lifecycle controls, manual recovery, an opt-in supervisor, per-job worker leases, and bounded generator retries are available. Windows users can opt in to current-user logon startup with `scripts/register-scheduler-supervisor.ps1`; no task is registered automatically.

### Media workflow

Uploads are limited to 5 MB, validated against allowlisted extensions, basic signatures, and selected media type, and stored using random server-generated names. Image/video parsing is bounded; optional ClamAV may be unavailable, and semantic vision is sent to OpenAI only after explicit user opt-in. This does not constitute exhaustive parsing or a safety guarantee.

### Production operation

The app is configured for local development, not shared or production deployment. Authentication, production WSGI configuration, dedicated secret management, deployment-level log retention, external error reporting, and monitoring remain to be designed. Readiness is available at `/ready`. Rate limiting defaults to process-local storage and must use shared storage in multi-worker deployments.
