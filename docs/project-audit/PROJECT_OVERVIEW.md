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
- Saves scheduled generated posts as JSON files in an in-process loop.
- Accepts web uploads by extension and uses the filename as prompt context; it does not analyze file contents.

## Architecture

- `app.py` — CLI argument parsing and generation/scheduling entry point.
- `social_media_agent/generator.py` — prompt construction, provider adapters, response parsing, and local fallback.
- `social_media_agent/web.py` — Flask route, form validation, and upload handling.
- `social_media_agent/scheduler.py` — shared interval/count parsing and in-process periodic output loop.
- `social_media_agent/templates/index.html` — server-rendered web form and result/status display.
- `tests/test_phase1_regressions.py` — `unittest` regression coverage using mocked provider responses.

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

There is no database. Generated posts are returned as dictionaries or written as JSON files. Scheduled jobs are process-local and are lost when the process exits. Uploaded files are stored under `uploads/`.

The web runner binds to localhost with Flask debug disabled. This is not a production deployment configuration; there is no authentication, authorization, CSRF protection, rate limiting, or production server setup.

## Current status

Phase 1 provider compatibility, request error handling, and core CLI/web/scheduler validation are implemented with regression tests. Remaining Phase 1 confidence work includes live provider smoke tests and Flask test-client coverage. Persistent scheduling, richer media processing, multi-user access, and deployment hardening remain future work.
