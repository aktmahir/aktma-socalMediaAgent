import json
import os
import re
import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from typing import Dict
from unittest.mock import Mock, patch

from PIL import Image

from social_media_agent.generator import SocialMediaPostGenerator
from social_media_agent.media_analysis import (
    FRAME_SIZE,
    MediaAnalysisError,
    analyze_media,
    prepare_vision_images,
    scan_for_malware,
    _validate_video_container,
)
from social_media_agent.scheduler import PeriodicPostScheduler
from social_media_agent.web import create_app


def _write_png(path: Path, size: tuple[int, int] = (16, 8)) -> None:
    Image.new("RGB", size, (230, 80, 35)).save(path, format="PNG")


def _post_with_csrf(client, *args, **kwargs):
    page = client.get("/")
    match = re.search(
        r'<input type="hidden" name="csrf_token" value="([^"]+)"',
        page.get_data(as_text=True),
    )
    if match is None:
        raise AssertionError("The web form did not contain a CSRF token.")
    data = dict(kwargs.get("data") or {})
    data["csrf_token"] = match.group(1)
    kwargs["data"] = data
    return client.post(*args, **kwargs)


class MediaAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.observability_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.observability_dir.cleanup)
        self.observability_env = patch.dict(
            os.environ,
            {
                "OBSERVABILITY_DB_PATH": str(
                    Path(self.observability_dir.name) / "observability.sqlite3"
                )
            },
        )
        self.observability_env.start()
        self.addCleanup(self.observability_env.stop)

    def test_image_analysis_reports_basic_visual_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            _write_png(path)

            result = analyze_media(path, "image")

        self.assertEqual(result["width"], 16)
        self.assertEqual(result["height"], 8)
        self.assertEqual(result["orientation"], "landscape")
        self.assertEqual(result["brightness"], "balanced")
        self.assertEqual(result["format"], "PNG")
        self.assertEqual(result["color_mode"], "RGB")
        self.assertEqual(result["frame_count"], 1)
        self.assertFalse(result["is_animated"])
        self.assertIn("Local image analysis", result["summary"])

    def test_animated_image_metadata_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            frames = [
                Image.new("RGB", (4, 4), (255, 0, 0)),
                Image.new("RGB", (4, 4), (0, 0, 255)),
            ]
            frames[0].save(
                path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=120,
                loop=0,
            )

            result = analyze_media(path, "image")

        self.assertEqual(result["format"], "GIF")
        self.assertEqual(result["frame_count"], 2)
        self.assertTrue(result["is_animated"])
        self.assertEqual(result["first_frame_duration_ms"], 120)

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

    def test_oversized_image_is_rejected_before_pixel_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            _write_png(path, size=(5, 5))

            with patch(
                "social_media_agent.media_analysis.MAX_IMAGE_PIXELS",
                20,
            ), patch(
                "social_media_agent.media_analysis.ImageOps.exif_transpose"
            ) as transpose:
                with self.assertRaisesRegex(MediaAnalysisError, "dimensions are too large"):
                    analyze_media(path, "image")

        transpose.assert_not_called()

    def test_image_parser_rejects_extension_format_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            Image.new("RGB", (4, 4), (255, 0, 0)).save(path, format="JPEG")

            with self.assertRaisesRegex(MediaAnalysisError, "does not match"):
                analyze_media(path, "image")

    def test_image_parser_applies_exif_orientation_and_reports_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oriented.jpg"
            exif = Image.Exif()
            exif[274] = 6
            exif[271] = "Test Camera"
            Image.new("RGB", (8, 4), (220, 80, 35)).save(
                path,
                format="JPEG",
                exif=exif,
                dpi=(72, 72),
            )

            result = analyze_media(path, "image")

        self.assertEqual((result["width"], result["height"]), (4, 8))
        self.assertEqual(result["exif_orientation"], 6)
        self.assertIn("Orientation", result["exif_tag_names"])
        self.assertEqual(result["exif_metadata"]["Make"], "Test Camera")
        self.assertEqual(result["dpi"], [72.0, 72.0])
        json.dumps(result)

    def test_image_parser_rejects_animations_over_the_frame_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            frames = [
                Image.new("RGB", (4, 4), (255, 0, 0)),
                Image.new("RGB", (4, 4), (0, 0, 255)),
            ]
            frames[0].save(
                path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=120,
                loop=0,
            )

            with patch(
                "social_media_agent.media_analysis.MAX_IMAGE_FRAMES_TO_INSPECT",
                1,
            ), self.assertRaisesRegex(MediaAnalysisError, "too many"):
                analyze_media(path, "image")

    def test_video_analysis_samples_frames_and_reports_observations(self) -> None:
        frame_bytes = FRAME_SIZE * FRAME_SIZE * 3
        first_frame = bytes([20, 40, 60]) * (FRAME_SIZE * FRAME_SIZE)
        second_frame = bytes([220, 220, 220]) * (FRAME_SIZE * FRAME_SIZE)
        probe_result = CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout=(
                '{"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2","duration":"12.5"},'
                '"streams":[{"codec_type":"video","codec_name":"h264","width":1280,'
                '"height":720,"avg_frame_rate":"30/1","pix_fmt":"yuv420p",'
                '"tags":{"rotate":"90"}},{"codec_type":"audio",'
                '"codec_name":"aac","sample_rate":"48000","channels":2,'
                '"channel_layout":"stereo"}]}'
            ),
            stderr="",
        )
        sample_result = CompletedProcess(
            args=["ffmpeg"],
            returncode=0,
            stdout=first_frame + second_frame,
            stderr=b"",
        )
        with patch(
            "social_media_agent.media_analysis.shutil.which",
            side_effect=lambda name: {"ffprobe": "ffprobe", "ffmpeg": "ffmpeg"}.get(name),
        ), patch(
            "social_media_agent.media_analysis.subprocess.run",
            side_effect=[probe_result, sample_result],
        ) as run:
            result = analyze_media(Path("sample.mp4"), "video")

        self.assertEqual(result["container"], "mov,mp4,m4a,3gp,3g2,mj2")
        self.assertEqual(result["duration_seconds"], 12.5)
        self.assertEqual(result["video_stream_count"], 1)
        self.assertEqual(result["video_streams"][0]["codec"], "h264")
        self.assertEqual(result["video_streams"][0]["frame_rate"], 30.0)
        self.assertEqual(result["video_streams"][0]["pixel_format"], "yuv420p")
        self.assertEqual(result["video_streams"][0]["rotation_degrees"], 90.0)
        self.assertEqual(result["audio_stream_count"], 1)
        self.assertEqual(result["audio_streams"][0]["sample_rate_hz"], 48000)
        self.assertEqual(result["audio_streams"][0]["channels"], 2)
        self.assertEqual(result["frames_sampled"], 2)
        self.assertEqual(result["sample_interval_seconds"], 10)
        self.assertEqual(result["visual_change"], "high")
        self.assertEqual(len(result["dominant_colors"]), 2)
        self.assertIn("Local video sample", result["summary"])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(len(first_frame), frame_bytes)

    def test_video_analysis_requires_ffprobe(self) -> None:
        with patch("social_media_agent.media_analysis.shutil.which", return_value=None):
            with self.assertRaisesRegex(MediaAnalysisError, "requires FFprobe"):
                analyze_media(Path("sample.mp4"), "video")

    def test_video_sampling_requires_ffmpeg(self) -> None:
        probe_result = CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout=(
                '{"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2","duration":"1"},'
                '"streams":[{"codec_type":"video","codec_name":"h264",'
                '"width":16,"height":16}]}'
            ),
            stderr="",
        )
        with patch(
            "social_media_agent.media_analysis.shutil.which",
            side_effect=lambda name: "ffprobe" if name == "ffprobe" else None,
        ), patch(
            "social_media_agent.media_analysis.subprocess.run",
            return_value=probe_result,
        ):
            with self.assertRaisesRegex(MediaAnalysisError, "requires FFmpeg"):
                analyze_media(Path("sample.mp4"), "video")

    def test_video_decode_failure_is_explicit(self) -> None:
        probe_result = CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout=(
                '{"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2","duration":"1"},'
                '"streams":[{"codec_type":"video","codec_name":"h264",'
                '"width":16,"height":16}]}'
            ),
            stderr="",
        )
        decode_failure = CompletedProcess(
            args=["ffmpeg"],
            returncode=1,
            stdout=b"",
            stderr=b"decode failed",
        )
        with patch(
            "social_media_agent.media_analysis.shutil.which",
            side_effect=lambda name: name,
        ), patch(
            "social_media_agent.media_analysis.subprocess.run",
            side_effect=[probe_result, decode_failure],
        ):
            with self.assertRaisesRegex(MediaAnalysisError, "could not be decoded"):
                analyze_media(Path("sample.mp4"), "video")

    def test_video_metadata_failure_is_explicit(self) -> None:
        with patch(
            "social_media_agent.media_analysis.shutil.which",
            side_effect=lambda name: "ffprobe" if name == "ffprobe" else "ffmpeg",
        ), patch(
            "social_media_agent.media_analysis.subprocess.run",
            return_value=CompletedProcess(
                args=["ffprobe"],
                returncode=1,
                stdout="",
                stderr="invalid media",
            ),
        ):
            with self.assertRaisesRegex(MediaAnalysisError, "metadata could not be parsed"):
                analyze_media(Path("sample.mp4"), "video")

    def test_video_stream_over_pixel_limit_is_rejected_before_decoding(self) -> None:
        probe_result = CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout=(
                '{"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2","duration":"1"},'
                '"streams":[{"codec_type":"video","codec_name":"h264",'
                '"width":5,"height":5}]}'
            ),
            stderr="",
        )
        with patch(
            "social_media_agent.media_analysis.MAX_VIDEO_FRAME_PIXELS",
            20,
        ), patch(
            "social_media_agent.media_analysis.shutil.which",
            side_effect=lambda name: name,
        ), patch(
            "social_media_agent.media_analysis.subprocess.run",
            return_value=probe_result,
        ) as run:
            with self.assertRaisesRegex(MediaAnalysisError, "pixel limits"):
                analyze_media(Path("sample.mp4"), "video")

        run.assert_called_once()

    def test_video_container_validation_covers_all_allowed_extensions(self) -> None:
        for extension, container, brand in (
            (".mp4", "mov,mp4,m4a,3gp,3g2,mj2", "isom"),
            (".mov", "mov,mp4,m4a,3gp,3g2,mj2", "qt  "),
            (".m4v", "mov,mp4,m4a,3gp,3g2,mj2", "m4v "),
            (".avi", "avi", ""),
            (".webm", "matroska,webm", ""),
        ):
            with self.subTest(extension=extension):
                _validate_video_container(
                    Path("media" + extension),
                    {
                        "format_name": container,
                        "tags": {"major_brand": brand} if brand else {},
                    },
                )

        with self.assertRaisesRegex(ValueError, "does not match AVI"):
            _validate_video_container(
                Path("media.avi"),
                {"format_name": "matroska,webm", "tags": {}},
            )

    def test_video_vision_preparation_samples_bounded_frames(self) -> None:
        frame_size = 512
        frame = bytes([20, 40, 60]) * (frame_size * frame_size)
        with patch(
            "social_media_agent.media_analysis.shutil.which",
            return_value="ffmpeg",
        ), patch(
            "social_media_agent.media_analysis.subprocess.run",
            return_value=CompletedProcess(
                args=["ffmpeg"],
                returncode=0,
                stdout=frame,
                stderr=b"",
            ),
        ) as run:
            images = prepare_vision_images(Path("sample.mp4"), "video")

        self.assertEqual(len(images), 1)
        self.assertTrue(images[0].startswith("data:image/jpeg;base64,"))
        self.assertIn("-frames:v", run.call_args.args[0])

    def test_vision_preparation_rejects_oversized_image_before_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            _write_png(path, size=(5, 5))

            with patch(
                "social_media_agent.media_analysis.MAX_IMAGE_PIXELS",
                20,
            ), patch(
                "social_media_agent.media_analysis.ImageOps.exif_transpose"
            ) as transpose:
                with self.assertRaisesRegex(MediaAnalysisError, "dimensions are too large"):
                    prepare_vision_images(path, "image")

        transpose.assert_not_called()

    def test_openai_vision_analysis_sends_images_and_parses_description(self) -> None:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {"summary": "A red product package on a table."}
                        )
                    )
                )
            ]
        )
        generator = SocialMediaPostGenerator(api_key="test-key", provider="openai")
        generator.vision_model = "test-vision-model"
        generator._openai_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=response))
            )
        )
        image_data = "data:image/jpeg;base64,dGVzdA=="
        with patch(
            "social_media_agent.generator.prepare_vision_images",
            return_value=[image_data],
        ):
            result = generator.analyze_media_with_vision(Path("image.png"), "image")

        self.assertEqual(result["summary"], "A red product package on a table.")
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["model"], "test-vision-model")
        request = generator._openai_client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "test-vision-model")
        self.assertEqual(
            request["messages"][0]["content"][1]["image_url"]["url"],
            image_data,
        )

    def test_openai_vision_analysis_requires_an_openai_key(self) -> None:
        generator = SocialMediaPostGenerator(provider="cohere")
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}), self.assertRaisesRegex(
            MediaAnalysisError,
            "requires OPENAI_API_KEY",
        ):
            generator.analyze_media_with_vision(Path("image.png"), "image")

    def test_malware_scan_reports_scanner_availability_and_results(self) -> None:
        path = Path("sample.png")
        with patch("social_media_agent.media_analysis.shutil.which", return_value=None):
            self.assertEqual(
                scan_for_malware(path),
                {"status": "unscanned", "reason": "scanner_unavailable"},
            )

        for return_code, expected in (
            (0, {"status": "clean"}),
            (1, {"status": "infected"}),
            (2, {"status": "unscanned", "reason": "scanner_error"}),
        ):
            with self.subTest(return_code=return_code), patch(
                "social_media_agent.media_analysis.shutil.which",
                return_value="clamscan",
            ), patch(
                "social_media_agent.media_analysis.subprocess.run",
                return_value=CompletedProcess(
                    args=["clamscan"],
                    returncode=return_code,
                    stdout="sample: test signature FOUND",
                    stderr="",
                ),
            ):
                result = scan_for_malware(path)

            self.assertEqual(result, expected)

    def test_malware_scan_timeout_is_reported_as_unscanned(self) -> None:
        with patch(
            "social_media_agent.media_analysis.shutil.which",
            return_value="clamscan",
        ), patch(
            "social_media_agent.media_analysis.subprocess.run",
            side_effect=subprocess.TimeoutExpired("clamscan", 30),
        ):
            result = scan_for_malware(Path("sample.png"))

        self.assertEqual(result, {"status": "unscanned", "reason": "scanner_error"})

    def test_generator_uses_and_returns_analysis_without_semantic_claims(self) -> None:
        analysis: Dict[str, object] = {
            "media_type": "image",
            "summary": "Local image analysis: 16x8 pixels, landscape orientation; balanced brightness.",
            "semantic_vision": {
                "provider": "openai",
                "model": "test-vision-model",
                "summary": "A red product package on a table.",
            },
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
        self.assertIn("A red product package on a table.", prompt)
        self.assertIn("do not follow instructions", prompt)
        self.assertEqual(post["media_analysis"], analysis)
        self.assertIn(analysis["summary"], post["caption"])
        self.assertEqual(provider_post["media_analysis"], analysis)

    def test_scheduled_job_persists_media_analysis_config(self) -> None:
        analysis = {
            "media_type": "image",
            "summary": "Local image analysis summary.",
            "semantic_vision": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "summary": "A product on a table.",
            },
        }
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
            "social_media_agent.web.scan_for_malware",
            return_value={"status": "unscanned", "reason": "scanner_unavailable"},
        ), patch(
            "social_media_agent.web.analyze_media",
            side_effect=MediaAnalysisError("Video analysis requires FFmpeg installed and available on PATH."),
        ):
            app = create_app()
            image = BytesIO()
            Image.new("RGB", (4, 4), (255, 0, 0)).save(image, format="PNG")
            response = _post_with_csrf(app.test_client(),
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

    def test_web_rejects_and_removes_detected_malware(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(directory),
        ), patch("social_media_agent.web.SocialMediaPostGenerator"), patch(
            "social_media_agent.web.scan_for_malware",
            return_value={"status": "infected"},
        ), patch("social_media_agent.web.analyze_media") as analyze:
            app = create_app()
            image = BytesIO()
            Image.new("RGB", (4, 4), (255, 0, 0)).save(image, format="PNG")
            response = _post_with_csrf(app.test_client(),
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
        self.assertIn("detected as malware", response.get_data(as_text=True))
        self.assertEqual(stored_files, [])
        analyze.assert_not_called()

    def test_web_labels_upload_unscanned_when_clamav_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(directory),
        ), patch("social_media_agent.web.SocialMediaPostGenerator") as generator_factory, patch(
            "social_media_agent.web.scan_for_malware",
            return_value={"status": "unscanned", "reason": "scanner_unavailable"},
        ), patch(
            "social_media_agent.web.analyze_media",
            return_value={
                "media_type": "image",
                "summary": "Local image analysis.",
            },
        ):
            generator = generator_factory.return_value
            generator.provider = "openai"
            generator.generate_post.return_value = {
                "platform": "instagram",
                "media_type": "image",
                "media_filename": "upload.png",
                "media_analysis": {
                    "summary": "Local image analysis.",
                    "malware_scan": {
                        "status": "unscanned",
                        "reason": "scanner_unavailable",
                    },
                },
                "title": "",
                "description": "",
                "tags": [],
                "caption": "Image post",
                "call_to_action": "",
                "hashtags": [],
            }
            app = create_app()
            image = BytesIO()
            Image.new("RGB", (4, 4), (255, 0, 0)).save(image, format="PNG")
            response = _post_with_csrf(app.test_client(),
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

        self.assertEqual(response.status_code, 200)
        self.assertIn("ClamAV is not installed", response.get_data(as_text=True))
        generation_config = generator.generate_post.call_args.kwargs
        self.assertEqual(
            generation_config["media_analysis"]["malware_scan"],
            {"status": "unscanned", "reason": "scanner_unavailable"},
        )
        generator.analyze_media_with_vision.assert_not_called()

    def test_web_sends_media_to_vision_only_after_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "social_media_agent.web.UPLOAD_FOLDER",
            Path(directory),
        ), patch("social_media_agent.web.SocialMediaPostGenerator") as generator_factory, patch(
            "social_media_agent.web.scan_for_malware",
            return_value={"status": "clean"},
        ), patch(
            "social_media_agent.web.analyze_media",
            return_value={
                "media_type": "image",
                "summary": "Local image analysis.",
            },
        ):
            generator = generator_factory.return_value
            generator.provider = "openai"
            generator.analyze_media_with_vision.return_value = {
                "provider": "openai",
                "model": "test-vision-model",
                "summary": "A red product package on a table.",
            }
            generator.generate_post.return_value = {
                "platform": "instagram",
                "media_type": "image",
                "media_filename": "upload.png",
                "media_analysis": {
                    "summary": "Local image analysis.",
                    "semantic_vision": {
                        "summary": "A red product package on a table.",
                    },
                },
                "title": "",
                "description": "",
                "tags": [],
                "caption": "Image post",
                "call_to_action": "",
                "hashtags": [],
            }
            app = create_app()
            image = BytesIO()
            Image.new("RGB", (4, 4), (255, 0, 0)).save(image, format="PNG")
            response = _post_with_csrf(app.test_client(),
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
                    "provider_vision": "yes",
                    "media_file": (BytesIO(image.getvalue()), "upload.png"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("A red product package on a table.", response.get_data(as_text=True))
        generator.analyze_media_with_vision.assert_called_once()
        generation_config = generator.generate_post.call_args.kwargs
        self.assertEqual(
            generation_config["media_analysis"]["semantic_vision"]["summary"],
            "A red product package on a table.",
        )

    def test_web_rejects_vision_opt_in_without_media(self) -> None:
        with patch("social_media_agent.web.SocialMediaPostGenerator") as generator_factory:
            response = _post_with_csrf(create_app().test_client(),
                "/",
                data={
                    "topic": "product launch",
                    "media_type": "text",
                    "provider_vision": "yes",
                    "interval": "",
                    "count": "0",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Upload an image or video", response.get_data(as_text=True))
        generator_factory.return_value.generate_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
