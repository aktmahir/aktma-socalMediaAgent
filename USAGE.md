# Usage Guide

This guide covers installation and the supported CLI and web workflows.

## 1. Install

Create and activate a virtual environment, then install the application dependencies:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy the example environment file and configure the provider you intend to use:

```powershell
copy .env.example .env
```

Set `AI_PROVIDER` to `openai`, `huggingface`, or `cohere` and configure that provider's API key. Model settings are optional:

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
```

Hugging Face uses `HUGGINGFACE_API_KEY` and optionally `HUGGINGFACE_MODEL`. Cohere uses `COHERE_API_KEY` and optionally `COHERE_MODEL` (default: `command-a-03-2025`). The Cohere adapter uses the Cohere v2 Chat API. Choose the OpenAI model with `--openai-model`; `--provider-model` overrides the model for any selected provider. Do not commit real API keys.

For stable web sessions across restarts, generate a signing key:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Put the output in `.env` as `FLASK_SECRET_KEY=<generated-value>`. `.env` is ignored by Git; keep it private and do not paste secrets into logs or share them. Rotating this key invalidates existing sessions and CSRF tokens. This is local-file guidance, not production secret management.

The web upload form includes a separate, unchecked-by-default option for semantic vision descriptions. Selecting it sends the uploaded image, or up to three sampled video frames, to OpenAI using `OPENAI_API_KEY`; it uses `OPENAI_VISION_MODEL` when set and otherwise `gpt-4o-mini`. This works independently of `AI_PROVIDER`. Without that explicit per-upload selection, media remains local and is not sent to an AI service.

The app falls back to local generation when no provider key is configured or a provider request fails. Provider failures are logged. The CLI and web result identify local-template output so it is not mistaken for a response from the selected external provider. This fallback is useful for local development but does not confirm that an external provider is configured correctly.

Optional Sentry reporting can be installed without adding the SDK to the default dependencies:

```powershell
pip install ".[monitoring]"
```

Set `SENTRY_DSN` in `.env` to enable it and optionally set `SENTRY_ENVIRONMENT` (defaults to `development`). If no DSN is configured, no Sentry SDK is imported and no external events are sent. Before transmission, events are scrubbed of request and user data, breadcrumbs, arbitrary messages, local variables, and source context; exception messages are replaced by the exception type. Review organizational data handling requirements before enabling Sentry.

Optional: install the package to enable its console scripts:

```powershell
pip install .
```

## 2. Generate a post with the CLI

```powershell
python app.py --topic "launching a new product" --platform instagram --tone friendly --length medium
```

Available platform choices: `instagram`, `linkedin`, `twitter`, `facebook`, `youtube`, `youtube_shorts`.

Available media types: `text`, `image`, `video`. `--media-filename` adds a filename to the generation context; the CLI does not upload or analyze media.

Select a provider and optionally override its model:

```powershell
python app.py --topic "launching a new product" --ai-provider cohere --provider-model command-a-03-2025
```

If `--provider-model` is omitted, the selected provider's configured model is used. The OpenAI model is controlled by `--openai-model` (default `gpt-3.5-turbo`); Hugging Face and Cohere use their respective environment model variables or built-in defaults.

Generate YouTube metadata:

```powershell
python app.py --topic "new product launch" --platform youtube --media-type video --media-filename launch_clip.mp4
```

The generator rejects topics that are empty or whitespace-only.

## 3. Schedule generated posts

```powershell
python app.py --topic "weekly marketing tip" --platform instagram --interval 1d --count 7
```

- Interval units: `s` (seconds), `m` (minutes), `h` (hours), or `d` (days); the value must be positive.
- `--count` must be a non-negative integer. `0` means run indefinitely until stopped.
- Scheduled JSON files are written to `scheduled_posts/` by default; change this with `--scheduled-output`.
- Job records are stored in SQLite at `scheduled_posts/scheduler.sqlite3` by default. Override the database with `--scheduler-db PATH`.
- The scheduler validates interval seconds and count even when called directly.
- Unexpected generator exceptions are retried up to 3 attempts with 1- and 2-second delays; after exhaustion the job is marked failed and the error remains in SQLite. Provider/API/model failures currently use local template generation without an automatic provider retry, and the scheduled output JSON, console line, and lifecycle log identify the source as `local`. These fallback generations count as successful scheduled output; check `generation_source` when reviewing a generated file.

Manage jobs from another terminal:

```powershell
python app.py --list-scheduled
python app.py --pause-job JOB_ID
python app.py --resume-job JOB_ID
python app.py --cancel-job JOB_ID
python app.py --retry-job JOB_ID
```

If a process stops unexpectedly, list jobs to find a still-running job ID and recover it manually with:

```powershell
python app.py --run-scheduled JOB_ID
```

For automatic recovery while the CLI supervisor is running, scan all running jobs in the configured database:

```powershell
python app.py --supervise-scheduled --scheduler-poll-seconds 5 --max-scheduled-workers 4
```

The supervisor runs until Ctrl+C and starts up to the configured worker limit. Docker Compose starts a supervisor service automatically, sharing its scheduler database and output volume with the web app; it recovers abandoned jobs after their worker leases expire. On Windows, register the local supervisor to start at the current user's logon with the supplied Task Scheduler script:

```powershell
.\scripts\register-scheduler-supervisor.ps1 -PythonPath .venv\Scripts\python.exe -WhatIf
.\scripts\register-scheduler-supervisor.ps1 -PythonPath .venv\Scripts\python.exe
```

The first command previews the registration; omit `-WhatIf` to create the task. The task runs as the current user with limited privileges, starts at the next logon (not before sign-in), and uses the repository's `scheduled_posts\` directory and SQLite database by default. Pass `-StartNow` to start it immediately as well. If the web form uses another scheduled-output directory, pass the same absolute or repository-relative path with `-OutputDirectory`; pass `-DatabasePath` if the jobs use a custom database. The selected Python executable must have the project dependencies installed. The app loads provider settings from the repository `.env` file; the task does not store API keys in its command line.

To remove the task, run `.\scripts\register-scheduler-supervisor.ps1 -Unregister`. To view status, use `Get-ScheduledTask -TaskName "Social Media Agent Scheduler Supervisor"` and `Get-ScheduledTaskInfo -TaskName "Social Media Agent Scheduler Supervisor"`. The task is configured only for the current Windows user; logging out stops that user's process, and the next logon starts it again. The supervisor uses the same `--scheduler-db` and `--scheduled-output` paths as other scheduler commands.

For a job marked `failed` after exhausting its bounded generation retries, use `--retry-job JOB_ID` to clear the retry state and run it again. The command is rejected for jobs that are not in the `failed` state.

The SQLite lease rejects a second worker while one is active. The worker renews its 120-second lease every 20 seconds; if a process crashes, wait for the lease to expire before recovery. Generated payloads saved to SQLite are replayed to the same output file if progress recording was interrupted; a crash before saving the payload can still repeat generation. Resume a paused job with `--resume-job` first, then run `--run-scheduled JOB_ID` if its worker is no longer active. When managing a job created in the web UI with a custom output folder, pass that same folder through `--scheduled-output` (or provide the exact database path with `--scheduler-db`). Coordination is local to one SQLite database; this is not a distributed worker service.

## 4. Run the web interface

```powershell
python web.py
```

Open `http://127.0.0.1:5000`. The app listens on localhost and starts with Flask debug mode disabled.

For single-user access control, configure both `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD` in the process environment or `.env`; use a unique password of at least 16 characters. Authentication is disabled when neither is set, and startup fails if only one is configured. Browser login sessions expire after 12 hours and require signing in again. For Docker, set `WEB_HOST=0.0.0.0` and provide both credentials to the container; the app refuses a non-localhost bind without authentication. Protect the published port with your network configuration. Login and logout use CSRF-protected forms, and `/metrics` requires an authenticated session when login is enabled; `/health` and `/ready` stay public for orchestration.

Responses include a Content Security Policy, MIME-sniffing and framing protections, a restrictive referrer policy, and disabled camera/microphone/geolocation permissions. HTML pages use `Cache-Control: no-store` to prevent browsers from retaining authenticated content. HSTS is added only when Flask sees an HTTPS request, including through the explicitly trusted TLS proxy. HTTPS sessions use a host-only `__Host-` cookie with `Secure`, `HttpOnly`, `SameSite=Lax`, and a root path.

### Docker Compose

The Compose setup uses Gunicorn, a separate scheduled-job recovery supervisor, a shared Redis rate-limit backend, authenticated Prometheus scraping, and named volumes for scheduler state, scheduled outputs, uploads, and metrics history. The app, scheduler, Redis, and Prometheus run non-root with read-only root filesystems, dropped Linux capabilities, no-new-privileges, and bounded temporary storage. Redis is accessible only to the app through a dedicated internal network. The optional TLS proxy uses a read-only root filesystem and retains only the capabilities needed to bind its HTTP/HTTPS ports, initialize worker cache directories, and drop worker privileges. The stack binds the app and Prometheus UI to `127.0.0.1:8000` and `127.0.0.1:9090`.

1. Copy `.env.example` to `.env`.
2. Set `WEB_AUTH_USERNAME` in `.env`.
3. Create the git-ignored `secrets` directory and place a generated session key (at least 32 characters), a unique browser password (at least 16 characters), and a separate Prometheus password (at least 16 characters) in `flask_secret_key.txt`, `web_auth_password.txt`, and `prometheus_password.txt`, respectively. Add provider keys to `openai_api_key.txt`, `huggingface_api_key.txt`, and `cohere_api_key.txt`; unused provider files may be empty. Keep the files private; Compose mounts each read-only into the services that need it.
4. Run `docker compose up --build`, then open `http://127.0.0.1:8000`.
5. View alert state at `http://127.0.0.1:9090/alerts`.

The local sample uses HTTP and non-secure cookies, so `/ready` intentionally reports not-ready. Do not expose it beyond loopback. Compose file-backed secrets are read-only mounts, not encrypted storage; protect their host files with OS permissions and use your deployment platform's secret manager for production. For deployment behind HTTPS, configure the trusted TLS-terminating reverse proxy and set `SESSION_COOKIE_SECURE=true`. The WSGI entry point refuses to start without browser authentication, Prometheus scrape authentication, a stable session secret, and shared rate-limit storage. One Gunicorn worker is configured because scheduled jobs start in-process from web requests; a separate Compose supervisor coordinates through SQLite leases and recovers interrupted jobs after the 120-second lease expires.

To use the bundled Nginx TLS proxy locally, first create a self-signed certificate (for local testing only):

```powershell
New-Item -ItemType Directory -Force secrets
docker run --rm --mount "type=bind,source=$((Get-Location).Path)\secrets,target=/certs" nginx:1.28-alpine sh -c "apk add --no-cache openssl && openssl req -x509 -nodes -days 365 -newkey rsa:3072 -keyout /certs/tls.key -out /certs/tls.crt -subj /CN=localhost -addext subjectAltName=DNS:localhost,IP:127.0.0.1"
docker compose -f docker-compose.yml -f docker-compose.tls.yml up --build
```

The TLS overlay requires Compose v2.24 or newer. Open `https://localhost:8443`; the browser will warn because the local certificate is self-signed. Requests to port 8080 redirect to HTTPS. The overlay disables the app's published HTTP port, sets secure cookies, and enables exactly one trusted proxy hop from Nginx's fixed private IP. The app ignores forwarded headers from all other peers, and Nginx overwrites those headers from the connection rather than trusting client-provided values. TLS binds to loopback by default; changing `TLS_BIND_ADDRESS` changes network exposure and should be done only intentionally. The overlay reserves `172.30.252.0/24`; if that conflicts with an existing Docker network, change the overlay's proxy subnet and matching trusted proxy IP together. For domain deployments, supply a certificate/key with matching subject names, set `TLS_HTTPS_PORT` to the externally published HTTPS port, and configure external network access, TLS renewal, and secret storage separately.

Prometheus scrape requests use their own HTTP Basic credentials and do not rely on a browser login session. Rules alert on an unavailable scrape target, a sustained 5xx rate above 5%, p95 latency above 2 seconds, an unavailable scheduler database, failed scheduled jobs, or newly recorded unhandled application errors. The cumulative application-error counter persists across restarts; detailed exception records remain bounded to the most recent 1,000. Scheduler status metrics use `SCHEDULER_DB_PATH`; without it, the default is `SCHEDULED_OUTPUT_ROOT/scheduler.sqlite3`. Alerts are visible in Prometheus; notification routing is left for the deployment operator to configure.

Outside Compose, use `FLASK_SECRET_KEY_FILE`, `WEB_AUTH_PASSWORD_FILE`, `PROMETHEUS_PASSWORD_FILE`, and the corresponding provider `*_API_KEY_FILE` variables to read values from mounted secret files. The plain environment-variable forms remain available for local development; provider keys use the file form when both are set.

For production VM deployment and certificate renewal guidance, see the self-hosted VM deployment section in `README.md`.

The form validates the topic, supported select values, uploaded file extensions and signatures, schedule interval, and post count. Uploads are limited to 5 MB each. Scheduling creates a SQLite job and starts a background thread in the current process; closing the process stops that worker but preserves its job record for CLI recovery. A status message includes the job ID for validation or scheduler feedback.

Web schedules are confined to `SCHEDULED_OUTPUT_ROOT`, which defaults to `scheduled_posts`. Set this environment variable to a trusted local directory when a different root is needed. The form accepts relative subfolders or absolute paths that resolve inside the root; leave the field blank to use the root itself. When managing a web-created job from the CLI, use its resolved output folder with `--scheduled-output` and, if needed, its SQLite database path with `--scheduler-db`.

For request monitoring, scrape `http://127.0.0.1:5000/metrics`. It returns Prometheus text-format request totals and duration histograms by bounded HTTP method and status code; the scrape endpoint itself is excluded. Aggregates persist in SQLite across restarts. The default database is `scheduled_posts/observability.sqlite3`; set `OBSERVABILITY_DB_PATH` to change it.

The `http://127.0.0.1:5000/health` endpoint returns `{"status":"ok"}` when the Flask application is serving requests. It is a liveness check only. `http://127.0.0.1:5000/ready` checks observability/upload/scheduled-output storage, authentication, production session settings, debug mode, and shared rate-limit storage. When browser authentication is configured, unauthenticated probes receive only the overall ready/not-ready status; authenticated sessions can view individual check results. It does not verify provider credentials or scheduler-worker availability.

Logs are written to stderr by default. To retain local application logs, set `APP_LOG_FILE` to a file path; `APP_LOG_MAX_BYTES` (default 10 MiB) controls rotation size and `APP_LOG_BACKUP_COUNT` (default 3) controls the number of rotated files. Invalid limits fail startup rather than silently disabling rotation. Docker Compose uses the `json-file` driver with a 10 MiB size and three-file retention limit for stdout/stderr.

To pass readiness checks in a deployment, configure browser and Prometheus scrape authentication, a stable `FLASK_SECRET_KEY` with at least 32 bytes, `SESSION_COOKIE_SECURE=true` when serving over HTTPS, and a healthy shared `RATELIMIT_STORAGE_URI` backend (the default `memory://` is intentionally not production-ready). When using a reverse proxy, set `TRUSTED_PROXY_HOPS` to the exact number of trusted proxies and `TRUSTED_PROXY_IP` to the immediate proxy peer's exact IP; the app drops forwarded headers from other peers. Both settings default to disabled, so forwarded headers are ignored by default. The TLS Compose overlay configures these values for its fixed Nginx address and removes the app's host-published HTTP port. Install and configure the selected Flask-Limiter storage backend for the deployment. These checks do not replace production WSGI/server configuration.

Unexpected web exceptions return a generic message with an `X-Request-ID` reference. Full traceback details go to application logs; a bounded SQLite table stores only the timestamp, request ID, method, matched route template (or `<unmatched>`), and exception type. Raw URL values are not included in structured request or persisted error records. When configured, Sentry receives scrubbed unhandled web exceptions with the request ID as a correlation tag; capture failures are logged while local reporting continues.

## 5. Uploads and media limitations

The web form accepts image extensions `png`, `jpg`, `jpeg`, `gif` and video extensions `mp4`, `mov`, `avi`, `webm`, `m4v`. Each upload is limited to 5 MB and its initial file signature must match its extension and selected media type. Images and video streams above 20 million pixels are rejected before pixel conversion or frame decoding. Files are stored under random server-generated names in the repository's `uploads/` directory, so an uploaded name cannot overwrite another file or control its storage path. Invalid submissions are rejected before the upload is written.

Before parsing, the app uses `clamscan` when it is available on `PATH`. Detected files are rejected and removed. If ClamAV is unavailable or cannot complete a scan, the upload remains usable but its result is explicitly labeled **unscanned**; a clean result means only that ClamAV reported no detection. Install and maintain ClamAV and its signature database separately; the app does not install or update it.

Images are decoded locally with Pillow for dimensions after EXIF orientation, format, color mode, EXIF tag names, GPS-metadata presence (coordinates are not exposed), ICC profile/DPI presence, and bounded animation/frame metadata. Every frame must decode within configured pixel/frame limits, and the decoded format must match the extension. Videos require `ffprobe` for container, duration, file size/bitrate, video and audio stream codecs, dimensions, timing, pixel/aspect formats, rotation, and audio layout metadata; `ffmpeg` samples up to three low-resolution frames at 10-second intervals. The parsed container must match the selected extension and include a valid video stream. Missing tools or decode/metadata errors are reported and the uploaded file is removed. Local observations are passed as context and saved with scheduled job configuration. If the vision option is checked, the image or sampled video frames are sent to OpenAI and its description is passed to generation and saved in the scheduled configuration. Vision output may be incomplete or inaccurate, and video sampling does not inspect every frame. This bounded parsing is not exhaustive validation or a guarantee of safety; optional ClamAV scanning and keep-the-web-app-local guidance still apply.

## 6. Run regression tests

From the repository root:

```powershell
python -m unittest discover -s tests -v
```

Tests use mocks for provider requests and do not call external provider APIs. Live provider integration still requires valid credentials and provider-side model access.

## Troubleshooting

- CLI and web entry points emit timestamped logs to stderr. Web request and scheduler lifecycle records use JSON messages with request/job IDs and status information; prompts, credentials, and upload contents are excluded from structured request/job records. Unhandled web exceptions are logged with a traceback and request ID; `/metrics` exposes persistent request counts and latency aggregates without route paths or request IDs.
- Confirm the virtual environment is active and dependencies are installed.
- Confirm `AI_PROVIDER` and the selected provider's API key are set if AI-provider generation is expected.
- A provider request failure is logged and returns a local fallback post; inspect application logs when diagnosing provider connectivity, authentication, or model errors.
- Use a positive interval such as `30m` and a non-negative integer count.
- Unsupported extensions, mismatched signatures/media types, multiple files, and uploads over 5 MB are rejected. Uploaded files are stored locally under `uploads/` with generated names.
