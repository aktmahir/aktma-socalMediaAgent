# Missing Features and Incomplete Functionality

## Inventory

| ID | Feature | Status | Priority | Notes |
| --- | --- | --- | --- | --- |
| MF-001 | OpenAI SDK compatibility | Implemented; mock-tested | P0 | Current OpenAI client path is used; live access remains unverified. |
| MF-002 | Hugging Face/Cohere authentication and request handling | Implemented; mock-tested | P0 | Bearer auth and fallback behavior are tested; real provider/model availability is not. |
| MF-003 | Core input and schedule validation | Implemented; partially tested | P0 | CLI and scheduler tests exist; web route-level tests are still needed. |
| MF-004 | Automated tests and CI | Partially implemented | P1 | `unittest` regression tests are present; CI and web route tests are absent. |
| MF-005 | Persistent schedule state | Missing | P1 | Jobs cannot be paused, inspected, resumed, or recovered after restart. |
| MF-006 | Authentication and authorization | Missing | P1 | Keep deployment local until access control is added. |
| MF-007 | Production deployment configuration | Missing | P1 | No production WSGI, health checks, or deploy pipeline. |
| MF-008 | Actual media analysis | Missing | P2 | Upload name is prompt context; file contents are not processed. |
| MF-009 | Operational logging and monitoring | Partial | P2 | Provider failures are logged; metrics, structured context, and monitoring are absent. |
| MF-010 | Operational security hardening | Missing | P1 | No CSRF protection, rate limiting, secret-management service, or upload scanning. |

## Remaining work

### Provider verification

The adapters now use current request patterns and have mock tests for response parsing, authentication headers, and failure fallback. Credentialed smoke tests are still needed to verify provider-side permissions, model availability, and live response shapes.

### Web test coverage

The form performs basic validation and displays status feedback, but the Flask route is not covered by automated test-client tests. Add coverage for invalid topics, unsupported choices, upload extension rejection, invalid count/interval, and valid generation/scheduling flows.

### Durable scheduling

Scheduling remains a local process loop that writes files. Persistent job records, lifecycle controls, retry policy, and restart recovery are not available.

### Media workflow

Uploads are stored locally after filename sanitization and extension allowlisting. The app does not inspect content, enforce upload size limits, or perform image/video analysis.

### Production operation

The app is configured for local development, not shared or production deployment. Authentication, CSRF, rate limits, production WSGI configuration, secret handling, health checks, and monitoring remain to be designed.
