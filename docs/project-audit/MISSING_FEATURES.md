# Missing Features and Incomplete Functionality

## Inventory

| ID | Feature | Status | Priority | Notes |
| --- | --- | --- | --- | --- |
| MF-001 | OpenAI SDK compatibility | Implemented; mock-tested | P0 | Current OpenAI client path is used; live access remains unverified. |
| MF-002 | Hugging Face/Cohere authentication and request handling | Implemented; mock-tested | P0 | Bearer auth and fallback behavior are tested; real provider/model availability is not. |
| MF-003 | Core input and schedule validation | Implemented; tested | P0 | CLI, scheduler, and Flask test-client tests cover core invalid inputs and valid generation. |
| MF-004 | Automated tests and CI | Implemented; locally verified | P1 | `unittest` regression coverage includes scheduler lifecycle and Flask routes; GitHub Actions runs the suite. |
| MF-005 | Persistent schedule state | Implemented for local use | P1 | SQLite records jobs and generated outputs; CLI supports listing, pause/resume/cancel, manual recovery, an opt-in supervisor, leases, and three-attempt retries for unexpected generator exceptions. Automatic supervisor startup remains missing. |
| MF-006 | Authentication and authorization | Missing | P1 | Keep deployment local until access control is added. |
| MF-007 | Production deployment configuration | Missing | P1 | No production WSGI, health checks, or deploy pipeline. |
| MF-008 | Actual media analysis | Missing | P2 | Upload name is prompt context; file contents are not processed. |
| MF-009 | Operational logging and monitoring | Partial | P2 | Provider failures are logged; metrics, structured context, and monitoring are absent. |
| MF-010 | Operational security hardening | Missing | P1 | No CSRF protection, rate limiting, secret-management service, or upload scanning. |

## Remaining work

### Provider verification

The adapters now use current request patterns and have mock tests for response parsing, authentication headers, and failure fallback. Credentialed smoke tests are still needed to verify provider-side permissions, model availability, and live response shapes.

### Web test coverage

The form performs basic validation and displays status feedback. Flask test-client tests cover valid generation, invalid schedule input, and valid schedule creation; upload rejection remains a candidate for additional route coverage.

### Durable scheduling

Scheduling writes files through local process workers and persists job records, attempts, and generated outputs in SQLite. CLI lifecycle controls, manual recovery, an opt-in supervisor, per-job worker leases, and bounded generator retries are available. The supervisor must be launched separately for unattended operation.

### Media workflow

Uploads are stored locally after filename sanitization and extension allowlisting. The app does not inspect content, enforce upload size limits, or perform image/video analysis.

### Production operation

The app is configured for local development, not shared or production deployment. Authentication, CSRF, rate limits, production WSGI configuration, secret handling, health checks, and monitoring remain to be designed.
