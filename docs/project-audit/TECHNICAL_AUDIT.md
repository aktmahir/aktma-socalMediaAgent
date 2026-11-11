# Technical Audit

Audit date: 2026-11-11

## Architecture

The repository is a small Python monolith:

- `app.py` implements CLI generation and scheduler lifecycle commands.
- `social_media_agent/generator.py` builds provider requests, parses responses, and implements local-template fallback.
- `social_media_agent/web.py` configures Flask, CSRF, rate limiting, routes, uploads, request logging, readiness, and exception handling.
- `social_media_agent/media_analysis.py` performs bounded image/video parsing, optional ClamAV scanning, and vision-image preparation.
- `social_media_agent/scheduler.py` persists scheduled jobs, leases, retry state, and generated payloads in SQLite.
- `social_media_agent/observability.py` implements persistent request metrics, bounded local error records, structured logs, and optional Sentry reporting.
- `social_media_agent/templates/index.html` renders the web UI.
- `tests/` contains three standard-library `unittest` modules for provider/scheduler regressions, web/observability coverage, and media analysis.

The web app starts scheduled-job workers as daemon threads, which stop with the web process. Docker Compose also starts a separate supervisor using the same SQLite database and output volume; SQLite leases coordinate the workers and allow recovery after lease expiry, but do not provide distributed locking across separate databases or hosts.

## Provider integration status

- **OpenAI:** Uses the OpenAI SDK Chat Completions client. Initialization/request failures and malformed provider results fall back locally.
- **Hugging Face:** Uses HTTP requests with a 60-second timeout and handles HTTP/API error responses.
- **Cohere:** Uses the v2 Chat endpoint with a 60-second timeout, user message, and JSON response format.
- Provider behavior is covered by mocks. One credentialed smoke request per configured provider was attempted on 2026-11-11 using a generic, non-sensitive prompt. Each fell back to local generation: OpenAI returned an authentication error, Hugging Face a connection error, and Cohere an HTTP error. The configured credentials/model access and successful live response compatibility therefore remain unverified; credential values and provider response bodies were not recorded.
- Vision analysis uses OpenAI only after explicit per-upload opt-in. Media is prepared locally before transmission; the feature's output is a limited model-generated description, not verified ground truth.

## Input, files, and scheduling

The CLI, web form, and scheduler validate core topics, supported choices, interval units, and counts. Uploads are limited to 5 MB per file and the request body to 5 MB plus 256 KiB. Extension/signature and media-type checks precede storage under a random server-generated filename. Pillow rejects images above 20 million pixels before conversion and applies a bounded frame budget; FFprobe rejects video streams above 20 million pixels before FFmpeg sampling, which has subprocess timeouts and samples at most three frames. ClamAV is optional; scanner-unavailable/error states are reported as unscanned, while detected files are rejected. Parsing remains bounded rather than exhaustive, and sampled/provider-generated semantic descriptions are not guaranteed accurate or complete.

Residual local trust-boundary risks:

- Web-submitted schedule paths are resolved and confined to `SCHEDULED_OUTPUT_ROOT` (default: `scheduled_posts`); relative subfolders and absolute in-root paths are accepted. This guards against path escape through `..` and existing symlinks but does not replace authentication or protect against a hostile local process that can alter the configured root.
- Uploaded files remain in the uploads directory after successful analysis/generation; no automatic retention or cleanup policy is configured.
- Single-user authentication is configurable for local and Docker use; the local development runner can remain unauthenticated on loopback. Compose requires browser and Prometheus scrape credentials and publishes services only on loopback by default.

The scheduler persists jobs, retry attempts, next-run times, failures, and completed generation payloads in SQLite. Unexpected generator exceptions are retried up to three attempts with bounded delays; provider failures that return local fallback are treated as successful generation. Persisted payloads are replayed to the same output path after an interrupted progress update. If interruption occurs before payload persistence, provider generation may repeat. A 120-second lease is renewed every 20 seconds; coordination does not extend across separate databases or constitute distributed locking.

## Reliability and observability

- `GET /health` reports liveness.
- `GET /ready` checks metrics storage, upload-directory and scheduled-output-root writability, a configured session secret of at least 32 bytes, secure session cookies, disabled debug mode, and a healthy non-memory rate-limit backend. It creates the configured scheduled-output root if needed. With browser auth enabled, unauthenticated probes receive only the aggregate status; authenticated sessions receive individual check results. It does not check provider credentials, scheduler-worker availability, or Sentry delivery.
- `GET /metrics` renders SQLite-persisted request counters, duration histograms, and a cumulative unhandled-error counter that is independent of the bounded 1,000-row exception-detail retention. Metrics use bounded method/status labels; `/metrics` scrapes are excluded from request metrics and logging. Prometheus alerts on newly recorded unhandled errors.
- Scheduler status gauges read only the configured scheduler SQLite database, emit fixed status labels, and expose database availability separately; Prometheus alerts on failed jobs and missing scheduler metrics. The scheduler database path defaults to `SCHEDULED_OUTPUT_ROOT/scheduler.sqlite3`.
- Structured HTTP logs include request ID, method, matched route template (or `<unmatched>`), status, and duration; raw URL path values are not emitted. Unhandled exceptions log a traceback locally; SQLite retains at most 1,000 records containing timestamp, request ID, method, route template, and exception type, not raw URL values or exception messages.
- Browser authentication emits structured success and warning-level failure events correlated by request ID; usernames, passwords, and submitted form fields are not logged.
- Optional Sentry reporting is disabled without `SENTRY_DSN` and requires the `monitoring` extra. The scrubber drops request/user payloads, arbitrary event messages, breadcrumbs, local variables, and source context, and replaces exception text with its type. Sanitized stack frames still retain function names, line numbers, and source basenames. Sentry SDK/network delivery was not exercised in this audit.
- Alert notification delivery, an approved Sentry project, and external log-sink configuration remain operator responsibilities.

## Security and deployment

- CSRF protection uses Flask-WTF session tokens. Flask-Limiter applies a default 120 requests/hour and an additional 10 POSTs/minute on the generation/scheduling route. Health, readiness, and metrics are exempt. The default `memory://` limiter backend is process-local and unsuitable for multi-worker coordination.
- Configured browser login sessions are signed, `HttpOnly`, `SameSite=Lax`, and secure when HTTPS is enabled. HTTPS sessions use a host-only `__Host-` cookie with `Path=/` and no `Domain`; local HTTP retains the ordinary cookie name. Sessions have a fixed 12-hour maximum age; expiry is enforced from the login timestamp even if other session data is refreshed. Prometheus Basic-auth credentials remain independent of browser sessions.
- Docker Compose's app and scheduler run as the image's non-root `app` user with read-only root filesystems, all Linux capabilities dropped, `no-new-privileges`, and a 64 MiB `noexec`/`nosuid` `/tmp`. Redis runs as UID/GID 999:1000 with read-only root and bounded tmpfs storage (persistence is disabled), on a dedicated internal network shared only with the app; Prometheus runs as `nobody` with read-only root and a named data volume. Prometheus lifecycle control endpoints are disabled because config reload and shutdown are not needed by this stack. The CI smoke test inspects these runtime settings and network isolation.
- The optional Nginx TLS proxy also has a read-only root and drops all capabilities except `NET_BIND_SERVICE` (ports 80/443), `CHOWN` (Nginx initializes worker-owned cache directories), and `SETGID`/`SETUID` (Nginx drops worker privileges); it sets `no-new-privileges`, hides its version token, and uses bounded tmpfs mounts for generated config, cache, and runtime state. TLS mounts remain read-only. CI verifies the exact runtime capabilities, `nginx -t`, HTTPS readiness, version hiding, and redirects.
- Responses set a restrictive same-origin Content Security Policy, disable MIME sniffing and framing, limit referrer disclosure and unused device permissions, and add HSTS only when the request is HTTPS. HTML pages set `Cache-Control: no-store` to prevent cached authenticated content. The server-rendered pages use same-origin external stylesheets so the CSP does not permit inline styles or scripts.
- The launcher disables Flask debug mode and binds to `127.0.0.1`. A Gunicorn WSGI factory and loopback-only Docker Compose stack provide Redis-backed rate limiting, Prometheus scraping/alerts, secret-file mounts, and an optional Nginx TLS overlay. Multi-user authorization, a public production deployment pipeline, and a dedicated external secret manager/rotation process remain absent.
- GitHub Actions declares only `contents: read` token permission, pins third-party actions to verified full commit SHAs, and disables persisted Git credentials so test and dependency-install steps do not inherit them.
- `.env` is ignored by Git; local key generation and session invalidation on rotation are documented. This does not provide production secret storage or rotation.
- The readiness route is a configuration/dependency check, not a production deployment certification.

## Build and verification status

The documented regression command is:

```bash
python -m unittest discover -s tests -v
```

The current full suite discovers 131 tests and passed in the project virtual environment. The 126-test suite at GitHub Actions run 16 passed in a Python 3.9 container and on the Python 3.9–3.12 GitHub matrix; Python 3.9 dependency installation and `pip install .` also succeeded. The separate Docker monitoring job failed in that run and needs follow-up. Tests use mocks for providers and Sentry; no live provider or telemetry requests are made.

## Overall technical assessment

The project has broad local coverage for provider fallback, bounded media parsing, scheduler persistence/recovery, CSRF/rate limiting, and observability. Web schedule paths are confined to a configured output root, but CLI output paths remain operator-controlled. A manual GitHub Actions SSH deployment workflow, host-mounted Compose secret files, HTTP-01 webroot handling, and a Certbot proxy-recreation hook are provided as a self-hosted VM scaffold; no public VM deployment, external secret manager, or live certificate renewal has been verified. It is not production-certified: live provider behavior is unverified, multi-user authorization and external secret rotation are absent, local rate-limit storage remains process-local by default, malware scanning is optional, Sentry delivery is not live-verified, and alert routing is not configured.
