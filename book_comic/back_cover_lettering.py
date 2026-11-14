"""Back cover lettering: a dark translucent panel in the calm upper half with the tagline and the blurb.

The art is drawn with nobody in it and a calm upper half (image_prompts.back_cover_prompt); the panel keeps
white type readable on any art. Hebrew is set right to left. Type shrinks until the whole text fits the panel.

An optional badge (a brand mark, cover_badge.CoverBadge) is centred below the panel, right above the footer line or
ending at the lettering's bottom margin: one fixed spot, the same in Hebrew and English, never over any text.
"""

import math
from typing import Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont

from book_comic.cover_badge import TOP_SAFE, CoverBadge, as_badge, place_centred_badge
from book_comic.cover_lettering import SAFE_BOTTOM, SAFE_WIDTH, CoverFonts, _shadowed_text, resolve_font
from layout.lettering import _wrap, is_rtl

PANEL_TOP = 0.2      # the panel starts a fifth of the way down
PANEL_WIDTH = 0.8    # share of the cover width
MAX_HEIGHT = 0.55    # the panel never reaches past three quarters of the height
PANEL_FILL = (12, 14, 22, 175)
TAGLINE_SIZE = 0.052  # share of the width
BLURB_SIZE = 0.03     # share of the width; never below MIN_BLURB_SIZE
MIN_BLURB_SIZE = 0.018


def _measure(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, align: str) -> Tuple[str, int, int]:
    wrapped = _wrap(draw, text, font, max_width)
    style = {"align": align, "spacing": max(4, font.size // 4)}
    if is_rtl(text):
        style["direction"] = "rtl"
    try:
        left, top, right, bottom = draw.multiline_textbbox((0, 0), wrapped, font=font, **style)
    except (KeyError, ValueError):  # Pillow without libraqm cannot set direction; Hebrew is still shaped
        style.pop("direction", None)
        left, top, right, bottom = draw.multiline_textbbox((0, 0), wrapped, font=font, **style)
    return wrapped, right - left, bottom - top


def _fit_blurb(draw, blurb: str, path, width: int, room: int, cover_width: int):
    """The largest blurb face (down to MIN_BLURB_SIZE of the width) whose wrapped text fits in room pixels."""
    size = int(cover_width * BLURB_SIZE)
    floor = max(12, int(cover_width * MIN_BLURB_SIZE))
    while True:
        font = ImageFont.truetype(str(path), size)
        wrapped, _, height = _measure(draw, blurb, font, width, "center")
        if height <= room or size <= floor:
            return font, wrapped, height
        size = max(floor, int(size * 0.92))


def _place_badge(page: Image.Image, badge: CoverBadge, text: Optional[Tuple[int, int]], footer_top: Optional[int]) -> None:
    """The badge, centred and clear of the text (the rows `text` of the panel and blurb, and the footer): for
    "bottom" it ends one lettering gap above the footer, or at the bottom margin; for "top" it sits in the middle of
    the rows between the top margin and the panel. A back cover without a panel has it at the bottom either way."""
    h = page.height
    gap, blur = h // 50, max(3, h // 400)
    safe_top = math.ceil(h * TOP_SAFE)
    if text and badge.position == "top":
        place_centred_badge(page, badge, safe_top, text[0] - gap, at_end=False, shadow=blur)
        return
    end = footer_top - gap if footer_top is not None else h - math.ceil(h * SAFE_BOTTOM)
    place_centred_badge(page, badge, text[1] + gap if text else safe_top, end, shadow=blur)


def letter_back_cover(image: Image.Image, back: Dict, fonts: Optional[CoverFonts] = None,
                      badge: Optional[Union[CoverBadge, Dict]] = None) -> Image.Image:
    """Letter the back cover art.

    Args:
        image: Back cover art (the setting, nobody in it)
        back: {"tagline", "blurb", optional "footer", "title_font" (bundled file name or font path)}
        fonts: Faces to use: the title face for the tagline, the starring face for the blurb, the footer face
        badge: Optional picture (a brand mark) drawn after the lettering: cover_badge.CoverBadge or the same fields
            as a dict. Centred, inside the lettering's print-safe box, one lettering gap (2% of the height) away
            from the text: position "bottom" (default) puts it below the panel, right above the footer line or
            ending at SAFE_BOTTOM; "top" puts it between the top margin and the panel. Too little room draws it
            smaller (down to 75%), then not at all; it never moves or resizes text. None letters exactly as before
    """
    fonts = fonts or CoverFonts()
    badge = as_badge(badge)
    page = image.convert("RGBA")
    w, h = page.size
    draw = ImageDraw.Draw(page)
    panel_w = int(w * PANEL_WIDTH)
    pad = max(12, w // 28)
    inner = panel_w - 2 * pad
    tagline, blurb = (back.get("tagline") or "").strip(), (back.get("blurb") or "").strip()
    tag_font = None
    tag_h = 0
    if tagline:
        tag_font = ImageFont.truetype(str(resolve_font(back.get("title_font"), fonts.title)),
                                      max(16, int(w * TAGLINE_SIZE * fonts.title_scale)))
        _, _, tag_h = _measure(draw, tagline, tag_font, inner, "center")
    gap = pad // 2 if tagline and blurb else 0
    room = int(h * MAX_HEIGHT) - 2 * pad - tag_h - gap
    blurb_font, blurb_text, blurb_h = (None, "", 0)
    if blurb:
        blurb_font, blurb_text, blurb_h = _fit_blurb(draw, blurb, fonts.starring, inner, room, w)
    if not tagline and not blurb:
        if badge:
            _place_badge(page, badge, None, None)
        return page.convert("RGB")
    panel_h = min(int(h * MAX_HEIGHT), 2 * pad + tag_h + gap + blurb_h)
    x0, y0 = (w - panel_w) // 2, int(h * PANEL_TOP)
    shade = Image.new("RGBA", page.size, (0, 0, 0, 0))
    ImageDraw.Draw(shade).rounded_rectangle([x0, y0, x0 + panel_w, y0 + panel_h], radius=max(6, w // 60), fill=PANEL_FILL)
    page.alpha_composite(shade)
    y = y0 + pad
    if tag_font:
        y += _shadowed_text(page, tagline, tag_font, inner, y, blur=max(3, h // 400)) + gap
    if blurb_font:
        style = {"align": "center", "spacing": max(4, blurb_font.size // 4)}
        if is_rtl(blurb):
            style["direction"] = "rtl"
        draw = ImageDraw.Draw(page)
        try:
            left, top, right, _ = draw.multiline_textbbox((0, 0), blurb_text, font=blurb_font, **style)
        except (KeyError, ValueError):
            style.pop("direction", None)
            left, top, right, _ = draw.multiline_textbbox((0, 0), blurb_text, font=blurb_font, **style)
        draw.multiline_text(((w - (right - left)) // 2 - left, y - top), blurb_text, font=blurb_font,
                            fill=(240, 240, 240, 255), **style)
    footer: List[tuple] = []
    if back.get("footer"):
        font = ImageFont.truetype(str(fonts.footer), max(14, int(h * 0.022)))
        # Inside the printers' text margin, as the front cover's lettering (cover_lettering.SAFE_BOTTOM).
        _shadowed_text(page, back["footer"], font, int(w * SAFE_WIDTH), h - math.ceil(h * SAFE_BOTTOM), align_bottom=True,
                       blur=max(3, h // 400), boxes=footer)
    if badge:
        # A blurb too long for the panel at its smallest face runs past it: the text ends where the blurb does.
        _place_badge(page, badge, (y0, max(y0 + panel_h, y + blurb_h)), footer[0][1] if footer else None)
    return page.convert("RGB")
