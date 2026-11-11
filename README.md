# aktma-socalMediaAgent

AI-powered Social Media Post Generator in Python.

## Overview

This project creates social media posts automatically using OpenAI, Hugging Face, or Cohere when the selected API key is available, with a local fallback generator otherwise. It supports Instagram, LinkedIn, Twitter, Facebook, YouTube video posts, and YouTube Shorts.

## Installation

1. Create a virtual environment:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file from the example:

   ```bash
   copy .env.example .env
   ```

4. Configure the provider you want to use in `.env`. Only that provider's key is needed:

   ```bash
   AI_PROVIDER=openai
   OPENAI_API_KEY=your_api_key_here
   # Or set AI_PROVIDER=huggingface and configure HUGGINGFACE_API_KEY/HUGGINGFACE_MODEL
   # Or set AI_PROVIDER=cohere and configure COHERE_API_KEY/COHERE_MODEL
   ```

For OpenAI, select a model with the CLI `--openai-model` option. Hugging Face and Cohere use their provider-specific model environment variables, which can be overridden with `--provider-model`.

For stable web sessions across restarts, generate a signing key and add it to `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Set `FLASK_SECRET_KEY` to the generated value. `.env` is ignored by Git; keep it private and do not paste it into logs or share it. Changing this key invalidates existing sessions and CSRF tokens. This local-file setup is not a production secret manager.

5. Install the package locally (optional):

   ```bash
   pip install .
   ```

For optional Sentry exception reporting, install the monitoring extra:

```bash
pip install ".[monitoring]"
```

Set `SENTRY_DSN` and optionally `SENTRY_ENVIRONMENT` in `.env` to enable sending unhandled web exceptions to your Sentry project. Reporting is disabled when no DSN is configured. Events omit request/user data, breadcrumbs, arbitrary messages, local variables, and source context; exception messages are replaced with the exception type. Review your organization's data policy before enabling an external service.

## Usage

Generate a social media post from the command line:

```bash
python app.py --topic "launching a new product" --platform instagram --tone friendly --length medium
```

Use a different AI provider with `--ai-provider` and `--provider-model`:

```bash
python app.py --topic "launching a new product" --platform instagram --tone friendly --length medium --ai-provider huggingface --provider-model gpt2
```

For Cohere, configure `AI_PROVIDER=cohere` and `COHERE_API_KEY` in `.env`, or select it with `--ai-provider cohere`. `COHERE_MODEL` supplies the default Cohere model; `--provider-model` overrides it. The Cohere adapter uses the v2 Chat API. Hugging Face model availability depends on the configured model and the provider's current inference API.

Generate a YouTube video post:

```bash
python app.py --topic "new product launch" --platform youtube --media-type video --media-filename launch_clip.mp4 --tone motivational --length medium
```

Generate a YouTube Shorts caption:

```bash
python app.py --topic "quick launch tip" --platform youtube_shorts --media-type video --media-filename short_clip.mp4 --tone friendly --length short
```

## Periodic Generation

Generate and save post drafts automatically at a fixed interval:

```bash
python app.py --topic "weekly marketing tip" --platform instagram --media-type image --media-filename creative.jpg --tone educational --length medium --interval 1d --count 7
```

- `--interval 1d` means once every day.
- `--count 7` generates 7 scheduled post drafts; it does not publish to a social network.
- `--count 0` runs indefinitely until stopped.
- Scheduled post files are saved under `scheduled_posts/` by default.
- Job records are persisted in `scheduled_posts/scheduler.sqlite3` by default.
- Intervals must be positive values followed by `s`, `m`, `h`, or `d`; post counts must be non-negative integers.
- Unexpected generator exceptions are retried up to 3 attempts with 1- and 2-second delays; exhausted jobs are marked failed with the last error. Provider adapter failures that return the local fallback are treated as successful generation.

Manage persisted jobs from another terminal:

```bash
python app.py --list-scheduled
python app.py --pause-job JOB_ID
python app.py --resume-job JOB_ID
python app.py --cancel-job JOB_ID
python app.py --retry-job JOB_ID
```

Use `--retry-job JOB_ID` to explicitly restart a job that reached `failed` after exhausting its generation attempts. It clears that iteration's retry count/error and runs the job again. The SQLite lease prevents two live workers from running the same job. A worker renews its 120-second lease every 20 seconds; if a process crashes, wait for the lease to expire before recovering. Recover one job manually with `python app.py --run-scheduled JOB_ID`, or run the opt-in local supervisor to scan and recover all running jobs:

```bash
python app.py --supervise-scheduled --scheduler-poll-seconds 5 --max-scheduled-workers 4
```

The supervisor runs until stopped with Ctrl+C, scans the configured SQLite database, and starts up to the worker limit. It can recover persisted running jobs after their old worker leases expire. The Docker Compose stack runs a separate supervisor service automatically; local installs can configure an operating-system service/task for unattended recovery. A paused job must be resumed before it will run. Generated payloads saved to SQLite are replayed to the same output file if progress recording was interrupted, avoiding another generator call. A crash before the payload is saved can still repeat generation. Use `--scheduler-db PATH` when the database is not at its default location. If the web form used a custom scheduled-output folder, pass the same folder with `--scheduled-output` when managing jobs. Coordination is local to the SQLite database and is not a distributed worker service.

## Web Interface

Run the Flask web interface locally:

```bash
python web.py
```

Then open `http://127.0.0.1:5000` in your browser.

The web UI includes scheduling controls for interval, post count, and output folder. Web schedules are confined to `SCHEDULED_OUTPUT_ROOT`, which defaults to `scheduled_posts`; set that environment variable to choose a different trusted root, and enter a relative subfolder in the form. Absolute paths are accepted only when they resolve inside the configured root. Leave the field blank to use the root itself. When you submit a schedule, the app starts generating drafts in the background, stores the job in SQLite, and saves drafts under the selected output folder; it does not publish to a social network. The job ID is shown in the status message and can be managed with the CLI.
Invalid topics, unsupported form selections, file types, counts, and intervals are rejected with status feedback. The scheduler itself also rejects non-positive intervals and negative counts.

Web forms use session-backed CSRF tokens. Application routes are limited to 120 requests per hour per client IP, login submissions to 5 per minute, and generation/scheduling submissions to 10 POST requests per minute; health and readiness probes are exempt for reliable monitoring. The default limiter store is in-memory and process-local; set `RATELIMIT_STORAGE_URI` to a shared Flask-Limiter storage URI when running multiple workers. The local `.env` setup above provides a stable session key; changing this key invalidates existing sessions and CSRF tokens.

Responses include a Content Security Policy, MIME-sniffing and framing protections, a restrictive referrer policy, and disabled camera/microphone/geolocation permissions. HTML pages use `Cache-Control: no-store` to prevent browsers from retaining authenticated content. HSTS is added only when Flask sees an HTTPS request, including through the explicitly trusted TLS proxy. HTTPS sessions use a host-only `__Host-` cookie with `Secure`, `HttpOnly`, `SameSite=Lax`, and a root path.

To enable single-user authentication for local or Docker use, set both `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD` in the process environment or `.env`; the password must be at least 16 characters. The login form is rate-limited, credentials are compared without ordinary string equality, and protected routes (including `/metrics`) require a session. Browser login sessions expire after 12 hours and require signing in again. `/health` and `/ready` remain public for orchestration probes. Authentication is disabled when neither variable is set, so the development server refuses to bind beyond localhost unless you explicitly configure credentials. For a standalone container, set `WEB_HOST=0.0.0.0` and configure credentials; the Docker Compose setup binds only to loopback. `/ready` reports not-ready until authentication, a stable session secret, HTTPS secure cookies, writable storage, and shared rate-limit storage are configured.

### Docker

The Docker Compose setup runs the app behind Gunicorn, a separate scheduled-job recovery supervisor, Redis for shared rate limits, and Prometheus for authenticated app-metric scraping. The app, scheduler, Redis, and Prometheus run non-root with read-only root filesystems, no Linux capabilities, and bounded temporary storage; persistent application data is restricted to named volumes. Redis is accessible only to the app through a dedicated internal network. The optional TLS proxy also uses a read-only root filesystem and retains only the capabilities needed to bind ports 80/443, initialize worker cache directories, and drop worker privileges. The stack publishes the app and Prometheus UI only on loopback (`127.0.0.1:8000` and `127.0.0.1:9090`) and stores scheduler state, scheduled posts, uploads, and Prometheus data in named volumes.

1. Copy `.env.example` to `.env`, then set `WEB_AUTH_USERNAME`.
2. Create the git-ignored `secrets` directory and put the following values in separate files (one value per file): `flask_secret_key.txt` (generated, at least 32 characters), `web_auth_password.txt` and `prometheus_password.txt` (at least 16 characters each), and the provider key files `openai_api_key.txt`, `huggingface_api_key.txt`, and `cohere_api_key.txt` (leave unused provider files empty). Keep these files private; Compose mounts them as read-only Docker secrets only into services that need them.
3. Start the services with `docker compose up --build`.
4. Open `http://127.0.0.1:8000`; sign in using the configured credentials.
5. Inspect Prometheus alerts at `http://127.0.0.1:9090/alerts`.

The local Compose configuration defaults to non-secure session cookies because it serves plain HTTP on loopback; `/ready` intentionally remains not-ready until HTTPS and `SESSION_COOKIE_SECURE=true` are configured. Do not expose this HTTP setup to a network. Compose file-backed secrets are read-only mounts, not encrypted storage; protect their host files with OS permissions and use your deployment platform's secret manager for production. For TLS deployments, put the app behind a trusted HTTPS reverse proxy and set `SESSION_COOKIE_SECURE=true`. The `production` extra installs Gunicorn and Redis support. The WSGI factory refuses to start without browser authentication, Prometheus scrape credentials, a stable session secret, and shared rate-limit storage. The Docker Compose stack runs a separate supervisor against the same SQLite database and volume as the web app; it coordinates with web-started workers through database leases and recovers abandoned running jobs after their 120-second leases expire. Run one Gunicorn worker because web-scheduled jobs still start in-process.

For an optional bundled Nginx TLS proxy, create a local self-signed certificate and key (for local testing only; this command requires OpenSSL):

```bash
mkdir -p secrets
openssl req -x509 -nodes -days 365 -newkey rsa:3072 \
  -keyout secrets/tls.key -out secrets/tls.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
docker compose -f docker-compose.yml -f docker-compose.tls.yml up --build
```

Compose v2.24 or newer is required for the TLS overlay. Open `https://localhost:8443` and sign in; a browser warning is expected for a self-signed certificate. HTTP on port 8080 redirects to HTTPS. The overlay removes the app's published HTTP port, enables secure session cookies, and configures one trusted proxy hop from Nginx's fixed private IP. The app drops forwarded headers from any other peer, and Nginx replaces them with values from the actual connection rather than preserving client-supplied forwarding chains. The overlay reserves Docker subnet `172.30.252.0/24`; if it conflicts with another network, change the subnet and matching proxy IP together. The TLS listener binds to loopback by default; use `TLS_BIND_ADDRESS` only when intentionally changing network exposure. For a real domain, provide a certificate and private key with matching subject names, protect the key file, configure the external HTTPS port with `TLS_HTTPS_PORT`, and configure network/firewall access deliberately. This local sample is not a complete public-production setup.

### Self-hosted production VM

The repository includes a manual GitHub Actions deployment workflow at `.github/workflows/deploy-production.yml`. It only deploys `main` after an explicit confirmation, runs the test suite and Compose configuration checks first, transfers an immutable release over SSH using a pinned `DEPLOY_KNOWN_HOSTS` value, starts the TLS Compose stack, and checks the public `/ready` endpoint. Configure a protected GitHub Environment named `production`, require reviewers there, and add:

- Environment secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_PRIVATE_KEY`, and `DEPLOY_KNOWN_HOSTS` (verified host-key line from an independent trusted source; do not generate trust by running `ssh-keyscan` in the workflow).
- Environment variables: `DEPLOY_PATH` (absolute path without spaces, such as `/opt/social-media-agent`), `DEPLOY_PORT` (optional; defaults to `22`), and `APP_DOMAIN` (the public DNS name).

Before dispatching the workflow, prepare a Linux VM with Docker Engine and the Compose plugin, `rsync`, `curl`, `certbot`, and OpenSSL. Configure the deployment user for Docker access, DNS A/AAAA records, and a firewall that allows inbound TCP 80/443 only as intended. The deployment user must be able to create releases under `DEPLOY_PATH`; membership in the Docker group grants root-equivalent control of the host.

Create `/etc/social-media-agent/.env` and `/etc/social-media-agent/secrets/` on the VM. Set `WEB_AUTH_USERNAME`, `TLS_BIND_ADDRESS=0.0.0.0`, `TLS_HTTPS_PORT=443`, `TLS_HTTP_PORT=80`, and `CERTBOT_WEBROOT=/var/lib/letsencrypt/www` in the environment file; configure `AI_PROVIDER` and model settings as needed. Place `flask_secret_key.txt`, `web_auth_password.txt`, `prometheus_password.txt`, `openai_api_key.txt`, `huggingface_api_key.txt`, and `cohere_api_key.txt` in the secrets directory. Generate a unique session key and strong passwords; unused provider key files may be empty. Restrict the config directory to root and the deployment account (for example, mode `0750` on directories and `0640` on files). Do not put secret contents in GitHub variables, workflow logs, or the repository.

These are Docker Compose file-backed secrets, not an external vault: they are protected by VM filesystem permissions but are not encrypted at rest by Compose. Rotate a secret by atomically replacing its file with restricted permissions, then recreate the consuming services; for provider keys use `docker compose ... up -d --force-recreate app scheduler`. Rotate `flask_secret_key.txt` to invalidate browser sessions. For managed, audited, or centrally rotated secrets, integrate a host-side secret manager before treating the service as production-ready.

For initial TLS, create the webroot and secret directories. Use a temporary self-signed certificate only to start the first proxy; replace it with a publicly trusted certificate before using the service:

```sh
sudo install -d -m 0755 /var/lib/letsencrypt/www
sudo install -d -m 0750 /etc/social-media-agent/secrets
sudo openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
  -keyout /etc/social-media-agent/secrets/tls.key \
  -out /etc/social-media-agent/secrets/tls.crt \
  -subj "/CN=YOUR_PUBLIC_DOMAIN"
sudo chmod 0640 /etc/social-media-agent/secrets/tls.key \
  /etc/social-media-agent/secrets/tls.crt
```

Dispatch the deployment workflow after DNS and firewall setup, then issue the real certificate with Certbot HTTP-01 webroot validation (replace the domain and email placeholders):

```sh
APP_DOMAIN=YOUR_PUBLIC_DOMAIN
CERTBOT_EMAIL=YOUR_EMAIL_ADDRESS
sudo install -d -m 0755 /var/lib/letsencrypt/www
sudo certbot certonly --webroot -w /var/lib/letsencrypt/www \
  -d "$APP_DOMAIN" -m "$CERTBOT_EMAIL" --agree-tos --no-eff-email
sudo ln -sfn "/etc/letsencrypt/live/$APP_DOMAIN/fullchain.pem" \
  /etc/social-media-agent/secrets/tls.crt
sudo ln -sfn "/etc/letsencrypt/live/$APP_DOMAIN/privkey.pem" \
  /etc/social-media-agent/secrets/tls.key
```

Install a deploy hook that calls the included `scripts/renew-production-tls.sh`:

```sh
sudo tee /etc/letsencrypt/renewal-hooks/deploy/20-social-media-agent.sh >/dev/null <<'EOF'
#!/bin/sh
DEPLOY_PATH=/opt/social-media-agent
export DEPLOY_PATH
exec sh /opt/social-media-agent/current/scripts/renew-production-tls.sh
EOF
sudo chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/20-social-media-agent.sh
sudo DEPLOY_PATH=/opt/social-media-agent sh \
  /opt/social-media-agent/current/scripts/renew-production-tls.sh
sudo systemctl enable --now certbot.timer
sudo certbot renew --dry-run
```

The hook recreates only the TLS proxy so Docker re-resolves the renewed certificate symlinks. Confirm the renewed certificate is served after a real renewal. Keep the workflow manual until the VM, credentials, DNS, access controls, secret permissions, and certificate renewal have been verified. This is a deployment scaffold, not a claim that a public production deployment has been completed.

Prometheus alert rules flag an unavailable metrics target, a sustained 5xx response rate above 5%, p95 request latency above 2 seconds, an unavailable scheduler database, failed scheduled jobs, or newly recorded unhandled application errors. The unhandled-error counter persists across app restarts while the detailed event table retains only its most recent 1,000 records. Scheduler job counts are read from the configured SQLite scheduler database (`SCHEDULER_DB_PATH`, defaulting to `SCHEDULED_OUTPUT_ROOT/scheduler.sqlite3`). Alerts are visible in the local Prometheus UI; notification delivery (email, PagerDuty, or webhook) is not configured by default.

For deployments outside Compose, set `FLASK_SECRET_KEY_FILE`, `WEB_AUTH_PASSWORD_FILE`, and `PROMETHEUS_PASSWORD_FILE` to mounted secret-file paths; the corresponding direct environment variables remain supported for local development. Do not configure both forms for the same secret.

`GET /health` is a liveness probe. `GET /ready` is a production-readiness probe that returns HTTP 503 unless the observability SQLite database, upload directory, and scheduled-output root are writable, browser and Prometheus scrape authentication are configured, `FLASK_SECRET_KEY` is configured with at least 32 bytes, `SESSION_COOKIE_SECURE=true` is set, Flask debug mode is off, and rate limiting uses a healthy shared backend. It creates the configured scheduled-output root if needed. When authentication is enabled, unauthenticated probes receive only the overall status; individual check details are visible only to an authenticated session. `/metrics` serves Prometheus counters and latency histograms persisted in SQLite across restarts; when `PROMETHEUS_USERNAME` and `PROMETHEUS_PASSWORD` are configured, scrapes use HTTP Basic authentication. The database defaults to `scheduled_posts/observability.sqlite3` and can be changed with `OBSERVABILITY_DB_PATH`; `http_request_metrics` and `application_errors` are the metric/error-event tables.

Unhandled web exceptions are associated with the response's `X-Request-ID`, recorded in the same SQLite database (up to 1,000 recent events), and logged with a traceback for local operational diagnosis. Persisted error records contain the request ID, method, matched route template (or an `<unmatched>` marker), exception type, and timestamp—not raw URL values, exception messages, request bodies, or credentials. Structured request logs also use route templates rather than raw URLs. By default, logs go to stderr. Set `APP_LOG_FILE` to enable a size-rotated local log file; `APP_LOG_MAX_BYTES` defaults to 10 MiB and `APP_LOG_BACKUP_COUNT` to 3. In Docker Compose, stdout/stderr are retained in three 10 MiB files by the container logging driver. Sentry reporting is optional and disabled without `SENTRY_DSN`; when enabled, an event scrubber removes request/user data, arbitrary messages, breadcrumbs, local variables, and source context before transmission.

If the package is installed, use the console entry point:

```bash
aktma-socalmediaagent-web
```

## Upload support

The Web UI accepts allowlisted image and video uploads up to 5 MB each. It checks that the file's initial signature matches the extension and selected media type, then stores it under a random server-generated name to prevent path control and accidental overwrites. Images and video streams above 20 million pixels are rejected before pixel conversion or frame decoding. Media is otherwise parsed locally for bounded format, metadata, and visual observations; ClamAV scanning is optional and may report files as unscanned. By default, file bytes are not sent to providers. The explicit OpenAI vision opt-in described above sends an image or sampled video frames externally. These checks are not exhaustive validation or a safety guarantee, and sampled or model-generated descriptions may be incomplete or incorrect; the upload workflow is intended for local use, not public exposure.

Supported media types:
- `text`
- `image`
- `video`

Supported platforms include YouTube video posts and YouTube Shorts.

## Features

- `SocialMediaPostGenerator` Python class for integration
- CLI interface via `app.py`
- OpenAI-powered generation when `OPENAI_API_KEY` is present
- Hugging Face and Cohere request adapters with provider credentials in request headers
- Local fallback generation when API access is unavailable
- Provider errors are logged and fall back to local generation
- Hashtag creation and call-to-action support
- YouTube video metadata generation: title, description, and tags
- Input and scheduling validation across the CLI, web app, and scheduler
- Optional single-user web authentication with CSRF-protected login/logout
- SQLite-backed scheduled job records with CLI inspection, pause, resume, cancel, and recovery
- Regression tests runnable with Python's built-in `unittest` runner

## Validation

Run the regression tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

Provider behavior is covered by mocked tests. A credentialed smoke request was attempted for each configured provider on 2026-11-11; all three fell back locally (OpenAI authentication error, Hugging Face connection error, Cohere HTTP error). Successful live access therefore remains unverified; credential values and provider response bodies were not recorded.

## Continuous integration

The repository includes a GitHub Actions workflow that installs the app dependencies and runs the full unittest suite across supported Python versions. A Docker integration job also builds the Compose application stack, verifies the authenticated Prometheus scrape, and checks that all alert rules load on every push and pull request. The CI entry point is:

- `.github/workflows/python-tests.yml`

This keeps the Phase 1 and Phase 2 regression checks reproducible across supported Python versions.

## Extending

You can integrate this generator into other projects by importing it:

```python
from social_media_agent import SocialMediaPostGenerator

generator = SocialMediaPostGenerator()
post = generator.generate_post(
    topic="sustainable design",
    platform="instagram",
    tone="motivational",
    length="medium",
    language="English",
)
print(post)
```
