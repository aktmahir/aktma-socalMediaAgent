# aktma-socalMediaAgent

AI-powered Social Media Post Generator in Python.

## Overview

This project creates social media posts automatically using OpenAI, Hugging Face, or Cohere when the selected API key is available, with a local fallback generator otherwise. It supports Instagram, LinkedIn, Twitter, Facebook, YouTube video posts, and YouTube Shorts.

## Install

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

4. Update `.env` with your provider settings and API keys:

   ```bash
   AI_PROVIDER=openai
   OPENAI_API_KEY=your_api_key_here
   OPENAI_MODEL=gpt-3.5-turbo
   HUGGINGFACE_API_KEY=your_huggingface_api_key_here
   HUGGINGFACE_MODEL=gpt2
   COHERE_API_KEY=your_cohere_api_key_here
   COHERE_MODEL=command-xlarge-nightly
   ```

4. Install the package locally:

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

Generate a YouTube video post:

```bash
python app.py --topic "new product launch" --platform youtube --media-type video --media-filename launch_clip.mp4 --tone motivational --length medium
```

Generate a YouTube Shorts caption:

```bash
python app.py --topic "quick launch tip" --platform youtube_shorts --media-type video --media-filename short_clip.mp4 --tone friendly --length short
```

## Periodic Posting

Generate posts automatically at a fixed interval:

```bash
python app.py --topic "weekly marketing tip" --platform instagram --media-type image --media-filename creative.jpg --tone educational --length medium --interval 1d --count 7
```

- `--interval 1d` means once every day.
- `--count 7` sends 7 scheduled posts.
- `--count 0` runs indefinitely until stopped.
- Scheduled post files are saved under `scheduled_posts/` by default.

## Web Interface

Run the Flask web interface locally:

```bash
python web.py
```

Then open `http://127.0.0.1:5000` in your browser.

The web UI now includes scheduling controls for interval, post count, and output folder. When you submit a scheduled post, the app starts generating posts in the background and saves them under the selected output folder.

If the package is installed, use the console entry point:

```bash
aktma-socalmediaagent-web
```

## Upload support

The web UI now accepts image and video uploads for richer posts.

Supported media types:
- `text`
- `image`
- `video`

Supported platforms include YouTube video posts and YouTube Shorts.

## Features

- `SocialMediaPostGenerator` Python class for integration
- CLI interface via `app.py`
- OpenAI-powered generation when `OPENAI_API_KEY` is present
- Local fallback generation when API access is unavailable
- Hashtag creation and call-to-action support
- YouTube video metadata generation: title, description, and tags

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
