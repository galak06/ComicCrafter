"""A lettered sound effect ("BOOM!", "בום!"): bold tilted display type drawn over finished panel art.

The image model never hears about it (painted sound effects stay has_text defects); the engine letters it
after the caption, bubbles and note, in free space near the source of the noise. It is decoration: whatever
goes wrong (no free spot, a font problem, a bad point), draw_sfx reports why and draws nothing.
"""

import math
from functools import lru_cache
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFont

from layout.lettering import FONTS_DIR, INK, PAPER, Rect, _font, _hits, is_rtl

SFX_FONT = FONTS_DIR / "Rubik-Black.ttf"  # bundled, Hebrew and Latin
SIZE_STEPS = (1.6, 1.45, 1.3, 1.15, 1.0)  # of the dialogue size: the largest that fits and finds a spot is drawn
DIALOGUE_SIZE = 0.05  # dialogue type as a share of the type height (layout.comic_bubbles)
MAX_WIDTH, MAX_HEIGHT = 0.45, 0.30  # the tilted effect's box, as shares of the panel
MAX_CHARS = 40  # longer text is not even measured; up to this, the size rules alone decide
TILT = 7  # degrees; the word rises the way it is read
STROKE = 0.075  # outline width as a share of the type size
Point = Tuple[float, float]


def sfx_text(value) -> str:
    """The panel's sound effect as one line ("" for none, or for anything that is not a string)."""
    return " ".join(value.split()) if isinstance(value, str) else ""


@lru_cache(maxsize=256)
def _covered(path: str, text: str) -> bool:
    """Whether the face has a glyph for every character (a missing one draws the face's empty box)."""
    font = ImageFont.truetype(path, 40, layout_engine=ImageFont.Layout.BASIC)
    missing = bytes(font.getmask("￿"))
    return all(bytes(font.getmask(ch)) != missing for ch in set(text) if not ch.isspace())


def sfx_font(size: int, text: str, font_path: Optional[str] = None) -> ImageFont.ImageFont:
    """Rubik Black, or the lettering font (font_path, else the bundled defaults) when it lacks a glyph."""
    try:
        if _covered(str(SFX_FONT), text):
            return ImageFont.truetype(str(SFX_FONT), size)
    except OSError:
        pass
    return _font(size, text, font_path)


def sfx_layer(text: str, size: int, font_path: Optional[str] = None) -> Image.Image:
    """The whole word on a transparent layer: paper fill, ink outline, tilted as one piece, cropped to its ink.

    The string is shaped once (Hebrew through the same raqm path as the other lettering) and the layer is
    rotated, never the letters one by one.
    """
    font = sfx_font(size, text, font_path)
    hebrew = is_rtl(text)
    stroke = max(3, round(size * STROKE))
    style = {"font": font, "stroke_width": stroke, "direction": "rtl" if hebrew else "ltr"}
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    try:
        left, top, right, bottom = probe.textbbox((0, 0), text, **style)
    except (KeyError, ValueError):  # Pillow without libraqm cannot set direction (as in cover_lettering)
        style.pop("direction")
        left, top, right, bottom = probe.textbbox((0, 0), text, **style)
    pad = stroke + 2
    layer = Image.new("RGBA", (right - left + 2 * pad, bottom - top + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad - left, pad - top), text, fill=PAPER + (255,), stroke_fill=INK + (255,), **style)
    # Pillow turns counter-clockwise: Latin rises to the right, Hebrew (read leftwards) rises to the left.
    layer = layer.rotate(-TILT if hebrew else TILT, resample=Image.Resampling.BICUBIC, expand=True)
    return layer.crop(layer.getbbox()) if layer.getbbox() else layer


def lettering_ink(art: Image.Image, lettered: Image.Image) -> Optional[Image.Image]:
    """Mask of every pixel the lettering changed (caption, bubbles, tails, note); None when nothing changed."""
    if art.size != lettered.size:
        return None
    bands = ImageChops.difference(art.convert("RGB"), lettered.convert("RGB")).split()
    mask = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2]).point(lambda v: 255 if v else 0)
    return mask if mask.getbbox() else None


def _target(near, size: Tuple[int, int], box: Tuple[int, int], rtl: bool, margin: int) -> Point:
    """Where the effect's centre would like to be: the planner's point, else the upper reading-end corner."""
    w, h = size
    try:
        x, y = (float(v) for v in near)
        if all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
            return (x * w, y * h)
    except (TypeError, ValueError):
        pass
    return (margin + box[0] / 2 if rtl else w - margin - box[0] / 2, margin + box[1] / 2)


def find_spot(size: Tuple[int, int], box: Tuple[int, int], target: Point, obstacles: Sequence[Rect],
              ink: Optional[Image.Image] = None) -> Optional[Tuple[int, int]]:
    """Top-left corner of the free spot whose centre is nearest target (the bubbles' grid search), or None.

    Free: inside the panel's edge margin, a gap away from every obstacle rectangle and from every inked pixel.
    """
    w, h = size
    bw, bh = box
    gap, edge = max(6, h // 80), max(8, h // 40)  # the bubbles' gap; the captions' distance from the panel edge
    spots = [(math.hypot(x0 + bw / 2 - target[0], y0 + bh / 2 - target[1]), x0, y0)
             for y0 in range(edge, h - bh - edge + 1, max(4, h // 40))
             for x0 in range(edge, w - bw - edge + 1, max(4, w // 60))]
    for _, x0, y0 in sorted(spots):
        if any(_hits((x0, y0, bw, bh), o, gap) for o in obstacles):
            continue
        if ink is not None and ink.crop((max(0, x0 - gap), max(0, y0 - gap), min(w, x0 + bw + gap),
                                         min(h, y0 + bh + gap))).getbbox():
            continue
        return x0, y0
    return None


def draw_sfx(image: Image.Image, text: str, near: Optional[Point], obstacles: List[Rect], rtl: bool = False,
             type_height: Optional[int] = None, ink: Optional[Image.Image] = None,
             font_path: Optional[str] = None) -> Tuple[Optional[Rect], Optional[str]]:
    """Draw a sound effect on the panel in place; returns (its box, None) or (None, why it was left out).

    Args:
        image: Lettered panel (RGB), drawn on in place only when a spot is found
        text: The effect, one line
        near: Wanted centre, normalized 0-1 (the planner's point by the noise); None or an unusable value
            starts from the upper corner read last (top-right, or top-left in a right-to-left comic)
        obstacles: Rectangles to stay a gap away from (heads, protected subjects, lettering boxes)
        rtl: The comic's reading direction (only picks the fallback corner; the tilt follows the text)
        type_height: Panel height the type is sized for (default: the image's own height)
        ink: lettering_ink mask of pixels to stay a gap away from
        font_path: Lettering font used when Rubik Black lacks a glyph

    Reasons: "empty", "too_long" (over MAX_CHARS), "too_big" (over the size cap even at the dialogue size),
    "no_space" (no free spot at any size).
    """
    text = sfx_text(text)
    if not text:
        return None, "empty"
    if len(text) > MAX_CHARS:
        return None, "too_long"
    w, h = image.size
    base = max(16, int((type_height or h) * DIALOGUE_SIZE))
    edge = max(8, h // 40)
    reason = "too_big"
    for step in SIZE_STEPS:
        layer = sfx_layer(text, int(base * step), font_path)
        if layer.width > w * MAX_WIDTH or layer.height > h * MAX_HEIGHT:
            continue
        reason = "no_space"
        spot = find_spot((w, h), layer.size, _target(near, (w, h), layer.size, rtl, edge), obstacles, ink)
        if spot:
            image.paste(layer, spot, layer)
            return (spot[0], spot[1], layer.width, layer.height), None
    return None, reason
