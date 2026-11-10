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

5. Install the package locally (optional):

   ```bash
   pip install .
   ```

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

The supervisor runs until stopped with Ctrl+C, scans the configured SQLite database, and starts up to the worker limit. It can recover persisted running jobs after their old worker leases expire, but it does not automatically start when the web app or machine starts; configure an operating-system service/task if unattended operation is needed. A paused job must be resumed before it will run. Generated payloads saved to SQLite are replayed to the same output file if progress recording was interrupted, avoiding another generator call. A crash before the payload is saved can still repeat generation. Use `--scheduler-db PATH` when the database is not at its default location. If the web form used a custom scheduled-output folder, pass the same folder with `--scheduled-output` when managing jobs. Coordination is local to the SQLite database and is not a distributed worker service.

## Web Interface

Run the Flask web interface locally:

```bash
python web.py
```

Then open `http://127.0.0.1:5000` in your browser.

The web UI includes scheduling controls for interval, post count, and output folder. When you submit a schedule, the app starts generating drafts in the background, stores the job in SQLite, and saves drafts under the selected output folder; it does not publish to a social network. The job ID is shown in the status message and can be managed with the CLI.
Invalid topics, unsupported form selections, file types, counts, and intervals are rejected with status feedback. The scheduler itself also rejects non-positive intervals and negative counts.

Web forms use session-backed CSRF tokens. Application routes are limited to 120 requests per hour per client IP, and generation/scheduling submissions are additionally limited to 10 POST requests per minute per IP; health, readiness, and metrics probes are exempt for reliable monitoring. The default limiter store is in-memory and process-local; set `RATELIMIT_STORAGE_URI` to a shared Flask-Limiter storage URI when running multiple workers. Set `FLASK_SECRET_KEY` to a stable, securely generated secret when session continuity across restarts is needed. These controls do not provide authentication or make the development server suitable for public deployment.

`GET /health` is a liveness probe. `GET /ready` is a production-readiness probe that returns HTTP 503 unless the observability SQLite database and upload directory are writable, `FLASK_SECRET_KEY` is configured with at least 32 bytes, `SESSION_COOKIE_SECURE=true` is set, Flask debug mode is off, and rate limiting uses a healthy shared backend. It returns only check names and booleans. `/metrics` serves Prometheus counters and latency histograms persisted in SQLite across restarts. The database defaults to `scheduled_posts/observability.sqlite3` and can be changed with `OBSERVABILITY_DB_PATH`; `http_request_metrics` and `application_errors` are the metric/error-event tables.

Unhandled web exceptions are associated with the response's `X-Request-ID`, recorded in the same SQLite database (up to 1,000 recent events), and logged with a traceback for local operational diagnosis. Persisted error records contain the request ID, method, route path, exception type, and timestamp—not exception messages, request bodies, or credentials. Configure access-controlled log collection and retention in the hosting environment; no external error-reporting service is contacted.

If the package is installed, use the console entry point:

```bash
aktma-socalmediaagent-web
```

## Upload support

The Web UI accepts allowlisted image and video uploads up to 5 MB each. It checks that the file's initial signature matches the extension and selected media type, then stores it under a random server-generated name to prevent path control and accidental overwrites. Images and videos are parsed locally for bounded format, metadata, and visual observations; ClamAV scanning is optional and may report files as unscanned. By default, file bytes are not sent to providers. The explicit OpenAI vision opt-in described above sends an image or sampled video frames externally. These checks are not exhaustive validation or a safety guarantee; the upload workflow is intended for local use, not public exposure.

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
- SQLite-backed scheduled job records with CLI inspection, pause, resume, cancel, and recovery
- Regression tests runnable with Python's built-in `unittest` runner

## Validation

Run the regression tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

Provider behavior is covered by mocked tests. Live API calls require valid provider credentials and have not been verified as part of the local test suite.

## Continuous integration

The repository includes a GitHub Actions workflow that installs the app dependencies and runs the full unittest suite on every push and pull request. The CI entry point is:

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
