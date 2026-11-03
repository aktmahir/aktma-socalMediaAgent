# Audit Summary

## Current assessment

The project is a local Python prototype for generating social media content. It provides CLI and Flask web workflows, three external provider adapters, a local fallback, and SQLite-backed scheduled jobs that write JSON files. Phase 1 stabilization addressed provider request issues and basic input validation; Phase 2 added CI, web/scheduler regression tests, and local job lifecycle controls. The project is still not production-ready.

## Phase 1 status

| Roadmap task | Status | Current evidence |
| --- | --- | --- |
| ROAD-01: OpenAI SDK compatibility | Implemented; mocked | Uses the current `OpenAI` client and has success/fallback tests. No live credentialed call has been made. |
| ROAD-02: Hugging Face and Cohere requests | Implemented; mocked | Bearer auth and response parsing are covered with mocks; Cohere uses v2 Chat. Live provider/model access remains unverified. |
| ROAD-03: Input and scheduler validation | Implemented; locally tested | CLI, web form, shared interval/count parsers, and scheduler enforce basic input constraints. Automated tests cover parser, CLI, scheduler, and Flask routes. |

## Phase 2 status

| Roadmap task | Status | Current evidence |
| --- | --- | --- |
| ROAD-04: Automated tests and CI | Implemented; locally verified | 34 `unittest` cases pass locally; GitHub Actions is configured for Python 3.10–3.12. |
| ROAD-05: Persistent scheduling | Implemented for local use | SQLite persists jobs, retry attempts, and generated payloads; CLI supports inspection, pause/resume/cancel, manual recovery through `--run-scheduled JOB_ID`, and expiring leases to prevent concurrent workers. |

The regression suite covers provider success/failure paths, local fallback, schedule parsing, job state persistence/recovery, output files, Flask generation/scheduling routes, supervisor recovery/concurrency limits, and CLI errors. Tests do not make live network calls. CI has not yet been verified on GitHub.

## Remaining risks and limitations

- Provider behavior has not been validated using real credentials or current provider-side model access.
- Hugging Face inference availability and model compatibility depend on provider service support.
- Scheduler job state is persisted, and web workers use daemon threads and stop with the web process. Jobs can be recovered manually or by running the opt-in `--supervise-scheduled` CLI supervisor.
- Leases prevent concurrent workers per job within one SQLite database; the supervisor does not start automatically with the web app or machine and is not distributed coordination.
- Once generated output is persisted, recovery replays it to the same file without calling the generator again. A process failure before payload persistence may still repeat the provider call.
- Unexpected generator exceptions are retried up to three total attempts with 1- and 2-second delays; provider adapter fallback is treated as successful generation.
- Failed jobs can be retried explicitly with `--retry-job JOB_ID`; the command refuses jobs that are not failed.
- Uploaded file contents are not analyzed; web upload validation is extension-based and not malware/content inspection.
- No authentication, CSRF protection, rate limiting, or production deployment pipeline is provided.
- Logging currently reports provider fallback failures; comprehensive operational logs and monitoring are not implemented.

## Recommended next steps

1. Run credentialed smoke tests for supported providers and document verified model choices.
2. Verify GitHub Actions on a push or pull request and keep regression coverage current.
3. Configure the opt-in supervisor as an operating-system service/task if unattended recovery is required, and define provider outage behavior.
4. Add deployment controls, security protections, and operational monitoring before exposing the app beyond localhost.

## Overall conclusion

The app is a functional local prototype with improved Phase 1 validation and provider adapters. Its provider behavior is mock-verified rather than live-verified, and its scheduling, media handling, and deployment features remain prototype-level.
