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

The app falls back to local generation when no provider key is configured or a provider request fails. Provider failures are logged. This fallback is useful for local development but does not confirm that an external provider is configured correctly.

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
- Unexpected generator exceptions are retried up to 3 attempts with 1- and 2-second delays; after exhaustion the job is marked failed and the error remains in SQLite. Provider adapter failures that use the local fallback are treated as successful generation.

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

The supervisor runs until Ctrl+C, and starts up to the configured worker limit. It can recover persisted jobs after an old worker lease expires, but it does not start automatically with the web app or after a machine restart. Use an operating-system service/task for unattended startup. The supervisor uses the same `--scheduler-db` and `--scheduled-output` paths as other scheduler commands.

For a job marked `failed` after exhausting its bounded generation retries, use `--retry-job JOB_ID` to clear the retry state and run it again. The command is rejected for jobs that are not in the `failed` state.

The SQLite lease rejects a second worker while one is active. The worker renews its 120-second lease every 20 seconds; if a process crashes, wait for the lease to expire before recovery. Generated payloads saved to SQLite are replayed to the same output file if progress recording was interrupted; a crash before saving the payload can still repeat generation. Resume a paused job with `--resume-job` first, then run `--run-scheduled JOB_ID` if its worker is no longer active. When managing a job created in the web UI with a custom output folder, pass that same folder through `--scheduled-output` (or provide the exact database path with `--scheduler-db`). Coordination is local to one SQLite database; this is not a distributed worker service.

## 4. Run the web interface

```powershell
python web.py
```

Open `http://127.0.0.1:5000`. The app listens on localhost and starts with Flask debug mode disabled.

The form validates the topic, supported select values, uploaded file extensions, schedule interval, and post count. Scheduling creates a SQLite job and starts a background thread in the current process; closing the process stops that worker but preserves its job record for CLI recovery. A status message includes the job ID for validation or scheduler feedback.

## 5. Uploads and media limitations

The web form accepts image extensions `png`, `jpg`, `jpeg`, `gif` and video extensions `mp4`, `mov`, `avi`, `webm`, `m4v`. Files are stored in the repository's `uploads/` directory, and the filename is passed as prompt context. File contents are not analyzed or sent to a vision model. The extension allowlist is not a full content or malware inspection.

## 6. Run regression tests

From the repository root:

```powershell
python -m unittest discover -s tests -v
```

Tests use mocks for provider requests and do not call external provider APIs. Live provider integration still requires valid credentials and provider-side model access.

## Troubleshooting

- Confirm the virtual environment is active and dependencies are installed.
- Confirm `AI_PROVIDER` and the selected provider's API key are set if AI-provider generation is expected.
- A provider request failure is logged and returns a local fallback post; inspect application logs when diagnosing provider connectivity, authentication, or model errors.
- Use a positive interval such as `30m` and a non-negative integer count.
- Unsupported upload extensions are rejected. Uploaded files are stored locally under `uploads/`.
