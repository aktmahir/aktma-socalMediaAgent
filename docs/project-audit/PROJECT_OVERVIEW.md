# Project Overview

## Purpose

The project is a Python application for generating social media content from a topic, target platform, tone, length, language, and media type. It supports CLI and Flask web workflows, optional external AI providers, local fallback generation, and basic periodic generation to JSON files.

## Intended audience

- Solo creators and marketing teams
- Small businesses preparing content for multiple platforms
- Developers prototyping social media generation workflows
- Local experimentation with AI-provider adapters

## Current capabilities

- Generates captions, hashtags, and calls to action for Instagram, LinkedIn, Twitter, Facebook, YouTube, and YouTube Shorts.
- Uses OpenAI, Hugging Face, or Cohere when configured with a key and a usable model.
- Falls back to a randomized local template generator if no provider is configured or a provider fails.
- Offers a CLI (`app.py`) and a local Flask interface (`web.py`).
- Saves generated posts as JSON files and persists schedule configuration/progress in SQLite.
- Provides CLI commands to inspect, pause, resume, cancel, manually recover, and supervise persisted scheduled jobs.
- Accepts allowlisted web uploads up to 5 MB with signature checks, random server-generated names, bounded local image/video parsing, optional ClamAV scanning, and explicit opt-in OpenAI vision descriptions.

## Architecture

- `app.py` — CLI argument parsing and generation/scheduling entry point.
- `social_media_agent/generator.py` — prompt construction, provider adapters, response parsing, and local fallback.
- `social_media_agent/web.py` — Flask route, form validation, and upload handling.
- `social_media_agent/scheduler.py` — shared interval/count parsing, SQLite-backed job lifecycle, and periodic output loop.
- `social_media_agent/templates/index.html` — server-rendered web form and result/status display.
- `tests/` — `unittest` regression coverage for provider mocks, Flask routes, and scheduler behavior.

## Technology

- Python 3.9+
- Flask for the local web UI
- Requests for Hugging Face and Cohere HTTP requests
- OpenAI Python SDK
- python-dotenv for local `.env` loading
- setuptools packaging
- Python standard-library `unittest` for regression tests

## Provider and environment configuration

Set `AI_PROVIDER` to `openai`, `huggingface`, or `cohere` and configure the corresponding API key. Hugging Face and Cohere model environment variables are `HUGGINGFACE_MODEL` and `COHERE_MODEL`; select the OpenAI model with the CLI `--openai-model` option or the generator's `openai_model` argument. Cohere requests use v2 Chat; provider/model service availability is not guaranteed by the application. Provider request behavior has mock coverage but has not been validated with live credentials.

## Persistence and runtime boundaries

Generated posts are returned as dictionaries or written as JSON files. Scheduled job records use SQLite (default: `scheduled_posts/scheduler.sqlite3`), while web workers run in-process. Docker Compose also starts a separate supervisor that shares the scheduler database and output volume; SQLite leases coordinate the workers and allow recovery of abandoned jobs after lease expiry. Local users can run the CLI supervisor or register current-user Windows logon startup through `scripts/register-scheduler-supervisor.ps1`; registration is explicit. There is no cross-database coordination. Uploaded files are stored under `uploads/`, in per-account subdirectories when multi-user mode is enabled.

The web runner binds to localhost with Flask debug disabled. Forms use session-backed CSRF tokens, and application routes have per-IP rate limits. Health and monitoring probes are exempt; the default limiter storage is process-local. Request metrics and bounded web exception events persist in `scheduled_posts/observability.sqlite3`; `/ready` checks metrics, upload, and scheduled-output storage plus required production settings, creating the configured output root if needed. Gunicorn, a Docker Compose stack with Redis and Prometheus, optional single-user or invite-only multi-user authentication, per-user upload/scheduled-output paths, secret-file mounts, and an Nginx TLS overlay are available. These examples do not constitute a complete public-production setup; external secret management/rotation and deployment verification remain outstanding.

## Current status

Phase 1 provider compatibility, request error handling, and core CLI/web/scheduler validation are implemented with regression tests. Phase 2 adds CI, Flask route coverage, SQLite-backed local job lifecycle controls, worker leases, bounded generation retries, persistent request metrics, local centralized exception reporting, readiness checks, a Docker supervisor service for job recovery, and invite-only multi-user access with admin/user roles. Credentialed provider smoke requests were attempted, but all three fell back locally (OpenAI authentication error, Hugging Face connection error, Cohere HTTP error); successful live provider validation, richer media processing, alert notification routing, and full public-production hardening remain future work.
