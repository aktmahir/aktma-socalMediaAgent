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
- Intervals must be positive values followed by `s`, `m`, `h`, or `d`; post counts must be non-negative integers.

## Web Interface

Run the Flask web interface locally:

```bash
python web.py
```

Then open `http://127.0.0.1:5000` in your browser.

The web UI includes scheduling controls for interval, post count, and output folder. When you submit a schedule, the app starts generating drafts in the background and saves them under the selected output folder; it does not publish to a social network.
Invalid topics, unsupported form selections, file types, counts, and intervals are rejected with status feedback. The scheduler itself also rejects non-positive intervals and negative counts.

If the package is installed, use the console entry point:

```bash
aktma-socalmediaagent-web
```

## Upload support

The web UI accepts image and video uploads and passes the stored filename as prompt context; it does not analyze image or video contents. Uploaded files are stored under `uploads/`.

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
- Regression tests runnable with Python's built-in `unittest` runner

## Validation

Run the regression tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

Provider behavior is covered by mocked tests. Live API calls require valid provider credentials and have not been verified as part of the local test suite.

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
