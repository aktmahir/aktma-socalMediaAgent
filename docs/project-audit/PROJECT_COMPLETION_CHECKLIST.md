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
- [x] Bounded retry policy records failures and stops after three unexpected generator exceptions.
- [ ] Provider/model outage policy beyond the existing local fallback behavior.
- [ ] Actual image/video analysis and content-aware generation.
- [x] Web uploads enforce a 5 MB limit, allowlisted extensions, matching signatures and media type, and server-generated storage names.
- [ ] Malware scanning, full media parsing, and actual image/video analysis.

## Security and operations

- [ ] Authentication and authorization for any shared deployment.
- [ ] CSRF protection and rate limiting for web routes.
- [ ] Production WSGI/server and deployment configuration.
- [ ] Secret-management and rotation guidance beyond local `.env`.
- [x] Application liveness endpoint, structured application/scheduler logs, and in-process request metrics.
- [ ] Production readiness checks, persistent metrics, and centralized error reporting.
- [x] CI workflow configured to run the regression suite.

Jobs left running after process termination can be recovered manually with `--run-scheduled JOB_ID` or by running `--supervise-scheduled` after the 120-second lease expires. On Windows, `scripts/register-scheduler-supervisor.ps1` provides opt-in current-user logon startup; the task is not registered automatically. The lease is local to one SQLite database and is not a distributed or production-grade job service.

## Completion gate

Do not treat the application as production-ready until live provider behavior has been verified, upload malware/content scanning is addressed for the exposure model, web routes have test coverage, and the relevant deployment, security, and scheduler durability requirements are addressed.
