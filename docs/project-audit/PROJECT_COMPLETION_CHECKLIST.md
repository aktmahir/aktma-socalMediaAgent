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
- [x] Flask test-client coverage exercises valid generation, invalid scheduling input, and valid scheduled-job creation.
- [x] GitHub Actions workflow runs the test suite on pushes and pull requests.
- [ ] Credentialed live smoke tests for each external provider.

## Core product and reliability

- [x] SQLite persists schedule configuration, status, progress, next-run time, and failures.
- [x] CLI supports listing, pausing, resuming, cancelling, and recovering a persisted running job.
- [x] SQLite worker leases prevent concurrent workers for the same job and expire for manual recovery after process failure.
- [x] Operators can explicitly retry a job after bounded generation retries are exhausted.
- [x] Opt-in CLI supervisor scans persisted running jobs and recovers expired workers with a configurable concurrency limit.
- [x] Optional Windows Task Scheduler registration script starts the supervisor at the current user's logon.
- [x] Windows logon task is registered on this development machine; repeat per account/host when required.
- [x] Web validation errors and schedule-start messages have distinct accessible status styling and live-region announcements.
- [x] Generated posts identify whether output came from the selected provider or the local template fallback.
- [x] Bounded retry policy records failures and stops after three unexpected generator exceptions.
- [x] Provider/model outage policy: retain local fallback without automatic provider retries, and clearly mark fallback source in CLI, web, scheduled JSON, and scheduler events.
- [x] Lightweight local image/video analysis feeds objective visual observations into content generation; video sampling uses optional FFmpeg.
- [x] Web uploads enforce a 5 MB limit, allowlisted extensions, matching signatures and media type, and server-generated storage names.
- [x] Optional ClamAV scans reject detections and label uploads unscanned when ClamAV is unavailable or errors.
- [x] Bounded image EXIF/orientation and video/audio stream metadata parsing with strict decode/container checks.
- [x] Optional OpenAI semantic image/video-frame descriptions require an explicit per-upload opt-in.
- [ ] Exhaustive media validation and reliable semantic interpretation across all content.

## Security and operations

- [ ] Authentication and authorization for any shared deployment.
- [x] Session-backed CSRF protection and per-IP rate limiting for web routes (120 requests/hour globally; 10 POSTs/minute for generation/scheduling).
- [ ] Production WSGI/server and deployment configuration.
- [ ] Secret-management and rotation guidance beyond local `.env`.
- [x] Application liveness endpoint, structured application/scheduler logs, and persistent request metrics.
- [x] Production readiness endpoint, SQLite-persistent request metrics, and centralized local exception reporting with bounded error-event retention.
- [x] CI workflow configured to run the regression suite.

Jobs left running after process termination can be recovered manually with `--run-scheduled JOB_ID` or by running `--supervise-scheduled` after the 120-second lease expires. On Windows, `scripts/register-scheduler-supervisor.ps1` provides opt-in current-user logon startup; the task is not registered automatically. The lease is local to one SQLite database and is not a distributed or production-grade job service.

## Completion gate

Do not treat the application as production-ready until live provider behavior has been verified, upload malware/content scanning is addressed for the exposure model, web routes have test coverage, and the relevant deployment, security, and scheduler durability requirements are addressed.
