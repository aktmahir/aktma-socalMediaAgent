# Implementation Roadmap

## Phase 1 — Critical Fixes and Stabilization

### ROAD-01 — OpenAI SDK compatibility
- **Status:** Implemented; mock-tested.
- **Description:** Use the current OpenAI Python SDK client interface.
- **Module:** `social_media_agent/generator.py`
- **Acceptance:** No legacy `ChatCompletion.create` path remains; mocked success and failure tests verify response handling and local fallback.
- **Remaining verification:** Live request with valid credentials and a currently accessible model.

### ROAD-02 — Hugging Face and Cohere request construction
- **Status:** Implemented; mock-tested.
- **Description:** Use configured Bearer tokens, current request/response shapes, and visible fallback logging.
- **Modules:** `social_media_agent/generator.py`
- **Acceptance:** Mock tests verify authentication, response parsing, HTTP failure handling, and API error payload fallback. Cohere uses v2 Chat and JSON response format.
- **Remaining verification:** Live credentialed requests and provider-side model availability. Hugging Face availability depends on the configured model and currently available inference service.

### ROAD-03 — User input and scheduler validation
- **Status:** Implemented; locally tested.
- **Description:** Reject malformed topics, options, intervals, counts, and unsupported upload extensions, and guard scheduler direct calls.
- **Modules:** `app.py`, `social_media_agent/web.py`, `social_media_agent/scheduler.py`
- **Acceptance:** CLI reports invalid arguments with parser errors; web form returns status feedback; scheduler rejects invalid interval seconds and negative counts.
- **Verification:** Flask test-client tests cover valid generation and invalid schedule input.

## Phase 2 — Core Feature Completion

### ROAD-04 — Automated tests and CI
- **Status:** Implemented; locally verified.
- **Description:** Expand regression coverage to the scheduler and generator and run it automatically.
- **Modules:** `tests/`, CI configuration.
- **Current state:** `unittest` regression tests cover provider mocks and failures, scheduler output/recovery/supervision, and Flask generation and schedule submissions. GitHub Actions is configured to run the suite on pushes and pull requests across Python 3.9–3.12.
- **Verified:** The current suite discovers 131 tests and the full Windows run passed all 131. The 126-test suite at GitHub Actions run 16 passed locally in a Python 3.9 container and on CI across Python 3.9 (Ubuntu 22.04) and Python 3.10–3.12; Python 3.9 dependency installation and `pip install .` also passed. The separate Docker monitoring job failed in run 16 and requires follow-up.
- **Remaining:** Expand coverage as new features land.

### ROAD-05 — Persistent scheduling
- **Status:** Implemented for local and Docker use with a SQLite worker lease.
- **Description:** Add durable job records, lifecycle state, and recovery.
- **Modules:** `social_media_agent/scheduler.py`, `app.py`, `social_media_agent/web.py`
- **Acceptance:** SQLite stores job configuration, status, progress, next run, and failures. CLI supports listing, pausing, resuming, cancelling, and resuming a persisted running job after restart.
- **Limitations:** Docker Compose starts a separate supervisor against the shared database, which recovers abandoned jobs after the 120-second worker lease expires. Local recovery is available manually through `--run-scheduled JOB_ID` or continuously through the opt-in `--supervise-scheduled` CLI command. The lease prevents overlapping workers for the same database/job but is not distributed coordination. Unexpected generator exceptions are retried up to three attempts with 1- and 2-second delays; terminal errors are persisted and can be retried explicitly with `--retry-job JOB_ID`. Provider/model failures use local generation without provider retries; fallback source is recorded in generated JSON, console output, and lifecycle logs, and the fallback counts as a successful scheduled iteration. Persisted generation payloads replay to the same output file if progress recording is interrupted; provider calls may repeat if interruption occurs before the payload is committed. Web-created workers are daemon threads and stop with the web process.

### ROAD-06 — Authentication and authorization
- **Status:** Implemented for single-user local/Docker access.
- **Description:** Protect application routes, including metrics, with a rate-limited CSRF-protected login. Health/readiness remain public for orchestration.
- **Acceptance:** Environment configuration validation, protected-route, login/logout, invalid-credential, and Docker bind tests pass.
- **Limitations:** Multi-user identity/roles and external identity providers are not implemented.

### ROAD-11 — Process supervision
- **Status:** Implemented as an opt-in local CLI supervisor and an automatic Docker Compose service.
- **Description:** `--supervise-scheduled` scans persisted running jobs and launches up to a configurable number of workers; worker leases prevent duplicate execution for the same database/job. Compose runs the supervisor in a separate container sharing the scheduler SQLite database and output volume with the web app; it recovers abandoned jobs after their 120-second leases expire.
- **Verification:** Regression tests cover recovery of a persisted running job and CLI option dispatch.
- **Windows setup:** `scripts/register-scheduler-supervisor.ps1` can register a current-user logon task, with `-WhatIf`, optional immediate start, and an unregister mode. Registration remains an explicit operator action; it is not run automatically by installation.
- **Limitations:** The Windows task starts after that user signs in and stops when the user session ends; it does not provide pre-login machine startup. SQLite leases are local coordination, not distributed locking for multiple hosts or separate databases. Compose's database path and output volume are shared with the app, while local web-created schedules retain the existing per-output-directory database default unless `SCHEDULER_DB_PATH` is set.

## Phase 3 — Integration and Data Reliability

### ROAD-07 — Media upload processing
- **Status:** Partially implemented; upload validation, optional malware scanning, bounded format parsing, and opt-in provider vision.
- **Description:** The web upload path enforces a 5 MB per-file limit, allowlisted extensions, matching signatures and selected media type, one file per request, and random server-generated names. Optional ClamAV rejects detected files and labels unavailable/error scans as unscanned. Pillow validates bounded image frames and reads orientation, format, EXIF tag names, and color profile metadata. FFprobe validates video containers/streams and reads video/audio metadata; FFmpeg samples up to three frames. An unchecked-by-default option sends one image or sampled video frames to an OpenAI vision model for a limited visual description.
- **Verification:** Regression coverage checks scanner outcomes, infected-file removal, image metadata/orientation/frame limits, video/audio metadata/container validation, vision opt-in and payload forwarding, parser/tool failures, and upload cleanup.
- **Remaining:** ClamAV is optional and separately maintained; an unscanned result is not a safety guarantee. Parsing is bounded and not exhaustive validation for all malformed/hostile formats. Provider vision requires an OpenAI key and compatible model, sends media externally only after per-upload opt-in, and does not guarantee complete or accurate interpretation. Video inspection requires FFprobe and FFmpeg on `PATH`.

### ROAD-08 — Operational logging and monitoring
- **Status:** Partially implemented.
- **Description:** Web requests and scheduler lifecycle events emit JSON log records with request/job IDs, status, duration, and safe error types; CLI/web entry points enable INFO logging. `/metrics` exposes SQLite-persisted Prometheus request counters and duration histograms with bounded method/status labels. Unhandled web exceptions are correlated to request IDs, logged with tracebacks, and stored as bounded, data-minimized SQLite events. Optional Sentry reporting is disabled unless `SENTRY_DSN` is configured; events are scrubbed before transmission.
- **Added:** Optional `APP_LOG_FILE` logging rotates at `APP_LOG_MAX_BYTES` and keeps `APP_LOG_BACKUP_COUNT` archives. Docker Compose bounds stdout/stderr retention to three 10 MB files.
- **Added:** Docker Compose scrapes the app with Prometheus using separate HTTP Basic credentials for `/metrics`, with the password mounted as a Docker secret; alert rules cover target availability, sustained 5xx rate, p95 latency, scheduler database availability, failed scheduled jobs, and unhandled application errors. The Prometheus UI is bound to loopback. GitHub Actions builds this stack, verifies the authenticated scrape, scheduler metrics availability, and loaded rules, and confirms the scheduler supervisor starts.
- **Remaining:** Alert notification routing and production log-sink configuration are not implemented. Sentry requires an approved project and explicit opt-in configuration; event scrubbing removes full filesystem paths and arbitrary payloads, but retains source basenames, function names, and line numbers. HTTP logs and persisted error records use matched route templates or an `<unmatched>` marker rather than raw URL path values.

## Phase 4 — UX and Product Completeness

### ROAD-09 — Web feedback and state
- **Status:** Implemented for current local workflows.
- **Description:** Validation feedback is announced accessibly as an assertive error; schedule-start feedback is styled and announced as a polite status. Generated local-template fallback is labeled in the CLI and web result to distinguish it from provider output. Scheduled job IDs link the UI to CLI lifecycle controls.

## Phase 5 — Production Readiness

### ROAD-10 — Deployment and security hardening
- **Status:** Partially implemented; a manual SSH production deployment scaffold and Certbot renewal hook are available for a self-hosted VM, but host provisioning and live deployment remain unverified.
- **Description:** `GET /health` reports liveness. `GET /ready` checks writable observability, upload storage, and scheduled-output storage, browser and Prometheus scrape authentication, stable secret configuration, secure session cookies, disabled debug mode, and healthy shared rate-limit storage; it returns 503 when any check fails and creates the configured scheduled-output root if needed. The app can read Flask, auth, and provider API keys from mounted `*_FILE` paths; Compose mounts host-managed secret files read-only, which are not encrypted at rest. The optional TLS Compose overlay supports a Certbot HTTP-01 webroot challenge, removes the app's published HTTP port, and configures one trusted forwarded-header hop from the proxy's exact IP. A manual GitHub Actions workflow preflights tests/Compose and deploys a release over SSH to a self-hosted VM using verified known-host data; a Certbot deploy hook recreates the TLS proxy after renewal. These are unverified deployment scaffolds: host provisioning, public deployment, external secret manager/rotation, and live certificate renewal remain outstanding.

## Phase completion criteria

- **Phase 1:** Provider adapters and basic input/schedule checks are implemented and mock-tested. Credentialed provider smoke requests were attempted on 2026-11-11, but OpenAI returned an authentication error, Hugging Face a connection error, and Cohere an HTTP error; successful live checks remain.
- **Phase 2:** Core behavior has broad test coverage and scheduled jobs have durable state.
- **Phase 3:** Upload/data handling and operational controls are reliable.
- **Phase 4:** The UI presents clear, tested workflows.
- **Phase 5:** Deployment and security controls are verified for the target environment.

## Recommended next actions

1. Run credentialed smoke tests for OpenAI, Hugging Face, and Cohere using supported models.
2. Use Docker Compose's supervisor for unattended Docker recovery, or configure the local CLI supervisor as an operating-system service/task; define provider outage behavior.
3. Add deployment, access-control, and production safeguards before external exposure.
