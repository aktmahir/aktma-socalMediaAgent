# aktma-socalMediaAgent Usage Guide

This guide explains how to install and use the social media post generator app step by step.

## 1. Create a Python virtual environment

Open a terminal and run:

```powershell
python -m venv .venv
```

Activate the virtual environment:

```powershell
.venv\Scripts\activate
```

## 2. Install dependencies

Install the required Python packages:

```powershell
pip install -r requirements.txt
```

## 3. Create a .env file

Create a `.env` file from the example:

```powershell
copy .env.example .env
```

Open `.env` and configure the AI provider plus the API key for the provider you want to use:

```powershell
AI_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-3.5-turbo
HUGGINGFACE_API_KEY=your_huggingface_api_key_here
HUGGINGFACE_MODEL=gpt2
COHERE_API_KEY=your_cohere_api_key_here
COHERE_MODEL=command-xlarge-nightly
```

## 4. Optional: install the package locally

This adds convenient commands and installs the package for local use:

```powershell
pip install .
```

## 4. Optional: set your provider API key

If you want AI-powered results, set the selected provider and its API key in your environment or `.env` file. For example:

```powershell
set AI_PROVIDER=openai
set OPENAI_API_KEY=your_api_key_here
```

For Hugging Face:

```powershell
set AI_PROVIDER=huggingface
set HUGGINGFACE_API_KEY=your_huggingface_api_key_here
```

For Cohere:

```powershell
set AI_PROVIDER=cohere
set COHERE_API_KEY=your_cohere_api_key_here
```

## 5. Generate a post using the CLI

Basic command:

```powershell
python app.py --topic "launching a new product" --platform instagram --tone friendly --length medium
```

Use a different AI provider with `--ai-provider` and `--provider-model`:

```powershell
python app.py --topic "launching a new product" --platform instagram --tone friendly --length medium --ai-provider huggingface --provider-model gpt2
```

For a video post with a media filename:

```powershell
python app.py --topic "new product launch" --platform youtube --media-type video --media-filename launch_clip.mp4 --tone motivational --length medium
```

For a YouTube Short:

```powershell
python app.py --topic "quick launch tip" --platform youtube_shorts --media-type video --media-filename short_clip.mp4 --tone friendly --length short
```

## 6. Schedule periodic posting

To generate posts automatically at a regular interval, use `--interval` and optionally `--count`:

```powershell
python app.py --topic "weekly marketing tip" --platform instagram --media-type image --media-filename creative.jpg --tone educational --length medium --interval 1d --count 7
```

- `1d` means every day.
- `1h` means every hour.
- `30m` means every 30 minutes.
- `--count 0` means run until you stop it manually.

Scheduled post output files are written to `scheduled_posts/` by default.

If installed locally, you can also run:

```powershell
aktma-socalmediaagent
```

## 7. Use the web interface

Run the Flask web application:

```powershell
python web.py
```

Open your browser and go to:

```text
http://127.0.0.1:5000
```

The web app includes scheduling controls, so you can start periodic posting directly from the browser by setting an interval and count.

## 7. Upload image or video content

1. Choose a platform and media type in the web form.
2. Select `image` or `video` as the media type.
3. Upload the file using the file chooser.
4. Submit the form to generate caption, hashtags, and metadata.

Supported file types:
- Images: `png`, `jpg`, `jpeg`, `gif`
- Videos: `mp4`, `mov`, `avi`, `webm`, `m4v`

## 8. YouTube metadata output

When generating YouTube video posts, the app can provide:
- `title`
- `description`
- `tags`

These values are included in the CLI output and displayed in the web UI.

## 9. Where uploads are saved

Uploaded media files are stored in the project `uploads/` folder.

## 10. Troubleshooting

- If the app fails to run, make sure the virtual environment is active.
- Confirm dependencies are installed with `pip install -r requirements.txt`.
- If AI output is required, verify the selected `AI_PROVIDER` and corresponding API key are set in `.env`.
- For Hugging Face or Cohere, also confirm `HUGGINGFACE_API_KEY` or `COHERE_API_KEY` is configured.
- If the web UI does not allow file upload, confirm the browser can select the supported file type.
