# Missing Features and Incomplete Functionality

## Inventory

| ID | Feature | Status | Priority | Notes |
| --- | --- | --- | --- | --- |
| MF-001 | OpenAI SDK compatibility | Implemented; mock-tested | P0 | Current OpenAI client path is used; live access remains unverified. |
| MF-002 | Hugging Face/Cohere authentication and request handling | Implemented; mock-tested | P0 | Bearer auth and fallback behavior are tested; real provider/model availability is not. |
| MF-003 | Core input and schedule validation | Implemented; tested | P0 | CLI, scheduler, and Flask test-client tests cover core invalid inputs and valid generation. |
| MF-004 | Automated tests and CI | Implemented; locally and remotely verified | P1 | 49 `unittest` regression cases cover scheduler lifecycle, Flask routes, request metrics, health liveness, and provider mocks; GitHub Actions passed for Python 3.10–3.12 on commit `80d1215` (48 tests at that revision). |
| MF-005 | Persistent schedule state | Implemented for local use | P1 | SQLite records jobs and generated outputs; CLI supports lifecycle operations and an opt-in supervisor. A PowerShell script can register current-user Windows logon startup; task registration remains an explicit operator action. |
| MF-006 | Authentication and authorization | Missing | P1 | Keep deployment local until access control is added. |
| MF-007 | Production deployment configuration | Missing | P1 | No production WSGI, readiness checks, or deploy pipeline. A local `/health` liveness endpoint does not establish production readiness. |
| MF-008 | Actual media analysis | Missing | P2 | Upload name is prompt context; file contents are not processed. |
| MF-009 | Operational logging and monitoring | Partial | P2 | Provider failures and JSON request/job lifecycle context are logged; `/metrics` exposes in-process request counts/latency; persistent metrics, centralized exception reporting, retention, and monitoring remain absent. |
| MF-010 | Operational security hardening | Missing | P1 | No CSRF protection, rate limiting, secret-management service, or malware scanning. |

## Remaining work

### Provider verification

The adapters now use current request patterns and have mock tests for response parsing, authentication headers, and failure fallback. Credentialed smoke tests are still needed to verify provider-side permissions, model availability, and live response shapes.

### Web test coverage

The form performs basic validation and displays status feedback. Flask test-client coverage includes valid generation/scheduling, invalid schedule input, upload size boundaries, signature/media-type checks, unique storage names, and rejected uploads.

### Durable scheduling

Scheduling writes files through local process workers and persists job records, attempts, and generated outputs in SQLite. CLI lifecycle controls, manual recovery, an opt-in supervisor, per-job worker leases, and bounded generator retries are available. Windows users can opt in to current-user logon startup with `scripts/register-scheduler-supervisor.ps1`; no task is registered automatically.

### Media workflow

Uploads are limited to 5 MB, validated against allowlisted extensions, basic signatures, and selected media type, and stored using random server-generated names. The app does not fully parse or malware-scan content or perform image/video analysis.

### Production operation

The app is configured for local development, not shared or production deployment. Authentication, CSRF, rate limits, production WSGI configuration, secret handling, health checks, and monitoring remain to be designed.
