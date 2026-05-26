import os
import random
from typing import Dict, List, Optional

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None

PLATFORM_DESCRIPTIONS = {
    "instagram": "a warm, engaging caption with emoji-friendly phrasing and hashtag support",
    "linkedin": "a professional and insightful post tailored for personal branding and career engagement",
    "twitter": "a concise, punchy tweet optimized for engagement and quick readability",
    "facebook": "a conversational and shareable post with a friendly tone",
    "youtube": "a YouTube video caption and description built to increase watch time and discoverability",
    "youtube_shorts": "a short-form YouTube Shorts caption designed for quick views and shares",
}

MEDIA_TYPE_DESCRIPTIONS = {
    "text": "a text-only update",
    "image": "a post featuring an image",
    "video": "a post featuring a video",
}

TONE_PROMPTS = {
    "friendly": "warm, upbeat, and approachable",
    "professional": "polished, clear, and authoritative",
    "motivational": "inspiring, confident, and uplifting",
    "funny": "playful, witty, and lighthearted",
    "educational": "informative, helpful, and easy to follow",
}

LENGTH_PATTERNS = {
    "short": (1, 2),
    "medium": (2, 4),
    "long": (4, 7),
}

DEFAULT_HASHTAG_KEYWORDS = [
    "AI", "socialmedia", "content", "marketing", "digital", "brand", "online", "storytelling", "strategy"
]


class SocialMediaPostGenerator:
    def __init__(self, api_key: Optional[str] = None, openai_model: str = "gpt-3.5-turbo") -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.openai_model = openai_model
        self.use_openai = bool(self.api_key and openai)
        if self.use_openai:
            openai.api_key = self.api_key

    def generate_post(
        self,
        topic: str,
        platform: str = "instagram",
        tone: str = "friendly",
        length: str = "medium",
        language: str = "English",
        media_type: str = "text",
        media_filename: Optional[str] = None,
    ) -> Dict[str, object]:
        topic = topic.strip()
        platform = platform.lower()
        tone = tone.lower()
        length = length.lower()
        media_type = media_type.lower()

        if self.use_openai:
            return self._generate_openai(topic, platform, tone, length, language, media_type, media_filename)
        return self._generate_local(topic, platform, tone, length, language, media_type, media_filename)

    def _build_prompt(
        self,
        topic: str,
        platform: str,
        tone: str,
        length: str,
        language: str,
        media_type: str,
        media_filename: Optional[str],
    ) -> str:
        file_note = f" The media file is named {media_filename}." if media_filename else ""
        return (
            f"Compose a social media post for the topic '{topic}'. "
            f"Style it for {platform} as {PLATFORM_DESCRIPTIONS.get(platform, 'a social media post')}. "
            f"This will be published as {MEDIA_TYPE_DESCRIPTIONS.get(media_type, 'a social media update')}. "
            f"Use a {TONE_PROMPTS.get(tone, tone)} tone, in {language}. "
            f"Write the caption in {length} length, include a call to action if appropriate, and provide 5 relevant hashtags. "
            f"If the post is for YouTube or YouTube Shorts, also provide a video title, a full description, and 8 to 12 tags. "
            "Return your answer in JSON with keys: caption, hashtags, call_to_action, title, description, tags. "
            "Hashtags and tags should be arrays of strings without the '#' symbol."
            f"{file_note}"
        )

    def _generate_openai(
        self,
        topic: str,
        platform: str,
        tone: str,
        length: str,
        language: str,
        media_type: str,
        media_filename: Optional[str],
    ) -> Dict[str, object]:
        prompt = self._build_prompt(topic, platform, tone, length, language, media_type, media_filename)
        response = openai.ChatCompletion.create(
            model=self.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=400,
        )
        content = response.choices[0].message.content.strip()
        return self._parse_json_response(content, topic, platform, tone, length, language, media_type, media_filename)

    def _parse_json_response(
        self,
        text: str,
        topic: str,
        platform: str,
        tone: str,
        length: str,
        language: str,
        media_type: str,
        media_filename: Optional[str],
    ) -> Dict[str, object]:
        try:
            import json

            payload = json.loads(text)
            caption = str(payload.get("caption", "")).strip()
            hashtags = payload.get("hashtags", [])
            if not isinstance(hashtags, list):
                hashtags = [str(hashtags)]
            hashtags = [tag.lstrip("#").strip() for tag in hashtags if tag]
            call_to_action = str(payload.get("call_to_action", "")).strip()
            title = str(payload.get("title", "")).strip()
            description = str(payload.get("description", "")).strip()
            tags = payload.get("tags", [])
            if not isinstance(tags, list):
                tags = [str(tags)]
            tags = [tag.lstrip("#").strip() for tag in tags if tag]
            return {
                "topic": topic,
                "platform": platform,
                "tone": tone,
                "length": length,
                "language": language,
                "media_type": media_type,
                "media_filename": media_filename,
                "title": title,
                "description": description,
                "tags": tags,
                "caption": caption,
                "hashtags": hashtags,
                "call_to_action": call_to_action,
            }
        except Exception:
            return {
                "topic": topic,
                "platform": platform,
                "tone": tone,
                "length": length,
                "language": language,
                "media_type": media_type,
                "media_filename": media_filename,
                "title": self._build_youtube_title(topic, platform),
                "description": self._build_youtube_description(topic, platform, media_type),
                "tags": self._build_hashtags(topic, platform),
                "caption": text,
                "hashtags": self._build_hashtags(topic, platform),
                "call_to_action": "",
            }

    def _generate_local(
        self,
        topic: str,
        platform: str,
        tone: str,
        length: str,
        language: str,
        media_type: str,
        media_filename: Optional[str],
    ) -> Dict[str, object]:
        adjectives = {
            "friendly": ["bright", "friendly", "easygoing", "approachable"],
            "professional": ["polished", "credible", "professional", "insightful"],
            "motivational": ["inspiring", "uplifting", "energizing", "confident"],
            "funny": ["playful", "cheeky", "lighthearted", "witty"],
            "educational": ["helpful", "clear", "informative", "practical"],
        }
        calls_to_action = {
            "instagram": ["Share your thoughts below.", "Tag a friend who needs to see this.", "Double-tap if you agree!"],
            "linkedin": ["Let me know your perspective.", "Comment with your experience.", "Share this to your network if it helped."],
            "twitter": ["Retweet if this resonates.", "Reply with your favorite insight.", "Like and share."],
            "facebook": ["Tell us what you think.", "Share with someone who needs this.", "Comment below to join the conversation."],
            "youtube": ["Watch the full video and let me know what you think.", "Like and subscribe for more videos.", "Leave a comment with your thoughts."],
            "youtube_shorts": ["Watch this short and follow for more quick tips.", "Like and share if you enjoyed this short.", "Comment with your favorite moment."],
        }

        word_count = random.randint(*LENGTH_PATTERNS.get(length, (2, 4)))
        media_hint = ""
        if media_type == "image":
            media_hint = f" This post centers on an image titled {media_filename}."
        elif media_type == "video":
            media_hint = f" This post complements a video file named {media_filename}."

        fragments = [
            f"{topic.capitalize()} is a great moment to talk about {random.choice(adjectives.get(tone, ['something']))} ideas.{media_hint}",
            f"This {platform.replace('_', ' ')} post is written {random.choice(adjectives.get(tone, ['in a thoughtful way']))} and easy to read.",
            f"The message is built to connect with your audience and spark a conversation.",
            f"It highlights the value of {topic} while staying {random.choice(adjectives.get(tone, ['very relevant']))}.",
            f"Use this update to drive interest and invite people to engage.",
        ]

        if platform in ("youtube", "youtube_shorts"):
            fragments.insert(1, f"Use a compelling hook for {platform.replace('_', ' ')} viewers.")
            if media_type == "video":
                fragments.insert(2, "Keep the pacing strong and optimized for watch time.")

        caption = " ".join(fragments[:word_count])
        if tone == "friendly":
            caption = f"Hey there! {caption}" if not caption.startswith("Hey") else caption
        if tone == "motivational":
            caption = f"Ready to take action? {caption}"

        hashtags = self._build_hashtags(topic, platform)
        call_to_action = random.choice(calls_to_action.get(platform, calls_to_action["facebook"]))
        title = self._build_youtube_title(topic, platform)
        description = self._build_youtube_description(topic, platform, media_type)
        tags = self._build_hashtags(topic, platform)

        return {
            "topic": topic,
            "platform": platform,
            "tone": tone,
            "length": length,
            "language": language,
            "media_type": media_type,
            "media_filename": media_filename,
            "title": title,
            "description": description,
            "tags": tags,
            "caption": caption,
            "hashtags": hashtags,
            "call_to_action": call_to_action,
        }

    def _build_hashtags(self, topic: str, platform: str = "") -> List[str]:
        tokens = [part.strip("#.@") for part in topic.lower().split() if part.strip()]
        keywords = tokens + DEFAULT_HASHTAG_KEYWORDS
        if platform in ("youtube", "youtube_shorts"):
            keywords = ["youtube", "shorts"] + keywords
        unique_tags = []
        for token in keywords:
            cleaned = "".join(ch for ch in token if ch.isalnum())
            if cleaned and cleaned not in unique_tags:
                unique_tags.append(cleaned)
            if len(unique_tags) >= 8:
                break
        return [tag.lower() for tag in unique_tags if len(tag) > 1]

    def _build_youtube_title(self, topic: str, platform: str) -> str:
        if platform == "youtube_shorts":
            return f"{topic.capitalize()} | Quick YouTube Short"
        return f"{topic.capitalize()} - Watch Now"

    def _build_youtube_description(self, topic: str, platform: str, media_type: str) -> str:
        base = (
            f"In this {platform.replace('_', ' ')} video, we explore {topic}. "
            "Subscribe for more content and leave a comment with your thoughts."
        )
        if media_type == "video":
            base += " This video is packed with practical tips and engaging visuals."
        return base
