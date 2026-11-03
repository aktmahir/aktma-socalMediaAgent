# Project Overview

## Purpose
The project is a Python-based social media caption generator designed to help marketers, creators, and agencies generate short-form social content based on a topic, platform, tone, length, and media type. It supports CLI and web-based workflows and includes a local fallback generator when external AI providers are unavailable.

## Intended audience
- Solo creators and marketing teams
- Small businesses publishing on multiple platforms
- Developers prototyping AI content workflows
- Local experimentation with social caption generation

## Core requirements as implemented
The project is intended to:
- generate platform-specific captions for Instagram, LinkedIn, Twitter, Facebook, YouTube, and YouTube Shorts
- support text, image, and video post styles
- use OpenAI, Hugging Face, or Cohere when credentials are configured
- provide a local deterministic fallback when no provider is configured or available
- allow scheduled/periodic posting from CLI or web UI
- allow uploaded media files for richer prompt context

## Verified architecture
Based on the source code, the project has a small layered structure:
- `app.py` — CLI entry point and argument parsing
- `social_media_agent/generator.py` — core generation logic and AI provider abstractions
- `social_media_agent/web.py` — Flask front end and upload form
- `social_media_agent/scheduler.py` — periodic scheduling loop
- `social_media_agent/templates/index.html` — simple UI markup and form logic

## Technology stack
- Python 3.9+
- Flask for web UI
- Requests for HTTP client calls
- OpenAI Python SDK
- python-dotenv for `.env` support
- setuptools-based package metadata

## Frontend and backend architecture
The current implementation is a lightweight monolith rather than a multi-service application:
- backend logic is embedded in Python modules
- there is no database layer, ORM, or API service boundary
- the web UI is server-rendered HTML and not a modern SPA
- generated content is produced in memory or saved to JSON files

## Data model and persistence
There is no persistent database or schema. Current “data” is transient:
- generated post payloads are returned as dicts
- scheduled posts are saved as JSON files under a configured folder
- uploaded files are stored locally under `uploads/`

## External integrations
The codebase integrates with three provider models:
- OpenAI via `openai.ChatCompletion.create`
- Hugging Face via `requests.post` to the inference API
- Cohere via `requests.post` to the Cohere generate endpoint

## Configuration and security posture
Configuration is handled through environment variables and `.env` files. There is no secret-management layer, no auth provider, and no production-grade config separation.

## Current implementation status
The project is a working demo/prototype in its current form, but it is not production-ready. It has a credible local fallback and a useful CLI/web workflow, yet several core provider integrations and infrastructure assumptions are incomplete or broken.

## Summary assessment
This is best described as a functional prototype for AI-generated social captions with local scheduling and UI scaffolding. It is not yet a robust production system because the AI integrations are partially broken, testing is absent, deployment readiness is missing, and operational safeguards are not in place.
