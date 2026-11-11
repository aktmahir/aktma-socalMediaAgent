# Issues and Risks

## Issue inventory

| ID | Severity | Status | File(s) | Summary / evidence |
| --- | --- | --- | --- | --- |
| ISS-001 | P0 | Implemented; mock-tested | `social_media_agent/generator.py` | OpenAI uses the current SDK client API. Live credentials have not been tested. |
| ISS-002 | P0 | Implemented; mock-tested | `social_media_agent/generator.py` | Hugging Face and Cohere use Bearer authentication; Cohere was moved to v2 Chat. Live endpoint/model access remains unverified. |
| ISS-003 | P0 | Implemented for core cases | `app.py`, `social_media_agent/web.py`, `social_media_agent/scheduler.py` | Topic, core choice, interval, and count validation is present and Flask route-tested. Comprehensive abuse validation remains outstanding. |
| ISS-004 | P1 | Implemented; locally verified | `tests/`, `.github/workflows/python-tests.yml` | Standard-library regression tests cover provider behavior, scheduler persistence/output, and Flask routes; CI is configured for pushes and pull requests. |
| ISS-005 | P1 | Partially addressed | `social_media_agent/scheduler.py`, `app.py`, `docker-compose.yml`, `scripts/register-scheduler-supervisor.ps1` | SQLite job records, CLI lifecycle controls, per-job expiring worker leases, bounded retries, and explicit retry of terminal failures are implemented. Docker Compose runs a supervisor automatically; local installs can use the opt-in CLI supervisor or register the Windows logon task for the intended user. |
| ISS-006 | P1 | Partially addressed | Web application | Optional single-user auth protects the app and separate HTTP Basic credentials protect Prometheus scrapes; Compose requires both. Multi-user authorization and external identity providers are not implemented. Web schedule output is confined to the configured root; default local limiter storage remains process-local. |
| ISS-007 | P1 | Partially addressed | Project configuration | `GET /health` checks liveness and `GET /ready` checks metrics, upload, and scheduled-output storage plus production settings. Gunicorn, loopback-only Compose, Redis, Prometheus, mounted secrets, and an optional Nginx TLS overlay are configured; external production deployment and secret lifecycle remain operator responsibilities. |
| ISS-008 | P2 | Partially addressed | `social_media_agent/web.py`, `social_media_agent/media_analysis.py` | Uploads have a 5 MB cap, allowlisted extensions/signatures, media-type consistency checks, and random server-generated names. Bounded image/video parsing and opt-in OpenAI vision are implemented; ClamAV scanning is optional and may leave files unscanned. These controls are not exhaustive validation or a safety guarantee. |
| ISS-009 | P2 | Partially addressed | `social_media_agent/observability.py`, `social_media_agent/web.py`, `social_media_agent/scheduler.py` | Request metrics and bounded exception metadata persist in SQLite; unhandled exceptions also emit request-correlated tracebacks and can be sent to Sentry after scrubbing when configured. Sentry removes full filesystem paths and payloads but retains source basenames, function names, and line numbers; project setup, log retention, and alerting remain operator responsibilities. |
| ISS-010 | P2 | Implemented for local runner | `social_media_agent/web.py` | Debug mode is off and the development runner binds to localhost; this does not replace production server configuration. |

## Remaining risks

### Provider verification

Mock tests validate request shape, auth header construction, parsing, and fallback behavior. They cannot verify real credentials, provider entitlements, endpoint availability, rate limits, or configured model access.

### Scheduler lifecycle

Job configuration, progress, retry attempts, next-run time, status, failures, and completed generation payloads are persisted in SQLite. Unexpected generator exceptions are retried up to three total attempts with 1- and 2-second delays; terminal failures can be explicitly restarted with `--retry-job JOB_ID`; adapter errors that fall back locally are considered successful. Web workers are daemon threads and stop with the web process. Docker Compose starts a separate supervisor that recovers abandoned running jobs after the 120-second lease expires. Local installs can recover manually with `--run-scheduled JOB_ID` or run the opt-in `--supervise-scheduled` supervisor; Windows logon-task registration remains an explicit operator action. Leases prevent concurrent workers for the same job in one database; separate databases are not coordinated. Once a generated payload is committed, recovery rewrites the same output file without calling the generator again. A crash after provider generation but before that payload commit can still cause the provider call to repeat.

### Web exposure and uploads

Authentication is optional for local development and single-user for configured local/Docker use; Compose requires credentials. CSRF tokens protect form submissions, and per-IP limits apply globally and more strictly to generation/scheduling POSTs. Default local limiter storage is process-local, while Compose uses Redis. Uploads are limited to 5 MB and checked against expected signatures; additional upload safeguards are described above. The TLS overlay and loopback bindings do not by themselves constitute a public-production security review.

### Operations

Provider failures and JSON-formatted request/job events are logged at INFO by CLI/web entry points. HTTP request logs and persisted error records use matched route templates or an `<unmatched>` marker rather than raw URL path values. `/metrics` serves request totals and latency histograms persisted in SQLite. Unhandled web exceptions are captured with request IDs in local logs and a bounded SQLite event table; optional Sentry reporting is opt-in and strips request/user payloads, arbitrary messages, breadcrumbs, local variables, full filesystem paths, and source context. Sanitized events retain source basenames, function names, and line numbers. Sentry project setup and external log retention are not configured by the application. `/health` confirms liveness, and `/ready` checks local metrics, upload, and scheduled-output storage plus production secret/cookie/debug settings and shared limiter storage. Prometheus rules alert on target availability, sustained 5xx rate, and p95 latency; notification delivery and production deployment automation remain absent.

## Mitigation priorities

1. Run credentialed provider smoke tests and document verified model configuration.
2. Keep route/scheduler regression coverage current; verify Python 3.9 in CI (the Python 3.10–3.12 matrix passed for baseline `9f06fdd`).
3. Register the Windows supervisor task for the intended user if unattended recovery after sign-in is required, and define provider outage behavior.
4. Configure external secret/certificate lifecycle, define multi-user access if required, and address malware scanning before any shared exposure.
5. Configure approved Sentry and log sinks if required, then route Prometheus alerts to an operator-selected notification destination.
