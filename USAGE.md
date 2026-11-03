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

The web upload form includes a separate, unchecked-by-default option for semantic vision descriptions. Selecting it sends the uploaded image, or up to three sampled video frames, to OpenAI using `OPENAI_API_KEY`; it uses `OPENAI_VISION_MODEL` when set and otherwise `gpt-4o-mini`. This works independently of `AI_PROVIDER`. Without that explicit per-upload selection, media remains local and is not sent to an AI service.

The app falls back to local generation when no provider key is configured or a provider request fails. Provider failures are logged. The CLI and web result identify local-template output so it is not mistaken for a response from the selected external provider. This fallback is useful for local development but does not confirm that an external provider is configured correctly.

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

The supervisor runs until Ctrl+C and starts up to the configured worker limit. On Windows, register it to start at the current user's logon with the supplied Task Scheduler script:

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

The form validates the topic, supported select values, uploaded file extensions and signatures, schedule interval, and post count. Uploads are limited to 5 MB each. Scheduling creates a SQLite job and starts a background thread in the current process; closing the process stops that worker but preserves its job record for CLI recovery. A status message includes the job ID for validation or scheduler feedback.

For basic request monitoring, scrape `http://127.0.0.1:5000/metrics`. It returns Prometheus text-format request totals and duration histograms by bounded HTTP method and status code; the scrape endpoint itself is excluded. Metrics are held in memory and reset when the app restarts. Keep the web app bound to localhost, or protect the endpoint appropriately before exposing it beyond a trusted local environment.

The `http://127.0.0.1:5000/health` endpoint returns `{"status":"ok"}` when the Flask application is serving requests. This is a liveness check only; it does not verify provider credentials, database readiness, or scheduler-worker availability, and is not a production readiness probe.

## 5. Uploads and media limitations

The web form accepts image extensions `png`, `jpg`, `jpeg`, `gif` and video extensions `mp4`, `mov`, `avi`, `webm`, `m4v`. Each upload is limited to 5 MB and its initial file signature must match its extension and selected media type. Files are stored under random server-generated names in the repository's `uploads/` directory, so an uploaded name cannot overwrite another file or control its storage path. Invalid submissions are rejected before the upload is written.

Before parsing, the app uses `clamscan` when it is available on `PATH`. Detected files are rejected and removed. If ClamAV is unavailable or cannot complete a scan, the upload remains usable but its result is explicitly labeled **unscanned**; a clean result means only that ClamAV reported no detection. Install and maintain ClamAV and its signature database separately; the app does not install or update it.

Images are decoded locally with Pillow for dimensions after EXIF orientation, format, color mode, EXIF tag names, GPS-metadata presence (coordinates are not exposed), ICC profile/DPI presence, and bounded animation/frame metadata. Every frame must decode within configured pixel/frame limits, and the decoded format must match the extension. Videos require `ffprobe` for container, duration, file size/bitrate, video and audio stream codecs, dimensions, timing, pixel/aspect formats, rotation, and audio layout metadata; `ffmpeg` samples up to three low-resolution frames at 10-second intervals. The parsed container must match the selected extension and include a valid video stream. Missing tools or decode/metadata errors are reported and the uploaded file is removed. Local observations are passed as context and saved with scheduled job configuration. If the vision option is checked, the provider's description is also passed to generation and saved in the scheduled configuration. This bounded parsing is not exhaustive validation or a guarantee of safety; optional ClamAV scanning and keep-the-web-app-local guidance still apply.

## 6. Run regression tests

From the repository root:

```powershell
python -m unittest discover -s tests -v
```

Tests use mocks for provider requests and do not call external provider APIs. Live provider integration still requires valid credentials and provider-side model access.

## Troubleshooting

- CLI and web entry points emit timestamped logs to stderr. Web request and scheduler lifecycle records use JSON messages with request/job IDs and status information; prompt text, credentials, and upload contents are not included in those structured records. Request metrics are available at `/metrics`; they contain no routes, request IDs, prompts, filenames, or upload contents.
- Confirm the virtual environment is active and dependencies are installed.
- Confirm `AI_PROVIDER` and the selected provider's API key are set if AI-provider generation is expected.
- A provider request failure is logged and returns a local fallback post; inspect application logs when diagnosing provider connectivity, authentication, or model errors.
- Use a positive interval such as `30m` and a non-negative integer count.
- Unsupported extensions, mismatched signatures/media types, multiple files, and uploads over 5 MB are rejected. Uploaded files are stored locally under `uploads/` with generated names.
