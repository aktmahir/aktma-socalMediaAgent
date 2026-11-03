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
- **Current state:** `unittest` regression tests cover provider mocks and failures, scheduler output/recovery/supervision, and Flask generation and schedule submissions. GitHub Actions runs the suite on pushes and pull requests across Python 3.10–3.12.
- **Verified:** The 49-test suite passes locally; GitHub Actions passed all Python 3.10, 3.11, and 3.12 matrix jobs for commit `80d1215` (48 tests at that revision).
- **Remaining:** Expand coverage as new features land.

### ROAD-05 — Persistent scheduling
- **Status:** Implemented for local use with a SQLite worker lease.
- **Description:** Add durable job records, lifecycle state, and recovery.
- **Modules:** `social_media_agent/scheduler.py`, `app.py`, `social_media_agent/web.py`
- **Acceptance:** SQLite stores job configuration, status, progress, next run, and failures. CLI supports listing, pausing, resuming, cancelling, and resuming a persisted running job after restart.
- **Limitations:** Recovery is available manually through `--run-scheduled JOB_ID` or continuously through the opt-in `--supervise-scheduled` CLI command after the 120-second worker lease expires. The lease prevents overlapping workers for the same database/job but is not distributed coordination. Unexpected generator exceptions are retried up to three attempts with 1- and 2-second delays; terminal errors are persisted and can be retried explicitly with `--retry-job JOB_ID`. Provider/model failures use local generation without provider retries; fallback source is recorded in generated JSON, console output, and lifecycle logs, and the fallback counts as a successful scheduled iteration. Persisted generation payloads replay to the same output file if progress recording is interrupted; provider calls may repeat if interruption occurs before the payload is committed. Web-created workers are daemon threads and stop with the web process.

### ROAD-06 — Authentication and authorization
- **Status:** Not started; required only if shared deployment is in scope.
- **Description:** Protect user-facing routes and separate user/job ownership.
- **Acceptance:** Enforced identity and permissions with route-level tests.

### ROAD-11 — Process supervision
- **Status:** Implemented as an opt-in local CLI supervisor.
- **Description:** `--supervise-scheduled` scans persisted running jobs and launches up to a configurable number of workers; worker leases prevent duplicate execution for the same database/job.
- **Verification:** Regression tests cover recovery of a persisted running job and CLI option dispatch.
- **Windows setup:** `scripts/register-scheduler-supervisor.ps1` can register a current-user logon task, with `-WhatIf`, optional immediate start, and an unregister mode. Registration remains an explicit operator action; it is not run automatically by installation.
- **Limitations:** The task starts after that user signs in and stops when the user session ends; it does not provide pre-login machine startup. The supervisor is not started by the web process, and local SQLite leases are not distributed coordination.

## Phase 3 — Integration and Data Reliability

### ROAD-07 — Media upload processing
- **Status:** Partially implemented; upload validation and storage hardened.
- **Description:** The web upload path enforces a 5 MB per-file limit, allowlisted extensions, matching image/video signatures and selected media type, one file per request, and random server-generated storage names. It validates before writing and stores files outside Flask's static directory.
- **Verification:** Regression coverage checks each allowed extension's signature, exact/over-limit sizes, random non-overwriting names, signature/type mismatches, multiple files, and invalid form submissions.
- **Remaining:** Actual media-aware processing, malware scanning, and broader content validation are not implemented.

### ROAD-08 — Operational logging and monitoring
- **Status:** Partially implemented.
- **Description:** Web requests and scheduler lifecycle events emit JSON log records with request/job IDs, status, duration, and safe error types; CLI/web entry points enable INFO logging. `GET /metrics` exposes dependency-free Prometheus request counters and duration histograms with bounded method/status labels. Prompts, credentials, file names, and output paths are excluded from structured logs and metrics.
- **Remaining:** Centralized exception reporting, log retention/rotation, persistent metrics, and production log-sink configuration are not implemented. Metrics are in-process and reset when the web app restarts.

## Phase 4 — UX and Product Completeness

### ROAD-09 — Web feedback and state
- **Status:** Implemented for current local workflows.
- **Description:** Validation feedback is announced accessibly as an assertive error; schedule-start feedback is styled and announced as a polite status. Generated local-template fallback is labeled in the CLI and web result to distinguish it from provider output. Scheduled job IDs link the UI to CLI lifecycle controls.

## Phase 5 — Production Readiness

### ROAD-10 — Deployment and security hardening
- **Status:** Partially implemented for local liveness only.
- **Description:** `GET /health` reports that the Flask app is serving requests. It does not check provider credentials, database readiness, or scheduler workers. Production server configuration, environment separation, readiness checks, and protections appropriate to the exposure model remain outstanding. Flask debug mode is disabled and the local runner binds to localhost, but this is not a production deployment setup.

## Phase completion criteria

- **Phase 1:** Provider adapters and basic input/schedule checks are implemented and mock-tested; live provider smoke tests remain.
- **Phase 2:** Core behavior has broad test coverage and scheduled jobs have durable state.
- **Phase 3:** Upload/data handling and operational controls are reliable.
- **Phase 4:** The UI presents clear, tested workflows.
- **Phase 5:** Deployment and security controls are verified for the target environment.

## Recommended next actions

1. Run credentialed smoke tests for OpenAI, Hugging Face, and Cohere using supported models.
2. Configure the opt-in supervisor as an operating-system service/task if unattended recovery is required, and define provider outage behavior.
3. Add deployment, access-control, and production safeguards before external exposure.
