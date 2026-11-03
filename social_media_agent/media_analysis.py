import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageStat, UnidentifiedImageError


class MediaAnalysisError(ValueError):
    pass


FRAME_SIZE = 64
MAX_VIDEO_FRAMES = 3
MAX_IMAGE_PIXELS = 20_000_000


def analyze_media(path: Path, media_type: str) -> Dict[str, object]:
    if media_type == "image":
        return _analyze_image(path)
    if media_type == "video":
        return _analyze_video(path)
    raise MediaAnalysisError("Media analysis supports image or video uploads only.")


def _analyze_image(path: Path) -> Dict[str, object]:
    try:
        with Image.open(path) as source:
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise MediaAnalysisError(
                    "Image dimensions are too large for local analysis."
                )
            image = source.convert("RGB")
            image.thumbnail((FRAME_SIZE, FRAME_SIZE))
    except MediaAnalysisError:
        raise
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise MediaAnalysisError(
            "The uploaded image could not be decoded for local analysis."
        ) from exc

    return _describe_pixels(
        image,
        media_type="image",
        width=width,
        height=height,
    )


def _analyze_video(path: Path) -> Dict[str, object]:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise MediaAnalysisError(
            "Video analysis requires FFmpeg installed and available on PATH."
        )

    command = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        (
            "fps=1/10,"
            f"scale={FRAME_SIZE}:{FRAME_SIZE}:force_original_aspect_ratio=decrease,"
            f"pad={FRAME_SIZE}:{FRAME_SIZE}:(ow-iw)/2:(oh-ih)/2"
        ),
        "-frames:v",
        str(MAX_VIDEO_FRAMES),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaAnalysisError(
            "FFmpeg could not analyze the uploaded video within the local time limit."
        ) from exc

    frame_bytes = FRAME_SIZE * FRAME_SIZE * 3
    if result.returncode != 0 or not result.stdout or len(result.stdout) % frame_bytes:
        raise MediaAnalysisError(
            "The uploaded video could not be decoded for local frame analysis."
        )

    raw_frames = [
        result.stdout[offset:offset + frame_bytes]
        for offset in range(0, len(result.stdout), frame_bytes)
    ]
    if len(raw_frames) > MAX_VIDEO_FRAMES:
        raise MediaAnalysisError("Video analysis returned more frames than allowed.")

    images = [
        Image.frombytes("RGB", (FRAME_SIZE, FRAME_SIZE), frame)
        for frame in raw_frames
    ]
    analyzed = [_pixel_features(image) for image in images]
    color_counts: Counter[str] = Counter()
    for features in analyzed:
        color_counts.update(features["dominant_colors"])

    brightness_values = [float(features["brightness_value"]) for features in analyzed]
    average_brightness = sum(brightness_values) / len(brightness_values)
    brightness = _brightness_label(average_brightness)
    dominant_colors = [name for name, _ in color_counts.most_common(3)]
    visual_change = _visual_change(raw_frames)
    visual_change_label = (
        "low" if visual_change < 0.08 else "moderate" if visual_change < 0.25 else "high"
    )
    color_text = ", ".join(dominant_colors) if dominant_colors else "mixed"
    summary = (
        f"Local video sample: {len(images)} frames sampled at up to 10-second "
        f"intervals; {brightness} average brightness; mostly {color_text} tones; "
        f"{visual_change_label} visual change between sampled frames."
    )
    return {
        "media_type": "video",
        "frames_sampled": len(images),
        "sample_interval_seconds": 10,
        "brightness": brightness,
        "dominant_colors": dominant_colors,
        "visual_change": visual_change_label,
        "summary": summary,
    }


def _describe_pixels(
    image: Image.Image,
    media_type: str,
    width: int,
    height: int,
) -> Dict[str, object]:
    features = _pixel_features(image)
    dominant_colors = features["dominant_colors"]
    color_text = ", ".join(dominant_colors) if dominant_colors else "mixed"
    orientation = (
        "landscape" if width > height else "portrait" if height > width else "square"
    )
    brightness = _brightness_label(float(features["brightness_value"]))
    summary = (
        f"Local image analysis: {width}x{height} pixels, {orientation} orientation; "
        f"{brightness} brightness; mostly {color_text} tones."
    )
    return {
        "media_type": media_type,
        "width": width,
        "height": height,
        "orientation": orientation,
        "brightness": brightness,
        "dominant_colors": dominant_colors,
        "summary": summary,
    }


def _pixel_features(image: Image.Image) -> Dict[str, object]:
    thumbnail = image.convert("RGB")
    thumbnail.thumbnail((FRAME_SIZE, FRAME_SIZE))
    brightness_value = ImageStat.Stat(thumbnail.convert("L")).mean[0] / 255
    quantized = thumbnail.quantize(colors=3)
    palette = quantized.getpalette()
    colors = quantized.getcolors(maxcolors=FRAME_SIZE * FRAME_SIZE) or []
    top_colors = sorted(colors, reverse=True)[:3]
    dominant_colors = [
        _color_name(tuple(palette[index * 3:index * 3 + 3]))
        for _, index in top_colors
    ]
    return {
        "brightness_value": brightness_value,
        "dominant_colors": dominant_colors,
    }


def _color_name(rgb: Tuple[int, ...]) -> str:
    red, green, blue = rgb
    high = max(rgb)
    low = min(rgb)
    if high - low < 24:
        return "dark" if high < 72 else "light" if high > 190 else "neutral"
    if red >= green and red >= blue:
        return "orange" if green > red * 0.55 else "red"
    if green >= red and green >= blue:
        return "yellow-green" if red > green * 0.55 else "green"
    return "purple" if red > blue * 0.55 else "blue"


def _brightness_label(value: float) -> str:
    return "dark" if value < 0.3 else "bright" if value > 0.7 else "balanced"


def _visual_change(frames: List[bytes]) -> float:
    if len(frames) < 2:
        return 0.0
    changes = []
    for previous, current in zip(frames, frames[1:]):
        difference = sum(abs(left - right) for left, right in zip(previous, current))
        changes.append(difference / (len(previous) * 255))
    return sum(changes) / len(changes)
