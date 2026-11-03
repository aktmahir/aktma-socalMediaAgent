import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app as cli_module
from social_media_agent import generator as generator_module
from social_media_agent.generator import SocialMediaPostGenerator
from social_media_agent.scheduler import PeriodicPostScheduler, parse_count
from app import parse_interval


class PhaseOneRegressionTests(unittest.TestCase):
    def test_generate_post_local_fallback_returns_expected_shape(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            generator = SocialMediaPostGenerator()
            post = generator.generate_post(
                topic="AI marketing",
                platform="linkedin",
                tone="professional",
                length="medium",
            )

        self.assertTrue(
            {"caption", "hashtags", "call_to_action", "title", "description", "tags"}
            <= set(post)
        )
        self.assertEqual(post["platform"], "linkedin")
        self.assertTrue(post["caption"])
        self.assertTrue(post["hashtags"])

    def test_generate_post_rejects_empty_topic(self) -> None:
        generator = SocialMediaPostGenerator()
        with self.assertRaisesRegex(ValueError, "Topic must not be empty"):
            generator.generate_post("   ")

    def test_parse_interval_rejects_non_positive_and_invalid_units(self) -> None:
        for value in ("0m", "-15m", "15x", "abc"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_interval(value)

    def test_parse_interval_converts_supported_units(self) -> None:
        self.assertEqual(parse_interval("15s"), 15)
        self.assertEqual(parse_interval("2m"), 120)
        self.assertEqual(parse_interval("1h"), 3600)
        self.assertEqual(parse_interval("1d"), 86400)

    def test_parse_count_rejects_empty_or_negative_values(self) -> None:
        self.assertEqual(parse_count("0"), 0)
        self.assertEqual(parse_count("3"), 3)
        for value in ("", " ", "-1", "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_count(value)

    def test_scheduler_rejects_invalid_interval_and_count(self) -> None:
        generator = Mock()
        with tempfile.TemporaryDirectory() as output_dir:
            scheduler = PeriodicPostScheduler(generator, output_dir=output_dir)

            with self.assertRaises(ValueError):
                scheduler.schedule({}, interval_seconds=0, count=1)
            with self.assertRaises(ValueError):
                scheduler.schedule({}, interval_seconds=1, count=-1)

        generator.generate_post.assert_not_called()

    def test_cli_rejects_negative_count_and_invalid_interval(self) -> None:
        invalid_arguments = (
            ["app.py", "--topic", "   "],
            ["app.py", "--topic", "topic", "--count", "-1"],
            ["app.py", "--topic", "topic", "--interval", "0m"],
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with patch.object(sys, "argv", arguments):
                    with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                        cli_module.main()
                self.assertEqual(error.exception.code, 2)

    def test_openai_uses_current_sdk_client(self) -> None:
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps({"caption": "mock caption", "hashtags": ["mock"]})
                )
            )
        ]
        openai_module = Mock()
        openai_module.OpenAI.return_value = client

        with patch.object(generator_module, "openai", openai_module):
            generator = SocialMediaPostGenerator(api_key="test-token")
            post = generator.generate_post("topic")

        self.assertEqual(post["caption"], "mock caption")
        client.chat.completions.create.assert_called_once()

    def test_openai_failure_is_logged_and_falls_back(self) -> None:
        client = Mock()
        client.chat.completions.create.side_effect = RuntimeError("private provider response")
        openai_module = Mock()
        openai_module.OpenAI.return_value = client

        with patch.object(generator_module, "openai", openai_module):
            generator = SocialMediaPostGenerator(api_key="test-token")
            with self.assertLogs(generator_module.logger, level="WARNING") as logs:
                post = generator.generate_post("topic")

        self.assertTrue(post["caption"])
        self.assertIn("OpenAI generation failed", logs.output[0])
        self.assertIn("RuntimeError", logs.output[0])
        self.assertNotIn("private provider response", logs.output[0])

    def test_huggingface_and_cohere_use_bearer_token(self) -> None:
        provider_cases = (
            (
                "huggingface",
                "_generate_huggingface",
                [{"generated_text": json.dumps({"caption": "mock caption", "hashtags": ["mock"]})}],
            ),
            (
                "cohere",
                "_generate_cohere",
                {
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"caption": "mock caption", "hashtags": ["mock"]}),
                            }
                        ]
                    },
                    "finish_reason": "COMPLETE",
                },
            ),
        )

        for provider, method_name, response_payload in provider_cases:
            with self.subTest(provider=provider):
                requests_module = Mock()
                requests_module.post.return_value.json.return_value = response_payload
                with patch.object(generator_module, "requests", requests_module):
                    generator = SocialMediaPostGenerator(
                        api_key="test-token",
                        provider=provider,
                    )
                    post = getattr(generator, method_name)(
                        "topic", "instagram", "friendly", "short", "English", "text", None
                    )

                self.assertEqual(post["caption"], "mock caption")
                headers = requests_module.post.call_args.kwargs["headers"]
                self.assertEqual(headers["Authorization"], "Bearer test-token")
                if provider == "cohere":
                    args = requests_module.post.call_args
                    self.assertEqual(args.args[0], generator_module.COHERE_INFERENCE_URL)
                    self.assertEqual(args.kwargs["json"]["messages"][0]["role"], "user")
                    self.assertEqual(
                        args.kwargs["json"]["response_format"],
                        {"type": "json_object"},
                    )

    def test_cohere_model_is_loaded_from_environment(self) -> None:
        with patch.dict("os.environ", {"COHERE_MODEL": "custom-cohere-model"}):
            generator = SocialMediaPostGenerator(api_key="test-token", provider="cohere")

        self.assertEqual(generator.provider_model, "custom-cohere-model")

    def test_provider_http_failure_falls_back_to_local_generation(self) -> None:
        for provider, method_name in (
            ("huggingface", "_generate_huggingface"),
            ("cohere", "_generate_cohere"),
        ):
            with self.subTest(provider=provider):
                requests_module = Mock()
                requests_module.post.side_effect = RuntimeError("private provider response")
                with patch.object(generator_module, "requests", requests_module):
                    generator = SocialMediaPostGenerator(
                        api_key="test-token",
                        provider=provider,
                    )
                    with self.assertLogs(generator_module.logger, level="WARNING") as logs:
                        post = getattr(generator, method_name)(
                            "topic", "instagram", "friendly", "short", "English", "text", None
                        )

                self.assertTrue(post["caption"])
                self.assertIn("using local generation", logs.output[0])
                self.assertIn("RuntimeError", logs.output[0])
                self.assertNotIn("private provider response", logs.output[0])

    def test_provider_error_payload_falls_back_and_is_logged(self) -> None:
        provider_cases = (
            ("huggingface", "_generate_huggingface", {"error": "private provider detail"}),
            ("cohere", "_generate_cohere", {"message": "private provider detail"}),
        )
        for provider, method_name, response_payload in provider_cases:
            with self.subTest(provider=provider):
                requests_module = Mock()
                requests_module.post.return_value.json.return_value = response_payload
                with patch.object(generator_module, "requests", requests_module):
                    generator = SocialMediaPostGenerator(
                        api_key="test-token",
                        provider=provider,
                    )
                    with self.assertLogs(generator_module.logger, level="WARNING") as logs:
                        post = getattr(generator, method_name)(
                            "topic", "instagram", "friendly", "short", "English", "text", None
                        )

                self.assertTrue(post["caption"])
                self.assertIn("using local generation", logs.output[0])
                self.assertNotIn("private provider detail", logs.output[0])
