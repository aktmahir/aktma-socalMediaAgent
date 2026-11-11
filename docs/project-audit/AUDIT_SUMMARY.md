# Audit Summary

## Current assessment

The project is a local-first Python application for generating social media content. It provides CLI and Flask workflows, three external provider adapters, a local fallback, SQLite-backed scheduled jobs, optional single-user authentication, and a loopback-only Docker stack with monitoring and an optional TLS proxy. Core workflows are tested, but external provider behavior and production operations still need environment-specific verification.

## Phase 1 status

| Roadmap task | Status | Current evidence |
| --- | --- | --- |
| ROAD-01: OpenAI SDK compatibility | Implemented; mocked | Uses the current `OpenAI` client and has success/fallback tests. No live credentialed call has been made. |
| ROAD-02: Hugging Face and Cohere requests | Implemented; mocked | Bearer auth and response parsing are covered with mocks; Cohere uses v2 Chat. Live provider/model access remains unverified. |
| ROAD-03: Input and scheduler validation | Implemented; locally tested | CLI, web form, shared interval/count parsers, and scheduler enforce basic input constraints. Automated tests cover parser, CLI, scheduler, and Flask routes. |

## Phase 2 status

| Roadmap task | Status | Current evidence |
| --- | --- | --- |
| ROAD-04: Automated tests and CI | Implemented; Python 3.9 locally verified; GitHub rerun pending | Current suite discovers 126 tests; all passed on Windows and in a Python 3.9 container after dependency and package installation. GitHub Actions run 15 passed Python 3.10–3.12 and Docker monitoring checks. Its Python 3.9 job failed before setup because Ubuntu 26.04 has no matching 3.9 build; that job now targets Ubuntu 22.04 and still needs a successful rerun. |
| ROAD-05: Persistent scheduling | Implemented for local and Docker use | SQLite persists jobs, retry attempts, and generated payloads; CLI supports lifecycle controls and recovery. Docker Compose runs a separate supervisor sharing the app database and output volume, with leases coordinating active workers. |

The regression suite covers provider success/failure paths, local fallback, schedule parsing, job state persistence/recovery, output files, Flask generation/scheduling/upload validation, request metrics and structured logs, supervisor recovery/concurrency limits, readiness, proxy-header trust, error reporting, health liveness, and CLI errors. Tests do not make live network calls. Python 3.9 dependency, package-install, and test compatibility pass locally; confirmation of the corrected GitHub runner selection remains pending.

## Remaining risks and limitations

- Provider behavior has not been validated using real credentials or current provider-side model access.
- Hugging Face inference availability and model compatibility depend on provider service support.
- Scheduler job state is persisted, and web workers use daemon threads and stop with the web process. Docker Compose runs a separate supervisor that recovers abandoned running jobs after their 120-second leases expire. Local installs can run the CLI supervisor or opt into Windows Task Scheduler registration.
- The Windows task is not registered automatically and starts only after the configured user signs in. Leases prevent concurrent workers per job within one SQLite database; they are not distributed coordination.
- Once generated output is persisted, recovery replays it to the same file without calling the generator again. A process failure before payload persistence may still repeat the provider call.
- Unexpected generator exceptions are retried up to three total attempts with 1- and 2-second delays; provider/model failures use local fallback without automatic provider retries, are marked in scheduled JSON and lifecycle output, and count as successful generation.
- Failed jobs can be retried explicitly with `--retry-job JOB_ID`; the command refuses jobs that are not failed.
- Web uploads are limited to 5 MB, checked against allowlisted extensions/signatures and selected media type, stored under random names, and boundedly parsed locally. ClamAV scanning is optional; semantic vision sends images or sampled video frames to OpenAI only after explicit opt-in.
- CSRF protection, per-IP rate limiting, optional single-user login, shared Redis rate-limit storage in Compose, a Gunicorn WSGI factory, read-only secret mounts, and an optional Nginx TLS overlay are implemented. Multi-user authorization, public-production deployment automation, and externally managed secret rotation are not provided.
- Web validation errors and schedule-start messages now use distinct colors and accessible live-region announcements.
- `GET /health` checks liveness; `GET /ready` checks metrics, upload, and scheduled-output storage, stable session-secret configuration, secure cookies, disabled debug mode, and shared rate-limit storage. When browser authentication is configured, detailed readiness checks are limited to authenticated sessions.
- `GET /metrics` exposes request counters and duration histograms persisted in SQLite, plus a cumulative unhandled-error counter, scheduler job-state, and scheduler-database-availability gauges. Prometheus rules alert on new unhandled errors, failed jobs, and missing scheduler metrics in addition to HTTP target, error-rate, and latency conditions. Unhandled web exceptions are request-correlated, logged with tracebacks, and recorded as bounded, data-minimized SQLite events. Optional Sentry reporting sends scrubbed exception events only when a DSN is configured; full paths and payloads are removed, while source basenames, function names, and line numbers remain. Alert notification routing and external log retention remain deployment responsibilities.

## Recommended next steps

1. Run credentialed smoke tests for supported providers and document verified model choices.
2. Keep regression coverage current as features land.
3. Use the Compose supervisor for unattended Docker recovery, or register the Windows supervisor task for local recovery after sign-in; define provider outage behavior.
4. Configure external secret management, certificate issuance/renewal, and alert notification routing before any public deployment.

## Overall conclusion

The app is a functional local-first application with tested provider adapters, durable local scheduling, optional single-user access control, and Docker deployment/monitoring examples. It is not production-certified: live provider behavior, external secret/certificate lifecycle, and alert delivery remain unverified or operator-configured.
