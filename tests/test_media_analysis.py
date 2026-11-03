import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess
from typing import Dict
from unittest.mock import patch

from PIL import Image

from social_media_agent.generator import SocialMediaPostGenerator
from social_media_agent.media_analysis import (
    FRAME_SIZE,
    MediaAnalysisError,
    analyze_media,
)
from social_media_agent.scheduler import PeriodicPostScheduler
from social_media_agent.web import create_app


def _write_png(path: Path, size: tuple[int, int] = (16, 8)) -> None:
    Image.new("RGB", size, (230, 80, 35)).save(path, format="PNG")


class MediaAnalysisTests(unittest.TestCase):
    def test_image_analysis_reports_basic_visual_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            _write_png(path)

            result = analyze_media(path, "image")

        self.assertEqual(result["width"], 16)
        self.assertEqual(result["height"], 8)
        self.assertEqual(result["orientation"], "landscape")
        self.assertEqual(result["brightness"], "balanced")
        self.assertIn("Local image analysis", result["summary"])

    def test_image_analysis_rejects_invalid_and_oversized_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.png"
            path.write_bytes(b"not an image")
            with self.assertRaisesRegex(MediaAnalysisError, "could not be decoded"):
                analyze_media(path, "image")

            _write_png(path, size=(5, 5))
            with patch("social_media_agent.media_analysis.MAX_IMAGE_PIXELS", 20):
                with self.assertRaisesRegex(MediaAnalysisError, "dimensions are too large"):
                    analyze_media(path, "image")
    def test_video_analysis_samples_frames_and_reports_observations(self) -> None:
        frame_bytes = FRAME_SIZE * FRAME_SIZE * 3
        first_frame = bytes([20, 40, 60]) * (FRAME_SIZE * FRAME_SIZE)
        second_frame = bytes([220, 220, 220]) * (FRAME_SIZE * FRAME_SIZE)
        with patch("social_media_agent.media_analysis.shutil.which", return_value="ffmpeg"), patch(
            "social_media_agent.media_analysis.subprocess.run",
            return_value=CompletedProcess(
                args=["ffmpeg"],
                returncode=0,
                stdout=first_frame + second_frame,
                stderr=b"",
            ),
        ) as run:
            result = analyze_media(Path("sample.mp4"), "video")

        self.assertEqual(result["frames_sampled"], 2)
        self.assertEqual(result["sample_interval_seconds"], 10)
        self.assertEqual(result["visual_change"], "high")
        self.assertEqual(len(result["dominant_colors"]), 2)
        self.assertIn("Local video sample", result["summary"])
        self.assertEqual(len(run.call_args.args[0]), 14)
        self.assertEqual(len(first_frame), frame_bytes)

    def test_video_analysis_requires_ffmpeg(self) -> None:
        with patch("social_media_agent.media_analysis.shutil.which", return_value=None):
            with self.assertRaisesRegex(MediaAnalysisError, "requires FFmpeg"):
                analyze_media(Path("sample.mp4"), "video")

    def test_video_decode_failure_is_explicit(self) -> None:
        with patch("social_media_agent.media_analysis.shutil.which", return_value="ffmpeg"), patch(
            "social_media_agent.media_analysis.subprocess.run",
            return_value=CompletedProcess(
                args=["ffmpeg"],
                returncode=1,
                stdout=b"",
                stderr=b"decode failed",
            ),
        ):
            with self.assertRaisesRegex(MediaAnalysisError, "could not be decoded"):
                analyze_media(Path("sample.mp4"), "video")

    def test_generator_uses_and_returns_analysis_without_semantic_claims(self) -> None:
        analysis: Dict[str, object] = {
            "media_type": "image",
            "summary": "Local image analysis: 16x8 pixels, landscape orientation; balanced brightness.",
        }
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            generator = SocialMediaPostGenerator()
            prompt = generator._build_prompt(
                "product launch",
                "instagram",
                "friendly",
                "medium",
                "English",
                "image",
                "upload.png",
                analysis,
            )
            post = generator.generate_post(
                "product launch",
                media_type="image",
                media_filename="upload.png",
                media_analysis=analysis,
            )
            provider_post = generator._parse_json_response(
                '{"caption":"A provider caption."}',
                "product launch",
                "instagram",
                "friendly",
                "medium",
                "English",
                "image",
                "upload.png",
                analysis,
            )

        self.assertIn(analysis["summary"], prompt)
        self.assertIn("do not infer specific objects or events", prompt)
        self.assertEqual(post["media_analysis"], analysis)
        self.assertIn(analysis["summary"], post["caption"])
        self.assertEqual(provider_post["media_analysis"], analysis)

    def test_scheduled_job_persists_media_analysis_config(self) -> None:
        analysis = {"media_type": "image", "summary": "Local image analysis summary."}
        with tempfile.TemporaryDirectory() as directory:
            scheduler = PeriodicPostScheduler(
                SocialMediaPostGenerator(),
                output_dir=directory,
            )
            scheduler.create_job(
                {
                    "topic": "product launch",
                    "media_type": "image",
                    "media_analysis": analysis,
                },
                interval_seconds=60,
                count=1,
            )

            config = scheduler.list_jobs()[0]["post_config"]

        self.assertEqual(config["media_analysis"], analysis)

    def test_web_removes_saved_upload_when_analysis_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(directory),
        ), patch(
            "social_media_agent.web.SocialMediaPostGenerator",
        ), patch(
            "social_media_agent.web.analyze_media",
            side_effect=MediaAnalysisError("Video analysis requires FFmpeg installed and available on PATH."),
        ):
            app = create_app()
            image = BytesIO()
            Image.new("RGB", (4, 4), (255, 0, 0)).save(image, format="PNG")
            response = app.test_client().post(
                "/",
                data={
                    "topic": "product launch",
                    "platform": "instagram",
                    "media_type": "image",
                    "tone": "friendly",
                    "length": "medium",
                    "language": "English",
                    "interval": "",
                    "count": "0",
                    "media_file": (BytesIO(image.getvalue()), "upload.png"),
                },
                content_type="multipart/form-data",
            )
            stored_files = list(Path(directory).iterdir())

        self.assertEqual(response.status_code, 200)
        self.assertIn("requires FFmpeg", response.get_data(as_text=True))
        self.assertEqual(stored_files, [])


if __name__ == "__main__":
    unittest.main()
