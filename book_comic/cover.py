"""The comic's front cover: one portrait hero shot the size of a page, lettered afterwards.

The image model sometimes stacks a second strip of the scene over the top (a seam), paints in
writing, or puts the head up where the title goes; any of these gets one more image call.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from PIL import Image, ImageOps

from book_comic.art_check import inspect_art, request_art
from book_comic.cover_lettering import CoverFonts, letter_cover
from book_comic.image_prompts import cover_prompt
from book_comic.render import image_url
from generation.openrouter_image_client import OpenRouterImageClient, closest_aspect_ratio
from generation.vision_client import VisionClient

logger = logging.getLogger(__name__)

# The one-line title and the starring line end near 14% of the height; a head starting above 20%
# would crowd them (measured on real covers: 0.16 crowds, 0.19-0.24 leaves clear space).
HEAD_TOP_MIN = 0.2
ATTEMPTS = 2


def find_seam(image: Image.Image, search_share: float = 0.45) -> Optional[int]:
    """The row just below a thin, flat, full-width line across the top of the art where the model
    stacked a second strip; None when there is none. Only a run of at most 2% of the height with
    textured art on both sides counts, so a plain sky is not a seam."""
    import numpy as np
    flat = np.asarray(image.convert("RGB"), dtype=np.float32).std(axis=1).max(axis=1) < 20
    h = len(flat)
    thin, gap = max(3, int(h * 0.02)), max(2, h // 300)
    y = gap
    while y < int(h * search_share):
        if not flat[y]:
            y += 1
            continue
        run_end = y
        while run_end < h and flat[run_end]:
            run_end += 1
        if run_end - y <= thin and run_end + gap < h and not flat[y - gap] and not flat[run_end + gap]:
            return run_end
        y = run_end + 1
    return None


def panel_strip(arts: Sequence[Image.Image], height: int = 512, gap: int = 16) -> Optional[Image.Image]:
    """Panels side by side in reading order, so the cover sees every prop and companion. None if empty."""
    if not arts:
        return None
    scaled = [a.convert("RGB").resize((max(1, round(a.width * height / a.height)), height)) for a in arts]
    strip = Image.new("RGB", (sum(a.width for a in scaled) + gap * (len(scaled) - 1), height), "white")
    x = 0
    for art in scaled:
        strip.paste(art, (x, 0))
        x += art.width + gap
    return strip


def render_cover(
    cast: Dict,
    cover: Dict,
    size: tuple,
    path: Path,
    images: OpenRouterImageClient,
    vision: VisionClient,
    panels: Sequence[Image.Image] = (),
    references: Sequence[str] = (),
    reference_roles: Sequence[str] = (),
    fonts: Optional[CoverFonts] = None,
    dpi: Optional[int] = None,
) -> Path:
    """Draw and letter the cover; at most ATTEMPTS image calls.

    Art without a seam, without painted-in text and with the head below the title block wins at once;
    otherwise the better attempt (no seam, then no text, then the lower head). A seam left is cut off.

    Args:
        cast: Character sheet (style, characters, optional props)
        cover: {"scene", "title", optional "starring", "footer", "title_font"}
        size: Cover size in pixels (normally the page size)
        path: Where the lettered cover PNG is saved
        images: Image client
        vision: Vision client for the text and head check
        panels: The first page's unlettered panels, sent as one reference strip
        references: Other reference URLs (photo, character sheet), described by reference_roles
        reference_roles: Kind of each reference (see image_prompts.REFERENCE_ROLES)
        fonts: Cover faces (cover["title_font"] still overrides the title face)
        dpi: DPI tag for the saved PNG
    """
    references, roles = list(references), list(reference_roles)
    strip = panel_strip(panels)
    if strip is not None:
        references.append(image_url(strip))
        roles.append("panels")
    prompt = cover_prompt(cast, cover, roles)

    candidates: List[tuple] = []
    for _ in range(ATTEMPTS):
        art = ImageOps.fit(request_art(images, prompt, references, closest_aspect_ratio(*size)), size)
        seam = find_seam(art)
        found = inspect_art(art, vision) if seam is None else {"head_top": None, "has_text": None}
        head = found["head_top"] if found["head_top"] is not None else 1.0
        clean = not found["has_text"]
        candidates.append((seam is None, clean, head, art, seam))
        if seam is None and clean and head >= HEAD_TOP_MIN:
            break
        logger.info(f"Cover attempt rejected (seam={seam}, text={found['has_text']}, head_top={head:.2f})")
    _, _, head, art, seam = max(candidates, key=lambda c: (c[0], c[1], c[2]))
    if seam is not None:
        art = ImageOps.fit(art.crop((0, seam, art.width, art.height)), size, centering=(0.5, 0.0))

    dpi_tag = {"dpi": (dpi, dpi)} if dpi else {}
    # Every attempt drew the head up in the title block: letter the title at the bottom, never over the face.
    letter_cover(art, cover, fonts, title_at_bottom=head < HEAD_TOP_MIN).save(path, format="PNG", optimize=True, **dpi_tag)
    logger.info(f"Saved cover {path}")
    return path
