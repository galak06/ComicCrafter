"""Vision checks on drawn art: writing the image model painted in, broken human anatomy, and where the hero's head is."""

import logging
from io import BytesIO
from typing import Dict, Optional, Sequence

from PIL import Image

from book_comic.comic_rules import ANATOMY_RULE, NO_TEXT_RULE
from generation.openrouter_image_client import OpenRouterImageClient
from generation.vision_client import VisionClient

logger = logging.getLogger(__name__)

INSPECT_PROMPT = (
    'Look at this illustration. Return only JSON {"head_top": y, "has_text": b, "bad_anatomy": a}. y: the top of '
    "the main character's head (hair or hat included) in thousandths of the image height, 0 the top edge, 1000 the "
    "bottom. b: true if the image contains any readable or garbled letters, words, captions, labels or signs, else "
    "false. a: true if any person has more than two arms or more than two hands, a hand with more than five "
    "fingers, or a hand or arm that belongs to nobody; false otherwise (a hand hidden out of frame is fine)."
)


def inspect_art(image: Image.Image, vision: VisionClient) -> Dict[str, Optional[object]]:
    """One vision call on drawn art.

    Returns:
        {"head_top": share of the height (0 = top) or None, "has_text": bool or None, "bad_anatomy": bool or None};
        None values when the check failed, so a failed check never blocks the art
    """
    found: Dict[str, Optional[object]] = {"head_top": None, "has_text": None, "bad_anatomy": None}
    small = image.copy()
    small.thumbnail((768, 768))
    try:
        answer = vision.ask_json(INSPECT_PROMPT, small)
    except Exception as e:
        logger.warning(f"Art check failed; keeping the art: {e}")
        return found
    if not isinstance(answer, dict):
        return found
    if isinstance(answer.get("head_top"), (int, float)) and not isinstance(answer.get("head_top"), bool):
        found["head_top"] = min(1.0, max(0.0, float(answer["head_top"]) / 1000))
    for key in ("has_text", "bad_anatomy"):
        if isinstance(answer.get(key), bool):
            found[key] = answer[key]
    return found


def request_art(
    images: OpenRouterImageClient, prompt: str, references: Sequence[str], aspect_ratio: str
) -> Image.Image:
    """One image call, decoded to RGB."""
    data = images.generate_image(prompt, aspect_ratio=aspect_ratio, references=references)
    return Image.open(BytesIO(data)).convert("RGB")


def draw_checked(
    images: OpenRouterImageClient,
    vision: VisionClient,
    prompt: str,
    references: Sequence[str],
    aspect_ratio: str,
) -> Image.Image:
    """Draw art and check it for painted-in writing and broken human anatomy (image models ignore both rules at times).

    Art with either is drawn once more with the broken rule repeated; the second art is kept either way.
    """
    art = request_art(images, prompt, references, aspect_ratio)
    found = inspect_art(art, vision)
    repeat = (NO_TEXT_RULE if found["has_text"] else "") + (f" {ANATOMY_RULE}" if found["bad_anatomy"] else "")
    if repeat:
        logger.info("Art has painted-in text or broken anatomy; drawing it once more")
        art = request_art(images, f"{prompt} {repeat.strip()}", references, aspect_ratio)
    return art
