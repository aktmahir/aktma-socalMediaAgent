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
| ROAD-04: Automated tests and CI | Implemented; locally and remotely verified | 45 `unittest` cases pass locally; GitHub Actions run 1 passed its 34-test suite on Python 3.10, 3.11, and 3.12 for commit `20607d3`. |
| ROAD-05: Persistent scheduling | Implemented for local use | SQLite persists jobs, retry attempts, and generated payloads; CLI supports inspection, pause/resume/cancel, manual recovery through `--run-scheduled JOB_ID`, and expiring leases to prevent concurrent workers. |

The regression suite covers provider success/failure paths, local fallback, schedule parsing, job state persistence/recovery, output files, Flask generation/scheduling/upload validation, structured request and scheduler logs, supervisor recovery/concurrency limits, and CLI errors. Tests do not make live network calls. [The GitHub Actions run for commit `20607d3` passed all three Python matrix jobs](https://github.com/aktmahir/aktma-socalMediaAgent/actions/runs/41684526182).

## Remaining risks and limitations

- Provider behavior has not been validated using real credentials or current provider-side model access.
- Hugging Face inference availability and model compatibility depend on provider service support.
- Scheduler job state is persisted, and web workers use daemon threads and stop with the web process. Jobs can be recovered manually or by running the opt-in `--supervise-scheduled` CLI supervisor.
- Leases prevent concurrent workers per job within one SQLite database; the supervisor does not start automatically with the web app or machine and is not distributed coordination.
- Once generated output is persisted, recovery replays it to the same file without calling the generator again. A process failure before payload persistence may still repeat the provider call.
- Unexpected generator exceptions are retried up to three total attempts with 1- and 2-second delays; provider adapter fallback is treated as successful generation.
- Failed jobs can be retried explicitly with `--retry-job JOB_ID`; the command refuses jobs that are not failed.
- Web uploads are limited to 5 MB and checked against allowlisted extensions, initial file signatures, and selected media type; random server names prevent path control and accidental overwrite. Files are not analyzed, fully parsed, or malware-scanned.
- No authentication, CSRF protection, rate limiting, or production deployment pipeline is provided.
- JSON request/job lifecycle logs are emitted at INFO by CLI/web entry points, but metrics, centralized exception reporting, log retention, and production log-sink configuration are not implemented.

## Recommended next steps

1. Run credentialed smoke tests for supported providers and document verified model choices.
2. Keep regression coverage current as features land.
3. Configure the opt-in supervisor as an operating-system service/task if unattended recovery is required, and define provider outage behavior.
4. Add deployment controls, security protections, and operational monitoring before exposing the app beyond localhost.

## Overall conclusion

The app is a functional local prototype with improved Phase 1 validation and provider adapters. Its provider behavior is mock-verified rather than live-verified, and its scheduling, media handling, and deployment features remain prototype-level.
