# Functional Audit

## Current status

As of 2026-11-11, the project provides local and Docker workflows for generating social media drafts through a CLI or server-rendered Flask interface. It supports OpenAI, Hugging Face, and Cohere adapters, a randomized local-template fallback, bounded local image/video analysis, optional OpenAI vision, and SQLite-backed scheduled JSON output with optional Docker supervisor recovery. Provider integrations are mock-tested; this audit did not make credentialed provider requests.

## Feature assessment

| Feature | Status | Evidence / limitation |
| --- | --- | --- |
| CLI generation | Implemented | `app.py` validates required topics and schedule arguments, generates drafts, and exposes scheduler lifecycle commands. |
| Platform-specific generation | Implemented | Platform choices and prompt descriptions cover Instagram, LinkedIn, Twitter, Facebook, YouTube, and YouTube Shorts. |
| OpenAI generation | Implemented; mock-tested | Uses the SDK client API. Credential, model-access, and live response behavior have not been verified. |
| Hugging Face generation | Implemented; mock-tested | Handles HTTP/API errors with a logged local fallback. The selected model must be available through the provider's current inference service. |
| Cohere generation | Implemented; mock-tested | Uses the v2 Chat endpoint and parses text content. Live API access has not been tested. |
| Local fallback | Implemented | Randomized templates produce drafts without a provider. Fallback output is identified so it is not mistaken for provider output. |
| Web generation and scheduling | Implemented; route-tested | Flask test-client tests cover generation, invalid inputs, upload handling, persisted schedule creation, and output-path confinement. Scheduled jobs run in daemon threads within the web process. |
| Input validation | Implemented for core fields | CLI, web, and scheduler validate topics, supported choices, intervals, counts, and uploads. This is not comprehensive abuse protection. |
| Media uploads and analysis | Partial | Files are limited to 5 MB, checked against allowlisted extensions/signatures and selected media type, stored under random names, and parsed with resource limits. Images and video streams above 20 million pixels are rejected before expensive conversion/decoding. Optional ClamAV scanning may report unscanned; external OpenAI vision requires an explicit per-upload opt-in and may be incomplete or incorrect. |
| Scheduling and recovery | Implemented for local and Docker use | SQLite persists job state, retry attempts, and generated payloads. CLI lifecycle controls, a Docker Compose supervisor, and an opt-in local supervisor are available; a Windows script can register current-user logon startup. Leases coordinate workers only when they use the same SQLite database. |
| Operational visibility | Implemented for local use | `/health`, `/ready`, and SQLite-persisted `/metrics` are available. Unhandled web exceptions are logged locally and stored as bounded, data-minimized records; optional Sentry reporting requires an SDK extra and configured DSN. |
| Automated tests and CI | Implemented; Python 3.9–3.12 test matrix and Docker monitoring passed | The current 135 tests passed on Windows and in GitHub Actions run 19 across Python 3.9–3.12. The Docker monitoring job passed authenticated scraping, scheduler metrics, alert-rule loading, and TLS/readiness checks. Provider and Sentry behavior remains mocked; tests make no live provider calls. |
| Production deployment | Partial | A Gunicorn WSGI factory and loopback-only Docker Compose stack provide single-user or invite-only multi-user auth, admin/user roles, per-user upload/scheduled-output isolation, Redis rate-limit storage, Prometheus monitoring, secret-file mounts, and optional Nginx TLS termination. Public production deployment, external secret management/rotation, and alert notification routing remain unimplemented. |

## Verified workflows

- CLI validation reports invalid topics and schedule arguments through argparse. The web form validates supported selections and schedule inputs and returns user-visible feedback.
- The scheduler rejects invalid direct-call arguments, persists jobs and output payloads, limits concurrent workers per job/database with expiring leases, retries unexpected generation exceptions up to three attempts, and supports explicit retry of terminal failures.
- A provider/API failure that returns local-template output is treated as a successful generation. `generation_source` distinguishes local fallback from provider output.
- Uploaded images and videos are parsed locally within configured pixel/frame/time limits. FFprobe and FFmpeg are required for video analysis. An unchecked-by-default option sends prepared image data to OpenAI vision.
- Session-backed CSRF protection and per-IP rate limits are enabled. Default limiter state is process-local; health, readiness, and metrics probes are exempt.
- Browser responses include a restrictive Content Security Policy and other security headers; HSTS is sent only for HTTPS requests.

## Known limitations and local trust boundaries

- The local generator is a template-based fallback, not an AI model. Credentialed provider behavior and provider-side model availability remain unverified.
- Local media observations are not exhaustive validation or reliable semantic interpretation. ClamAV may be unavailable; an unscanned result is not a safety guarantee.
- Web schedule output paths are confined to `SCHEDULED_OUTPUT_ROOT` (default: `scheduled_posts`), including after resolving `..` segments and existing symlinks. The root is operator-configurable and is not an authorization boundary against a hostile local process; do not expose the app without access controls.
- Web-created workers stop with the web process. Docker Compose runs a separate supervisor that recovers abandoned running jobs after lease expiry; local supervisor/task setup remains an explicit operator action.
- Optional single-user authentication remains available. Invite-only multi-user mode provides local SQLite accounts, admin/user role checks, and per-user upload and scheduled-output directories. It does not provide external identity providers, self-service password reset, or separate provider/resource quotas. CSRF protection and rate limiting alone do not provide identity or access control.
- Sentry reporting is opt-in. The event scrubber removes request/user payloads and arbitrary messages, but sanitized stack frames retain function names, line numbers, and source basenames. Local traceback logs contain exception details and require appropriate local access and retention controls.
- `/ready` checks metrics, upload, and scheduled-output storage plus selected configuration conditions. With browser auth enabled, unauthenticated probes receive only the aggregate state; individual check results require an authenticated session. It creates the configured scheduled-output root if needed. It does not verify provider credentials, scheduler-worker availability, or external monitoring delivery.

## Functional conclusion

The local draft-generation, upload-analysis, and scheduling workflows are available and covered by automated tests. Web-supplied schedule outputs are confined to the configured root; in multi-user mode they are further confined to the current user's directory. CLI output paths remain operator-controlled. The Docker sample adds single-user or opt-in multi-user authentication, TLS termination, monitoring, and scheduler supervision, but the project is not a complete public-production deployment. Live provider tests, external secret/certificate lifecycle, and alert routing remain outstanding.
