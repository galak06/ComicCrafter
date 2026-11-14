"""Cover lettering: shaded art, a one-line shadowed title, a starring line and a footer. No boxes."""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from book_comic.cover_badge import CoverBadge, place_badge
from book_comic.print_safe import DEFAULT_COVER_SAFE, CoverSafe, lettering_box
from layout.lettering import FONTS_DIR, _wrap, is_rtl

TITLE_FONT = FONTS_DIR / "Rubik-Black.ttf"
STARRING_FONT = FONTS_DIR / "Assistant-SemiBold.ttf"
FOOTER_FONT = FONTS_DIR / "Assistant-Regular.ttf"

# Where lettering may sit, as shares of the cover art, so every word prints inside the printers' text margin
# (12.7 mm inside the trim, Lulu's, plus 1 mm to spare). The defaults and how each printer's cover crop gives them
# are in book_comic/print_safe.py (CoverSafe); a caller may pass another box (letter_cover(safe=...)).
SAFE_BOTTOM = DEFAULT_COVER_SAFE.bottom  # 0.11: 14.2 mm inside BookPod's trim, 26.2 mm inside Lulu's
SAFE_TOP = DEFAULT_COVER_SAFE.top  # 0.07: 15.5 mm inside Lulu's trim (it was 0.064: 13.9 mm), 10.2 mm inside BookPod's
SAFE_WIDTH = DEFAULT_COVER_SAFE.width  # 0.78: 14.4 mm inside Lulu's side trims, 15.3 mm inside BookPod's
# The smallest a title is drawn, as a share of its own size, to stay at the top above the head (top_title_shrink).
# Real cover 2026-11-14: Amatic SC at 1.6 (a 6.1% tall title, Rubik's is 4.6%) ended 16.9% down, 0.9% above a head at
# 17.8%; the whole block went onto the hero's shin and the robot. At 0.8 of its size it clears the head by the gap.
MIN_TITLE_SHRINK = 0.75
SHRINK_STEP = 0.025


@dataclass
class CoverFonts:
    """Cover faces. title_scale enlarges narrow, light title faces so they read as boldly as Rubik Black."""
    title: Path = TITLE_FONT
    starring: Path = STARRING_FONT
    footer: Path = FOOTER_FONT
    title_scale: float = 1.0


def resolve_font(choice: Optional[Union[str, Path]], default: Path) -> Path:
    """A font file path, or the file name of a bundled font (assets/fonts); default when neither exists."""
    if not choice:
        return default
    path = Path(choice)
    if path.is_absolute() and path.is_file():
        return path
    bundled = FONTS_DIR / path.name
    if path.name == str(choice) and path.suffix in (".ttf", ".otf") and bundled.is_file():
        return bundled
    return default


def cover_title_scale(title: str) -> float:
    """Title size as a share of the cover width: 7.2%, smaller for long titles and long words."""
    longest = max([len(word) for word in title.split()] or [1])
    scale = min(1, (30 / max(30, len(title))) ** 0.5, 14 / longest)
    return max(0.032, 0.072 * scale)


def one_line_font(path: Path, title: str, size: int, max_width: int) -> ImageFont.FreeTypeFont:
    """The title's face at size, shrunk until the whole title fits on one line of max_width."""
    font = ImageFont.truetype(str(path), size)
    width = font.getlength(title)
    if width > max_width:
        font = ImageFont.truetype(str(path), max(12, int(size * max_width / width)))
    return font


def _cover_shade(size: tuple) -> Image.Image:
    """Dark at the top fading out by 38%, clear through the middle, dark again from 72% down, so white
    lettering reads on any art."""
    w, h = size
    alpha = []
    for y in range(h):
        t = y / max(1, h - 1)
        top = 0.65 * (1 - t / 0.38) if t < 0.38 else 0
        bottom = 0.7 * (t - 0.72) / 0.28 if t > 0.72 else 0
        alpha.append(int(255 * (top or bottom)))
    shade = Image.new("L", (1, h))
    shade.putdata(alpha)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    overlay.putalpha(shade.resize(size))
    return overlay


def _block(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> tuple:
    """(wrapped text, drawing style, its box at the origin) of a centred block, as _shadowed_text draws it."""
    wrapped = _wrap(draw, text, font, max_width)
    style = {"align": "center", "spacing": max(4, font.size // 6), "direction": "rtl" if is_rtl(text) else "ltr"}
    try:
        box = draw.multiline_textbbox((0, 0), wrapped, font=font, **style)
    except (KeyError, ValueError):  # Pillow without libraqm cannot set direction; Hebrew is still shaped
        style.pop("direction")
        box = draw.multiline_textbbox((0, 0), wrapped, font=font, **style)
    return wrapped, style, box


def _shadowed_text(page: Image.Image, text: str, font, max_width: int, y: int, align_bottom=False, blur=6,
                   boxes: Optional[List[tuple]] = None) -> int:
    """Centred white text with a soft dark shadow; returns its height. boxes, when given, collects the text's box."""
    wrapped, style, (left, top, right, bottom) = _block(ImageDraw.Draw(page), text, font, max_width)
    tw, th = right - left, bottom - top
    x = (page.width - tw) // 2 - left
    y0 = (y - th if align_bottom else y) - top
    if boxes is not None:
        boxes.append((x + left, y0 + top, x + right, y0 + bottom))
    shadow = Image.new("RGBA", page.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).multiline_text((x, y0 + blur // 2), wrapped, font=font, fill=(0, 0, 0, 190), **style)
    page.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(page).multiline_text((x, y0), wrapped, font=font, fill=(255, 255, 255, 255), **style)
    return th


def _faces(cover: Dict, fonts: CoverFonts, size: tuple, title_shrink: float = 1.0, safe: Optional[CoverSafe] = None) -> tuple:
    """(title face, starring face) at their drawn sizes for a cover of `size`; None for a line the cover lacks.
    title_shrink (below 1) scales the title's drawn size, after it was fitted to one line of the safe width."""
    w, h = size
    safe = safe or DEFAULT_COVER_SAFE
    title, title_font = cover.get("title", ""), None
    if title:
        path = resolve_font(cover.get("title_font"), fonts.title)
        title_font = one_line_font(path, title, int(w * cover_title_scale(title) * fonts.title_scale), int(w * safe.width))
        if title_shrink < 1:
            title_font = ImageFont.truetype(str(path), max(12, int(title_font.size * title_shrink)))
    starring_font = ImageFont.truetype(str(fonts.starring), max(18, int(h * 0.026))) if cover.get("starring") else None
    return title_font, starring_font


def top_block_end(size: tuple, cover: Dict, fonts: Optional[CoverFonts] = None, title_shrink: float = 1.0,
                  safe: Optional[CoverSafe] = None) -> float:
    """Where the top title block ends, as a share of the cover height: the title at SAFE_TOP and the starring line
    one gap below it, measured for this title, these faces and this cover size exactly as letter_cover draws them
    (SAFE_TOP itself for a cover with neither line), with the title at title_shrink of its size. render_cover keeps
    the title at the top when the head starts below it."""
    w, h = size
    safe = safe or DEFAULT_COVER_SAFE
    title_font, starring_font = _faces(cover, fonts or CoverFonts(), size, title_shrink, safe)
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    height = lambda text, font, width: (lambda box: box[3] - box[1])(_block(draw, text, font, width)[2])
    end = int(h * safe.top) + (height(cover["title"], title_font, w) if title_font else 0)
    if starring_font:
        end += h // 50 + height(cover["starring"], starring_font, int(w * safe.width))
    return end / h


def top_title_shrink(head: float, size: tuple, cover: Dict, fonts: Optional[CoverFonts] = None, gap: float = 0.0,
                     safe: Optional[CoverSafe] = None) -> Optional[float]:
    """The title size (a share of its own, 1.0 when it fits as it is) at which the top block ends `gap` of the height
    or more above the head (its top, a share of the height). The largest step down to MIN_TITLE_SHRINK that fits;
    None when even the smallest does not, and the block belongs at the bottom."""
    steps = int(round((1 - MIN_TITLE_SHRINK) / SHRINK_STEP)) if cover.get("title") else 0
    for shrink in (round(1 - i * SHRINK_STEP, 3) for i in range(steps + 1)):
        if head >= top_block_end(size, cover, fonts, shrink, safe) + gap:
            return shrink
    return None


def letter_cover(image: Image.Image, cover: Dict, fonts: Optional[CoverFonts] = None, title_at_bottom: bool = False,
                 badge: Optional[Union[CoverBadge, Dict]] = None, head_top: Optional[float] = None,
                 title_shrink: float = 1.0, safe: Optional[CoverSafe] = None, report: Optional[List] = None) -> Image.Image:
    """Letter the cover art.

    Args:
        image: Cover art
        cover: {"title", optional "starring", "footer", "title_font" (bundled file name or font path)}
        fonts: Faces to use; cover["title_font"] overrides the title face
        title_at_bottom: Stack the title and starring line just above the footer instead of at the top,
            for art whose head reaches up into the title block (the title must never cover the face;
            top_block_end says where that block ends)
        badge: Optional picture drawn after the lettering in a corner that is clear of it (cover_badge.CoverBadge
            or the same fields as a dict). It never moves or resizes a line; with no clear corner or an unreadable
            file there is no badge. None (the default) letters the cover exactly as without this argument
        head_top: The top of the hero's head as a share of the height, when measured. Only the badge uses it:
            a free top corner above the head is preferred to the bottom band, where the figure stands
        title_shrink: The title's size as a share of its own (top_title_shrink), so a tall title still ends above
            the head; 1.0 (the default) letters the cover exactly as without this argument
        safe: The cover's print-safe box (print_safe.CoverSafe); None is the default (SAFE_TOP, SAFE_BOTTOM, SAFE_WIDTH)
        report: When given, gets {"kind": title|subtitle|footer|logo, "page": "front", "box_px": [x, y, w, h]}
            for every line and the badge, in the cover's px

    Every line stays inside the safe box's top, bottom and width, so none is printed in a printer's margin.
    """
    fonts = fonts or CoverFonts()
    safe = safe or DEFAULT_COVER_SAFE
    page = image.convert("RGBA")
    page.alpha_composite(_cover_shade(page.size))
    w, h = page.size
    margin, text_width = int(h * safe.top), int(w * safe.width)
    gap, bottom = h // 50, h - math.ceil(h * safe.bottom)
    boxes: List[tuple] = []  # where each line was drawn, so a badge can keep clear of them
    kinds: List[str] = []
    if cover.get("footer"):
        kinds.append("footer")
        font = ImageFont.truetype(str(fonts.footer), max(14, int(h * 0.022)))
        fh = _shadowed_text(page, cover["footer"], font, text_width, bottom, align_bottom=True, blur=max(3, h // 400), boxes=boxes)
        bottom -= fh + gap
    title = cover.get("title", "")
    title_font, starring_font = _faces(cover, fonts, page.size, title_shrink, safe)
    if title_at_bottom:  # starring right above the footer, the title above it, both in the bottom shade
        kinds += ["subtitle"] * bool(starring_font) + ["title"] * bool(title_font)
        if starring_font:
            bottom -= _shadowed_text(page, cover["starring"], starring_font, text_width, bottom, align_bottom=True, blur=max(3, h // 400), boxes=boxes) + gap
        if title_font:
            _shadowed_text(page, title, title_font, w, bottom, align_bottom=True, blur=max(4, h // 250), boxes=boxes)
    else:
        kinds += ["title"] * bool(title_font) + ["subtitle"] * bool(starring_font)
        th = _shadowed_text(page, title, title_font, w, margin, blur=max(4, h // 250), boxes=boxes) if title_font else 0
        if starring_font:
            _shadowed_text(page, cover["starring"], starring_font, text_width, margin + th + gap, blur=max(3, h // 400), boxes=boxes)
    if badge:
        # Reading direction as the lines themselves take it: from the first lettered text (CoverBadge.rtl overrides).
        rtl = is_rtl(next((cover[key] for key in ("title", "starring", "footer") if cover.get(key)), ""))
        placed = place_badge(page, badge, boxes, rtl, safe.bottom, safe.width, art=image, head_top=head_top)
        if placed:
            boxes, kinds = boxes + [placed], kinds + ["logo"]
    if report is not None:
        report += [lettering_box(kind, "front", (l, t, r - l, b - t)) for kind, (l, t, r, b) in zip(kinds, boxes)]
    return page.convert("RGB")
