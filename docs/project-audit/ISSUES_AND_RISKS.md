# Issues and Risks

## Issue inventory

| ID | Severity | Status | File(s) | Summary / evidence |
| --- | --- | --- | --- | --- |
| ISS-001 | P0 | Implemented; mock-tested | `social_media_agent/generator.py` | OpenAI uses the current SDK client API. Live credentials have not been tested. |
| ISS-002 | P0 | Implemented; mock-tested | `social_media_agent/generator.py` | Hugging Face and Cohere use Bearer authentication; Cohere was moved to v2 Chat. Live endpoint/model access remains unverified. |
| ISS-003 | P0 | Implemented for core cases | `app.py`, `social_media_agent/web.py`, `social_media_agent/scheduler.py` | Topic, core choice, interval, and count validation is present and Flask route-tested. Comprehensive abuse validation remains outstanding. |
| ISS-004 | P1 | Implemented; locally verified | `tests/`, `.github/workflows/python-tests.yml` | Standard-library regression tests cover provider behavior, scheduler persistence/output, and Flask routes; CI is configured for pushes and pull requests. |
| ISS-005 | P1 | Partially addressed | `social_media_agent/scheduler.py`, `app.py` | SQLite job records, CLI lifecycle controls, per-job expiring worker leases, bounded retries for unexpected generator exceptions, explicit retry of terminal failures, and an opt-in CLI supervisor are implemented. The supervisor must be launched separately for unattended recovery. |
| ISS-006 | P1 | Open | Web application | No authentication or authorization. Intended for local use only. |
| ISS-007 | P1 | Open | Project configuration | No production deployment configuration, health checks, or environment separation beyond `.env`. |
| ISS-008 | P2 | Open | `social_media_agent/web.py` | Uploads are stored by extension-allowlist; their contents are not analyzed or scanned. |
| ISS-009 | P2 | Partially addressed | `social_media_agent/generator.py` | Provider errors are logged, but structured operational logging, metrics, and monitoring are absent. |
| ISS-010 | P2 | Implemented for local runner | `social_media_agent/web.py` | Debug mode is off and the development runner binds to localhost; this does not replace production server configuration. |

## Remaining risks

### Provider verification

Mock tests validate request shape, auth header construction, parsing, and fallback behavior. They cannot verify real credentials, provider entitlements, endpoint availability, rate limits, or configured model access.

### Scheduler lifecycle

Job configuration, progress, retry attempts, next-run time, status, failures, and completed generation payloads are persisted in SQLite. Unexpected generator exceptions are retried up to three total attempts with 1- and 2-second delays; terminal failures can be explicitly restarted with `--retry-job JOB_ID`; adapter errors that fall back locally are considered successful. Workers run in-process, and web workers are daemon threads. Manual recovery with `--run-scheduled JOB_ID` or the opt-in `--supervise-scheduled` supervisor is available after the 120-second lease expires. The supervisor requires separate startup configuration. Leases prevent concurrent workers for the same job in one database; separate databases are not coordinated. Once a generated payload is committed, recovery rewrites the same output file without calling the generator again. A crash after provider generation but before that payload commit can still cause the provider call to repeat.

### Web exposure and uploads

The Flask app has no user authentication, CSRF protection, or rate limiting. Upload validation is extension-based and does not provide file-content verification, malware scanning, or size limits. Keep the web app local unless appropriate controls are added.

### Operations

Provider failures are logged, but operational visibility is limited. There is no structured scheduler history, monitoring, health endpoint, or deployment automation.

## Mitigation priorities

1. Run credentialed provider smoke tests and document verified model configuration.
2. Verify the configured CI workflow on GitHub and keep route/scheduler regression coverage current.
3. Configure the opt-in supervisor as an operating-system service/task if unattended recovery is required, and define provider outage behavior.
4. Add deployment, access control, CSRF/rate-limit, and upload safeguards before any shared exposure.
5. Verify the configured CI on GitHub and add operational monitoring.
