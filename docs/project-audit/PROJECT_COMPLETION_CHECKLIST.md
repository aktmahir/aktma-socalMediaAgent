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
- [ ] Credentialed live smoke tests for each external provider.
- [ ] Flask test-client coverage for valid and invalid form submissions.

## Core product and reliability

- [ ] Persistent schedule records and job lifecycle controls.
- [ ] Scheduler pause, resume, cancellation, and recovery after process restart.
- [ ] Retry policy and defined behavior for provider/model outages.
- [ ] Actual image/video analysis and content-aware generation.
- [ ] Upload size and content validation beyond extension checks.

## Security and operations

- [ ] Authentication and authorization for any shared deployment.
- [ ] CSRF protection and rate limiting for web routes.
- [ ] Production WSGI/server and deployment configuration.
- [ ] Secret-management and rotation guidance beyond local `.env`.
- [ ] Health checks, structured application/scheduler logs, and monitoring.
- [ ] CI workflow running the regression suite.

## Completion gate

Do not treat the application as production-ready until live provider behavior has been verified, web routes have test coverage, and the relevant deployment, security, and scheduler durability requirements are addressed.
