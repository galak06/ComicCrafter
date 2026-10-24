"""Vision-based placement of speech bubbles relative to the speaking characters."""

import base64
import json
import os
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Tuple

import requests
from PIL import Image

from utils import get_logger

logger = get_logger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-lite"

Point = Tuple[float, float]  # normalized 0-1 (x, y)


@dataclass
class BubblePlan:
    """Where to put a panel's bubbles.

    Attributes:
        speakers: For each dialogue line, the speaker's mouth position (None if not visible)
        bubbles: For each dialogue line, the bubble center in empty space
        caption_corner: "top-left" or "top-right"
    """
    speakers: List[Optional[Point]]
    bubbles: List[Point]
    caption_corner: str = "top-left"


def _prompt(lines: List[Tuple[str, str]], has_caption: bool, rtl: bool = False) -> str:
    order = "further right (this comic reads right-to-left)" if rtl else "further left"
    numbered = "\n".join(f'{i + 1}. {speaker or "unknown"}: "{text}"' for i, (speaker, text) in enumerate(lines))
    return f"""This is a comic book panel. Speech bubbles will be drawn on it for these lines:
{numbered}

For each line, find the speaking character in the image and return:
- "mouth": [x, y] of that character's mouth, or null if the speaker isn't visible
- "bubble": [x, y] center for the bubble in EMPTY space near the speaker (sky, background, wall),
  never covering any face or the main action, ideally above or beside the speaker's head.
  Bubbles for different lines must not overlap; earlier lines go higher and {order}.
{'Also pick "caption": "top-left" or "top-right", whichever corner covers less of the important art.' if has_caption else ''}

Coordinates are integers from 0 to 1000 (0,0 is top-left, 1000,1000 bottom-right).
Respond with only JSON: {{"lines": [{{"mouth": [x, y], "bubble": [x, y]}}], "caption": "top-left"}}"""


def _encode(image: Image.Image) -> str:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def _point(value) -> Optional[Point]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = (min(1.0, max(0.0, float(v) / 1000)) for v in value)
    return (x, y)


def plan_bubbles(
    image: Image.Image, lines: List[Tuple[str, str]], has_caption: bool, rtl: bool = False
) -> Optional[BubblePlan]:
    """Ask a vision model where each speaker is and where their bubble fits.

    Args:
        image: Panel image
        lines: (speaker, text) for each dialogue line; speaker may include a short look description
        has_caption: Whether the panel also has a narration caption
        rtl: Whether the comic reads right-to-left

    Returns:
        BubblePlan, or None if the request or response failed
    """
    model = os.getenv("OPENROUTER_VISION_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _prompt(lines, has_caption, rtl)},
                {"type": "image_url", "image_url": {"url": _encode(image)}},
            ],
        }],
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        # Models sometimes return the bare lines array instead of the wrapping object
        start = min(i for i in (content.find("{"), content.find("[")) if i != -1)
        data = json.loads(content[start:max(content.rfind("}"), content.rfind("]")) + 1])
        if isinstance(data, list):
            data = {"lines": data}

        planned = data.get("lines", [])
        if len(planned) < len(lines):
            raise ValueError(f"expected {len(lines)} lines, got {len(planned)}")

        bubbles = [_point(p.get("bubble")) for p in planned[:len(lines)]]
        if any(b is None for b in bubbles):
            raise ValueError("missing bubble position")

        corner = data.get("caption", "top-left")
        return BubblePlan(
            speakers=[_point(p.get("mouth")) for p in planned[:len(lines)]],
            bubbles=bubbles,
            caption_corner=corner if corner in ("top-left", "top-right") else "top-left",
        )
    except Exception as e:
        logger.warning(f"Bubble planning with {model} failed; using default placement: {e}")
        return None


def default_plan(num_lines: int) -> BubblePlan:
    """Fallback placement: bubbles across the top, tails pointing down."""
    bubbles = [((i + 0.5) / max(1, num_lines), 0.18) for i in range(num_lines)]
    return BubblePlan(speakers=[None] * num_lines, bubbles=bubbles)
