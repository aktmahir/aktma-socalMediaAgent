import base64
import io
import json
import math
import numbers
import shutil
import subprocess
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import ExifTags, Image, ImageOps, ImageStat, UnidentifiedImageError


class MediaAnalysisError(ValueError):
    pass


FRAME_SIZE = 64
MAX_VIDEO_FRAMES = 3
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_FRAMES_TO_INSPECT = 100
MAX_TOTAL_IMAGE_FRAME_PIXELS = 80_000_000

IMAGE_FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".gif": "GIF",
}


def scan_for_malware(path: Path) -> Dict[str, str]:
    scanner_path = shutil.which("clamscan")
    if scanner_path is None:
        return {"status": "unscanned", "reason": "scanner_unavailable"}

    try:
        result = subprocess.run(
            [scanner_path, "--no-summary", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unscanned", "reason": "scanner_error"}

    if result.returncode == 0:
        return {"status": "clean"}
    if result.returncode == 1:
        return {"status": "infected"}
    return {"status": "unscanned", "reason": "scanner_error"}


def analyze_media(path: Path, media_type: str) -> Dict[str, object]:
    if media_type == "image":
        return _analyze_image(path)
    if media_type == "video":
        return _analyze_video(path)
    raise MediaAnalysisError("Media analysis supports image or video uploads only.")


def prepare_vision_images(path: Path, media_type: str) -> List[str]:
    if media_type == "image":
        try:
            with Image.open(path) as source:
                _validate_image_format(path, source)
                source.seek(0)
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((1024, 1024))
                return [_image_data_url(image)]
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise MediaAnalysisError(
                "The uploaded image could not be prepared for vision analysis."
            ) from exc

    if media_type == "video":
        return _prepare_video_frames(path)

    raise MediaAnalysisError("Vision analysis supports image or video uploads only.")


def _analyze_image(path: Path) -> Dict[str, object]:
    try:
        with Image.open(path) as source:
            _validate_image_format(path, source)
            width, height = source.size
            image_format = source.format or "unknown"
            color_mode = source.mode
            exif = source.getexif()
            exif_orientation = exif.get(274)
            exif_metadata, exif_tag_names = _extract_exif_metadata(exif)
            image = ImageOps.exif_transpose(source).convert("RGB")
            width, height = image.size
            image.thumbnail((FRAME_SIZE, FRAME_SIZE))
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise MediaAnalysisError(
                    "Image dimensions are too large for local analysis."
                )
            frame_limit = min(
                MAX_IMAGE_FRAMES_TO_INSPECT,
                max(1, MAX_TOTAL_IMAGE_FRAME_PIXELS // (width * height)),
            )
            frame_count = _validate_image_frames(source, frame_limit)
            frame_duration_ms = source.info.get("duration")
            dpi = source.info.get("dpi")
            has_icc_profile = bool(source.info.get("icc_profile"))
    except MediaAnalysisError:
        raise
    except (
        OSError,
        ValueError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as exc:
        raise MediaAnalysisError(
            "The uploaded image could not be decoded for local analysis."
        ) from exc

    result = _describe_pixels(
        image,
        media_type="image",
        width=width,
        height=height,
    )
    result.update(
        {
            "format": image_format,
            "color_mode": color_mode,
            "exif_orientation": exif_orientation,
            "exif_tag_names": exif_tag_names,
            "exif_metadata": exif_metadata,
            "gps_metadata_present": bool(exif.get(34853)),
            "has_icc_profile": has_icc_profile,
            "frame_count": frame_count,
            "is_animated": frame_count > 1,
        }
    )
    if isinstance(frame_duration_ms, (int, float)) and math.isfinite(frame_duration_ms):
        result["first_frame_duration_ms"] = frame_duration_ms
    if isinstance(dpi, tuple) and len(dpi) == 2:
        result["dpi"] = [round(float(value), 2) for value in dpi]
    return result


def _analyze_video(path: Path) -> Dict[str, object]:
    metadata = _probe_video(path)
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
        **metadata,
        "frames_sampled": len(images),
        "sample_interval_seconds": 10,
        "brightness": brightness,
        "dominant_colors": dominant_colors,
        "visual_change": visual_change_label,
        "summary": summary,
    }


def _prepare_video_frames(path: Path) -> List[str]:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise MediaAnalysisError(
            "Video vision analysis requires FFmpeg installed and available on PATH."
        )

    frame_size = 512
    command = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        (
            "fps=1/10,"
            f"scale={frame_size}:{frame_size}:force_original_aspect_ratio=decrease,"
            f"pad={frame_size}:{frame_size}:(ow-iw)/2:(oh-ih)/2"
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
            "FFmpeg could not prepare video frames for vision analysis."
        ) from exc

    frame_bytes = frame_size * frame_size * 3
    if result.returncode != 0 or not result.stdout or len(result.stdout) % frame_bytes:
        raise MediaAnalysisError(
            "Video frames could not be decoded for vision analysis."
        )

    frames = [
        result.stdout[offset:offset + frame_bytes]
        for offset in range(0, len(result.stdout), frame_bytes)
    ]
    return [
        _image_data_url(Image.frombytes("RGB", (frame_size, frame_size), frame))
        for frame in frames[:MAX_VIDEO_FRAMES]
    ]


def _probe_video(path: Path) -> Dict[str, object]:
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path is None:
        raise MediaAnalysisError(
            "Video metadata analysis requires FFprobe installed and available on PATH."
        )

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        (
            "format=format_name,duration,size,bit_rate:"
            "format_tags=major_brand:"
            "stream=codec_type,codec_name,width,height,avg_frame_rate,"
            "r_frame_rate,pix_fmt,sample_aspect_ratio,display_aspect_ratio,"
            "sample_rate,channels,channel_layout,duration,bit_rate:"
            "stream_tags=rotate:stream_side_data=rotation"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaAnalysisError(
            "FFprobe could not inspect the uploaded video within the local time limit."
        ) from exc

    if result.returncode != 0:
        raise MediaAnalysisError("The uploaded video metadata could not be parsed.")

    try:
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("Unexpected FFprobe response shape.")
        format_info = payload.get("format", {})
        streams = payload.get("streams", [])
        if not isinstance(format_info, dict) or not isinstance(streams, list):
            raise ValueError("Unexpected FFprobe response shape.")
        video_source_streams = [
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ]
        if not video_source_streams:
            raise ValueError("No video stream found.")
        _validate_video_container(path, format_info)
        duration_value = _parse_duration(format_info.get("duration"))
        video_streams = [
            {
                "codec": stream.get("codec_name", "unknown"),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "frame_rate": _parse_frame_rate(stream.get("avg_frame_rate")),
                "pixel_format": stream.get("pix_fmt"),
                "sample_aspect_ratio": stream.get("sample_aspect_ratio"),
                "display_aspect_ratio": stream.get("display_aspect_ratio"),
                "rotation_degrees": _stream_rotation(stream),
                "duration_seconds": _parse_duration(stream.get("duration")),
                "bit_rate": _parse_nonnegative_int(stream.get("bit_rate")),
            }
            for stream in video_source_streams
        ]
        if any(
            not isinstance(stream["width"], int)
            or not isinstance(stream["height"], int)
            or stream["width"] <= 0
            or stream["height"] <= 0
            for stream in video_streams
        ):
            raise ValueError("Invalid video stream dimensions.")
        return {
            "container": format_info.get("format_name", "unknown"),
            "duration_seconds": duration_value,
            "size_bytes": _parse_nonnegative_int(format_info.get("size")),
            "bit_rate": _parse_nonnegative_int(format_info.get("bit_rate")),
            "video_stream_count": len(video_streams),
            "video_streams": video_streams[:8],
            "audio_streams": [
                {
                    "codec": stream.get("codec_name", "unknown"),
                    "sample_rate_hz": _parse_nonnegative_int(stream.get("sample_rate")),
                    "channels": _parse_nonnegative_int(stream.get("channels")),
                    "channel_layout": stream.get("channel_layout"),
                    "duration_seconds": _parse_duration(stream.get("duration")),
                    "bit_rate": _parse_nonnegative_int(stream.get("bit_rate")),
                }
                for stream in streams
                if isinstance(stream, dict) and stream.get("codec_type") == "audio"
            ][:8],
            "audio_stream_count": sum(
                1 for stream in streams
                if isinstance(stream, dict) and stream.get("codec_type") == "audio"
            ),
        }
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaAnalysisError("The uploaded video metadata could not be parsed.") from exc


def _validate_image_frames(image: Image.Image, frame_limit: int) -> int:
    frame_count = 0
    total_frame_pixels = 0
    for frame_index in range(frame_limit + 1):
        try:
            image.seek(frame_index)
        except EOFError:
            break
        image.load()
        width, height = image.size
        frame_pixels = width * height
        if width <= 0 or height <= 0 or frame_pixels > MAX_IMAGE_PIXELS:
            raise MediaAnalysisError("An image frame exceeds local parsing limits.")
        total_frame_pixels += frame_pixels
        if frame_count >= frame_limit or total_frame_pixels > MAX_TOTAL_IMAGE_FRAME_PIXELS:
            raise MediaAnalysisError(
                "The uploaded image has too many or too-large frames for local parsing."
            )
        frame_count += 1
    image.seek(0)
    return frame_count


def _parse_frame_rate(value: object) -> Optional[float]:
    if not isinstance(value, str) or "/" not in value:
        return None
    numerator, denominator = value.split("/", maxsplit=1)
    try:
        rate = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return None
    return round(rate, 3) if math.isfinite(rate) and rate > 0 else None


def _parse_duration(value: object) -> Optional[float]:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        duration = float(value)
    except ValueError:
        return None
    return round(duration, 3) if math.isfinite(duration) and duration >= 0 else None


def _parse_nonnegative_int(value: object) -> Optional[int]:
    if not isinstance(value, (str, int)):
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _stream_rotation(stream: Dict[str, object]) -> Optional[float]:
    tags = stream.get("tags")
    if isinstance(tags, dict):
        rotation = _parse_rotation(tags.get("rotate"))
        if rotation is not None:
            return rotation
    side_data = stream.get("side_data_list")
    if isinstance(side_data, list):
        for item in side_data:
            if isinstance(item, dict):
                rotation = item.get("rotation")
                if isinstance(rotation, (int, float)) and math.isfinite(rotation):
                    return round(float(rotation), 3)
    return None


def _parse_rotation(value: object) -> Optional[float]:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        angle = float(value)
    except ValueError:
        return None
    return round(angle, 3) if math.isfinite(angle) else None


def _extract_exif_metadata(exif: Image.Exif) -> Tuple[Dict[str, object], List[str]]:
    allowed_names = {
        "DateTime",
        "DateTimeOriginal",
        "Make",
        "Model",
        "Software",
        "ExposureTime",
        "FNumber",
        "ISOSpeedRatings",
        "FocalLength",
        "Flash",
        "WhiteBalance",
        "LensModel",
        "PixelXDimension",
        "PixelYDimension",
        "ColorSpace",
    }
    tag_names = set()
    metadata: Dict[str, object] = {}
    ifd_exif = getattr(ExifTags, "IFD", None)
    ifd_ids = [None]
    if ifd_exif is not None:
        ifd_ids.append(getattr(ifd_exif, "Exif", None))

    for ifd_id in ifd_ids:
        try:
            tags = exif if ifd_id is None else exif.get_ifd(ifd_id)
        except (KeyError, OSError, TypeError, ValueError):
            continue
        if not isinstance(tags, Mapping):
            continue
        for tag_id, value in tags.items():
            name = ExifTags.TAGS.get(tag_id, f"tag_{tag_id}")
            tag_names.add(name)
            if name in allowed_names:
                safe_value = _json_safe_metadata_value(value)
                if safe_value is not None:
                    metadata[name] = safe_value

    return metadata, sorted(tag_names)[:64]


def _json_safe_metadata_value(value: object) -> Optional[object]:
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    if isinstance(value, str):
        return value[:256]
    if isinstance(value, (tuple, list)) and len(value) <= 8:
        safe_values = [_json_safe_metadata_value(item) for item in value]
        if all(item is not None for item in safe_values):
            return safe_values
    return None


def _validate_video_container(path: Path, format_info: Dict[str, object]) -> None:
    format_name = format_info.get("format_name")
    if not isinstance(format_name, str):
        raise ValueError("Missing video container format.")
    normalized_formats = {name.strip().lower() for name in format_name.split(",")}
    extension = path.suffix.lower()
    if extension == ".avi" and "avi" not in normalized_formats:
        raise ValueError("Video container does not match AVI extension.")
    if extension == ".webm" and not normalized_formats.intersection({"webm", "matroska"}):
        raise ValueError("Video container does not match WebM extension.")
    if extension in {".mp4", ".mov", ".m4v"}:
        major_brand = format_info.get("tags", {})
        major_brand = major_brand.get("major_brand") if isinstance(major_brand, dict) else None
        major_brand = major_brand.lower() if isinstance(major_brand, str) else ""
        if not normalized_formats.intersection({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}):
            raise ValueError("Video container does not match QuickTime/MP4 extension.")
        if extension == ".mov" and major_brand and major_brand not in {"qt", "qt  "}:
            raise ValueError("Video major brand does not match MOV extension.")
        if extension == ".m4v" and major_brand and "m4v" not in major_brand:
            raise ValueError("Video major brand does not match M4V extension.")
        if extension == ".mp4" and major_brand and major_brand not in {
            "isom", "iso2", "mp41", "mp42", "avc1"
        }:
            raise ValueError("Video major brand does not match MP4 extension.")


def _validate_image_format(path: Path, image: Image.Image) -> None:
    expected_format = IMAGE_FORMATS.get(path.suffix.lower())
    if expected_format is None or image.format != expected_format:
        raise MediaAnalysisError(
            "The decoded image format does not match the filename extension."
        )


def _image_data_url(image: Image.Image) -> str:
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


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
