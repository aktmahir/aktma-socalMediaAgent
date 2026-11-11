# Project Completion Checklist

This checklist reflects the current prototype status. Checked items are implemented or locally verified; they do not imply production readiness.

## Phase 1 — critical fixes and stabilization

- [x] Local fallback generates the documented output fields.
- [x] OpenAI uses the current SDK client API; mocked success and failure tests pass.
- [x] Hugging Face and Cohere use Bearer authentication and mock-tested response parsing.
- [x] Cohere adapter uses v2 Chat request/response format.
- [x] Provider transport and error-payload failures are logged and fall back locally.
- [x] CLI rejects empty topics, negative counts, and invalid schedule intervals.
- [x] Web form validates basic topic, option, extension, count, and interval input.
- [x] Scheduler rejects non-positive intervals and negative counts on direct calls.
- [x] Regression tests pass using Python's built-in `unittest` runner.
- [x] Python 3.9 runtime, dependency, package-install, and test compatibility passes the expanded CI matrix (GitHub Actions run 16 passed all 126 tests on Ubuntu 22.04).
- [x] Flask test-client coverage exercises valid generation, invalid scheduling input, and valid scheduled-job creation.
- [x] GitHub Actions workflow runs the test suite on pushes and pull requests.
- [ ] Credentialed live smoke tests pass for each external provider (latest one-request attempt per configured provider fell back locally: OpenAI authentication error, Hugging Face connection error, Cohere HTTP error).

## Core product and reliability

- [x] SQLite persists schedule configuration, status, progress, next-run time, and failures.
- [x] CLI supports listing, pausing, resuming, cancelling, and recovering a persisted running job.
- [x] SQLite worker leases prevent concurrent workers for the same job and expire for manual recovery after process failure.
- [x] Operators can explicitly retry a job after bounded generation retries are exhausted.
- [x] Opt-in CLI supervisor scans persisted running jobs and recovers expired workers with a configurable concurrency limit.
- [x] Docker Compose runs a separate scheduler supervisor sharing the app database/output volume and coordinating through job leases.
- [x] Optional Windows Task Scheduler registration script starts the supervisor at the current user's logon.
- [x] Register the Windows logon task for the current Windows account/host; repeat on any other account/host that needs unattended scheduler recovery.
- [x] Web validation errors and schedule-start messages have distinct accessible status styling and live-region announcements.
- [x] Generated posts identify whether output came from the selected provider or the local template fallback.
- [x] Bounded retry policy records failures and stops after three unexpected generator exceptions.
- [x] Provider/model outage policy: retain local fallback without automatic provider retries, and clearly mark fallback source in CLI, web, scheduled JSON, and scheduler events.
- [x] Lightweight local image/video analysis feeds objective visual observations into content generation; video sampling uses optional FFmpeg.
- [x] Web uploads enforce a 5 MB limit, allowlisted extensions, matching signatures and media type, and server-generated storage names.
- [x] Optional ClamAV scans reject detections and label uploads unscanned when ClamAV is unavailable or errors.
- [x] Bounded image EXIF/orientation and video/audio stream metadata parsing with strict decode/container checks.
- [x] Optional OpenAI semantic image/video-frame descriptions require an explicit per-upload opt-in.
- [ ] Exhaustive media validation and reliable semantic interpretation across all content (bounded local checks and sampled vision cannot guarantee this).

## Security and operations

- [x] Optional single-user authentication for local/Docker deployments.
- [x] Authenticated browser sessions expire after a fixed 12-hour maximum lifetime; HTTPS uses a host-only `__Host-` cookie.
- [ ] Multi-user authentication and role-based authorization for shared deployments.
- [x] Session-backed CSRF protection and per-IP rate limiting for web routes (120 requests/hour globally; 10 POSTs/minute for generation/scheduling).
- [x] Browser security headers restrict content sources, framing, referrers, and unused device permissions; HSTS is sent only over HTTPS.
- [x] Docker app, scheduler, Redis, and Prometheus containers use non-root users, read-only root filesystems, dropped Linux capabilities, no-new-privileges, and bounded temporary filesystems.
- [x] Prometheus lifecycle control endpoints are disabled; the stack does not require remote config reload or shutdown.
- [x] Optional TLS proxy uses a read-only root filesystem, retains only the capabilities needed for binding, cache initialization, and worker privilege dropping, and writes runtime state only to bounded temporary filesystems.
- [x] Optional TLS proxy suppresses the Nginx version token in response headers.
- [x] Redis is attached only to an internal rate-limit network shared with the app, not the scheduler or Prometheus.
- [x] Gunicorn WSGI and loopback-only Docker Compose deployment configuration with optional Nginx TLS.
- [x] Manual GitHub Actions SSH deployment scaffold for a self-hosted VM, with test/Compose preflight and pinned host-key verification.
- [x] Let's Encrypt HTTP-01 webroot route and TLS-proxy renewal deploy hook.
- [ ] Provisioned and publicly validated production VM, external secret manager with verified rotation, and automated certificate renewal lifecycle.
- [x] Local `.env` signing-key generation, storage, and session invalidation on rotation are documented.
- [ ] Production secret-management and rotation beyond local `.env`.
- [x] Application liveness endpoint, structured application/scheduler logs, and persistent request metrics.
- [x] Production readiness endpoint, SQLite-persistent request metrics, and centralized local exception reporting with bounded error-event retention.
- [x] Local web launcher binds to `127.0.0.1` with Flask debug mode disabled; regression-tested.
- [x] Web-supplied scheduled-output paths are confined to configurable `SCHEDULED_OUTPUT_ROOT`.
- [x] CI workflow configured to run the regression suite.

Jobs left running after process termination are recovered by the Docker Compose supervisor after the 120-second lease expires. Local installs can run `--run-scheduled JOB_ID` or `--supervise-scheduled`; on Windows, `scripts/register-scheduler-supervisor.ps1` provides opt-in current-user logon startup. The task is not registered automatically. The lease is local to one SQLite database and is not a distributed or production-grade job service.

## Completion gate

Do not treat the application as production-ready until live provider behavior has been verified, upload malware/content scanning is addressed for the exposure model, web routes have test coverage, and the relevant deployment, security, and scheduler durability requirements are addressed.
