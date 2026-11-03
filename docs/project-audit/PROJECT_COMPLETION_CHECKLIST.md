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
- [ ] Automatic supervisor startup through the web app or an operating-system service/task.
- [x] Bounded retry policy records failures and stops after three unexpected generator exceptions.
- [ ] Provider/model outage policy beyond the existing local fallback behavior.
- [ ] Actual image/video analysis and content-aware generation.
- [ ] Upload size and content validation beyond extension checks.

## Security and operations

- [ ] Authentication and authorization for any shared deployment.
- [ ] CSRF protection and rate limiting for web routes.
- [ ] Production WSGI/server and deployment configuration.
- [ ] Secret-management and rotation guidance beyond local `.env`.
- [ ] Health checks, structured application/scheduler logs, and monitoring.
- [x] CI workflow configured to run the regression suite.

Jobs left running after process termination can be recovered manually with `--run-scheduled JOB_ID` or by running `--supervise-scheduled` after the 120-second lease expires. The supervisor must be launched separately; the lease is local to one SQLite database and is not a distributed or production-grade job service.

## Completion gate

Do not treat the application as production-ready until live provider behavior has been verified, web routes have test coverage, and the relevant deployment, security, and scheduler durability requirements are addressed.
