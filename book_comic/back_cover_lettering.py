"""Back cover lettering: a dark translucent panel in the calm upper half with the tagline and the blurb.

The art is drawn with nobody in it and a calm upper half (image_prompts.back_cover_prompt); the panel keeps
white type readable on any art. Hebrew is set right to left. Type shrinks until the whole text fits the panel.

Optional stamps (cover_stamps.CornerStamp: a logo tile, a barcode panel) stand in the bottom corners, under the text.
The footer line is centred at the bottom, so with stamps it is wrapped to the width left between them.
"""

import math
from typing import Dict, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from book_comic.cover_badge import TOP_SAFE
from book_comic.cover_lettering import SAFE_BOTTOM, SAFE_WIDTH, CoverFonts, _shadowed_text, resolve_font
from book_comic.cover_stamps import draw_stamps, fit_stamps, room_between
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


def _footer_and_stamps(page: Image.Image, back: Dict, fonts: CoverFonts, stamps, text_end: Optional[int]) -> None:
    """The footer line at the bottom margin and the stamps in the bottom corners, one lettering gap under the text
    (which ends at text_end; None for a back cover without text). A footer beside stamps is wrapped between them."""
    w, h = page.size
    gap = h // 50
    placed = fit_stamps(stamps, page.size, text_end + gap if text_end is not None else math.ceil(h * TOP_SAFE), SAFE_BOTTOM, SAFE_WIDTH) if stamps else []
    if back.get("footer"):
        font = ImageFont.truetype(str(fonts.footer), max(14, int(h * 0.022)))
        between = room_between(placed, w, gap)
        width = int(w * SAFE_WIDTH) if between is None else min(int(w * SAFE_WIDTH), between)
        # Inside the printers' text margin, as the front cover's lettering (cover_lettering.SAFE_BOTTOM).
        _shadowed_text(page, back["footer"], font, width, h - math.ceil(h * SAFE_BOTTOM), align_bottom=True, blur=max(3, h // 400))
    draw_stamps(page, placed)


def letter_back_cover(image: Image.Image, back: Dict, fonts: Optional[CoverFonts] = None, stamps: Sequence = ()) -> Image.Image:
    """Letter the back cover art.

    Args:
        image: Back cover art (the setting, nobody in it)
        back: {"tagline", "blurb", optional "footer", "title_font" (bundled file name or font path)}
        fonts: Faces to use: the title face for the tagline, the starring face for the blurb, the footer face
        stamps: Optional opaque pictures for the bottom corners (cover_stamps.CornerStamp or the same fields as
            dicts): each stands on SAFE_BOTTOM in its corner of the print-safe box, one lettering gap (2% of the
            height) or more under the text, drawn smaller (down to 75%) or left out when the text leaves too
            little room. The footer is then wrapped to the width between them. Empty letters exactly as before
    """
    fonts = fonts or CoverFonts()
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
        if stamps:
            _footer_and_stamps(page, {}, fonts, stamps, None)
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
    # A blurb too long for the panel at its smallest face runs past it: the text ends where the blurb does.
    _footer_and_stamps(page, back, fonts, stamps, max(y0 + panel_h, y + blurb_h))
    return page.convert("RGB")
