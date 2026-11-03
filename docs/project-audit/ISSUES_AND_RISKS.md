# Issues and Risks

## Issue inventory

| ID | Severity | Status | File(s) | Summary / evidence |
| --- | --- | --- | --- | --- |
| ISS-001 | P0 | Implemented; mock-tested | `social_media_agent/generator.py` | OpenAI uses the current SDK client API. Live credentials have not been tested. |
| ISS-002 | P0 | Implemented; mock-tested | `social_media_agent/generator.py` | Hugging Face and Cohere use Bearer authentication; Cohere was moved to v2 Chat. Live endpoint/model access remains unverified. |
| ISS-003 | P0 | Implemented for core cases | `app.py`, `social_media_agent/web.py`, `social_media_agent/scheduler.py` | Topic, core choice, interval, and count validation is present and Flask route-tested. Comprehensive abuse validation remains outstanding. |
| ISS-004 | P1 | Implemented; locally verified | `tests/`, `.github/workflows/python-tests.yml` | Standard-library regression tests cover provider behavior, scheduler persistence/output, and Flask routes; CI is configured for pushes and pull requests. |
| ISS-005 | P1 | Partially addressed | `social_media_agent/scheduler.py`, `app.py`, `scripts/register-scheduler-supervisor.ps1` | SQLite job records, CLI lifecycle controls, per-job expiring worker leases, bounded retries, explicit retry of terminal failures, and an opt-in CLI supervisor are implemented. A Windows logon-task registration script is available but must be run for the intended user. |
| ISS-006 | P1 | Open | Web application | No authentication or authorization. Intended for local use only. |
| ISS-007 | P1 | Partially addressed | Project configuration | `GET /health` checks application liveness only; no production deployment configuration, readiness checks, or environment separation beyond `.env`. |
| ISS-008 | P2 | Partially addressed | `social_media_agent/web.py` | Uploads have a 5 MB cap, allowlisted extensions/signatures, media-type consistency checks, and random server-generated names. Full media parsing, malware scanning, and content analysis remain absent. |
| ISS-009 | P2 | Partially addressed | `social_media_agent/generator.py`, `social_media_agent/web.py`, `social_media_agent/scheduler.py` | Provider errors, JSON request/job lifecycle logs, and in-process Prometheus request metrics are available; centralized exception reporting, log retention, persistent metrics, and monitoring remain absent. |
| ISS-010 | P2 | Implemented for local runner | `social_media_agent/web.py` | Debug mode is off and the development runner binds to localhost; this does not replace production server configuration. |

## Remaining risks

### Provider verification

Mock tests validate request shape, auth header construction, parsing, and fallback behavior. They cannot verify real credentials, provider entitlements, endpoint availability, rate limits, or configured model access.

### Scheduler lifecycle

Job configuration, progress, retry attempts, next-run time, status, failures, and completed generation payloads are persisted in SQLite. Unexpected generator exceptions are retried up to three total attempts with 1- and 2-second delays; terminal failures can be explicitly restarted with `--retry-job JOB_ID`; adapter errors that fall back locally are considered successful. Workers run in-process, and web workers are daemon threads. Manual recovery with `--run-scheduled JOB_ID` or the opt-in `--supervise-scheduled` supervisor is available after the 120-second lease expires. A Windows logon-task registration script is provided but must be run explicitly for the intended user. Leases prevent concurrent workers for the same job in one database; separate databases are not coordinated. Once a generated payload is committed, recovery rewrites the same output file without calling the generator again. A crash after provider generation but before that payload commit can still cause the provider call to repeat.

### Web exposure and uploads

The Flask app has no user authentication, CSRF protection, or rate limiting. Uploads are limited to 5 MB and checked against expected signatures, but there is no full media parsing or malware scanning. Keep the web app local unless appropriate controls are added.

### Operations

Provider failures and JSON-formatted request/job events are logged at INFO by CLI/web entry points. An in-process `/metrics` endpoint exposes request totals and latency histograms; counters reset on restart. `/health` confirms only that the Flask app can serve a request. Operational visibility remains limited: centralized exception reporting, log retention, monitoring, readiness checks, and deployment automation are absent.

## Mitigation priorities

1. Run credentialed provider smoke tests and document verified model configuration.
2. Keep route/scheduler regression coverage current; the Python 3.10–3.12 GitHub Actions matrix passed for commit `2310887`.
3. Register the Windows supervisor task for the intended user if unattended recovery after sign-in is required, and define provider outage behavior.
4. Add deployment, access control, CSRF/rate-limit, and malware-scanning safeguards before any shared exposure.
5. Extend operational metrics with persistence and alerting; add centralized exception reporting, log retention, and monitoring.
