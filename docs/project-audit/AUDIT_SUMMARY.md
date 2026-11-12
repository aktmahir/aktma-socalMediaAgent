# Audit Summary

## Current assessment

The project is a local-first Python application for generating social media content. It provides CLI and Flask workflows, three external provider adapters, a local fallback, SQLite-backed scheduled jobs, optional single-user or invite-only multi-user authentication, and a loopback-only Docker stack with monitoring and an optional TLS proxy. Core workflows are tested, but external provider behavior and production operations still need environment-specific verification.

## Phase 1 status

| Roadmap task | Status | Current evidence |
| --- | --- | --- |
| ROAD-01: OpenAI SDK compatibility | Implemented; mocked; live smoke failed | Uses the current `OpenAI` client and has success/fallback tests. The 2026-11-11 credentialed smoke request fell back locally after an authentication error; successful live access remains unverified. |
| ROAD-02: Hugging Face and Cohere requests | Implemented; mocked | Bearer auth and response parsing are covered with mocks; Cohere uses v2 Chat. Live provider/model access remains unverified. |
| ROAD-03: Input and scheduler validation | Implemented; locally tested | CLI, web form, shared interval/count parsers, and scheduler enforce basic input constraints. Automated tests cover parser, CLI, scheduler, and Flask routes. |

## Phase 2 status

| Roadmap task | Status | Current evidence |
| --- | --- | --- |
| ROAD-04: Automated tests and CI | Implemented; Python 3.9–3.12 matrix locally and on CI | Current suite discovers 135 tests; all passed locally on Windows. GitHub Actions run 16 passed all 126 tests present at that revision on Python 3.9 (Ubuntu 22.04) and Python 3.10–3.12. The separate Docker monitoring job failed, so that integration check still needs follow-up. |
| ROAD-05: Persistent scheduling | Implemented for local and Docker use | SQLite persists jobs, retry attempts, and generated payloads; CLI supports lifecycle controls and recovery. Docker Compose runs a separate supervisor sharing the app database and output volume, with leases coordinating active workers. |

The regression suite covers provider success/failure paths, local fallback, schedule parsing, job state persistence/recovery, output files, Flask generation/scheduling/upload validation, request metrics and structured logs, supervisor recovery/concurrency limits, readiness, proxy-header trust, error reporting, health liveness, CLI errors, invitation-based account creation, role enforcement, account disabling, and per-user output scoping. Tests do not make live network calls. Python 3.9 dependency installation, package installation, and the 126-test suite pass locally and in GitHub Actions run 16. The current 135-test suite passes locally; the overall run's separate Docker monitoring job failed and remains to be investigated.

## Remaining risks and limitations

- One minimal credentialed smoke request per configured provider was attempted on 2026-11-11. All fell back locally: OpenAI returned an authentication error, Hugging Face a connection error, and Cohere an HTTP error. Successful real-credential behavior and current model access remain unverified.
- Hugging Face inference availability and model compatibility depend on provider service support.
- Scheduler job state is persisted, and web workers use daemon threads and stop with the web process. Docker Compose runs a separate supervisor that recovers abandoned running jobs after their 120-second leases expire. Local installs can run the CLI supervisor or opt into Windows Task Scheduler registration.
- The Windows task is not registered automatically and starts only after the configured user signs in. Leases prevent concurrent workers per job within one SQLite database; they are not distributed coordination.
- Once generated output is persisted, recovery replays it to the same file without calling the generator again. A process failure before payload persistence may still repeat the provider call.
- Unexpected generator exceptions are retried up to three total attempts with 1- and 2-second delays; provider/model failures use local fallback without automatic provider retries, are marked in scheduled JSON and lifecycle output, and count as successful generation.
- Failed jobs can be retried explicitly with `--retry-job JOB_ID`; the command refuses jobs that are not failed.
- Web uploads are limited to 5 MB, checked against allowlisted extensions/signatures and selected media type, stored under random names, and boundedly parsed locally. ClamAV scanning is optional; semantic vision sends images or sampled video frames to OpenAI only after explicit opt-in.
- CSRF protection, per-IP rate limiting, optional single-user or invite-only multi-user login with admin/user roles and per-user upload/scheduled-output isolation, shared Redis rate-limit storage in Compose, a Gunicorn WSGI factory, read-only secret mounts, and an optional Nginx TLS overlay are implemented. Public-production deployment automation and externally managed secret rotation are not provided.
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
