"""Cover lettering: shaded art, a one-line shadowed title, a starring line and a footer. No boxes."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Union

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from layout.lettering import FONTS_DIR, _wrap, is_rtl

TITLE_FONT = FONTS_DIR / "Rubik-Black.ttf"
STARRING_FONT = FONTS_DIR / "Assistant-SemiBold.ttf"
FOOTER_FONT = FONTS_DIR / "Assistant-Regular.ttf"


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


def _shadowed_text(page: Image.Image, text: str, font, max_width: int, y: int, align_bottom=False, blur=6) -> int:
    """Centred white text with a soft dark shadow; returns its height."""
    draw = ImageDraw.Draw(page)
    wrapped = _wrap(draw, text, font, max_width)
    style = {"align": "center", "spacing": max(4, font.size // 6), "direction": "rtl" if is_rtl(text) else "ltr"}
    try:
        left, top, right, bottom = draw.multiline_textbbox((0, 0), wrapped, font=font, **style)
    except (KeyError, ValueError):  # Pillow without libraqm cannot set direction; Hebrew is still shaped
        style.pop("direction")
        left, top, right, bottom = draw.multiline_textbbox((0, 0), wrapped, font=font, **style)
    tw, th = right - left, bottom - top
    x = (page.width - tw) // 2 - left
    y0 = (y - th if align_bottom else y) - top
    shadow = Image.new("RGBA", page.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).multiline_text((x, y0 + blur // 2), wrapped, font=font, fill=(0, 0, 0, 190), **style)
    page.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(page).multiline_text((x, y0), wrapped, font=font, fill=(255, 255, 255, 255), **style)
    return th


def letter_cover(image: Image.Image, cover: Dict, fonts: Optional[CoverFonts] = None, title_at_bottom: bool = False) -> Image.Image:
    """Letter the cover art.

    Args:
        image: Cover art
        cover: {"title", optional "starring", "footer", "title_font" (bundled file name or font path)}
        fonts: Faces to use; cover["title_font"] overrides the title face
        title_at_bottom: Stack the title and starring line just above the footer instead of at the top,
            for art whose head reaches up into the title block (the title must never cover the face)
    """
    fonts = fonts or CoverFonts()
    page = image.convert("RGBA")
    page.alpha_composite(_cover_shade(page.size))
    w, h = page.size
    margin = max(12, h // 18)
    gap, bottom = h // 50, h - margin // 2
    if cover.get("footer"):
        font = ImageFont.truetype(str(fonts.footer), max(14, int(h * 0.022)))
        fh = _shadowed_text(page, cover["footer"], font, int(w * 0.8), bottom, align_bottom=True, blur=max(3, h // 400))
        bottom -= fh + gap
    title = cover.get("title", "")
    title_font = None
    if title:
        path = resolve_font(cover.get("title_font"), fonts.title)
        size = int(w * cover_title_scale(title) * fonts.title_scale)
        title_font = one_line_font(path, title, size, int(w * 0.88))
    starring_font = ImageFont.truetype(str(fonts.starring), max(18, int(h * 0.026))) if cover.get("starring") else None
    if title_at_bottom:  # starring right above the footer, the title above it, both in the bottom shade
        if starring_font:
            bottom -= _shadowed_text(page, cover["starring"], starring_font, int(w * 0.8), bottom, align_bottom=True, blur=max(3, h // 400)) + gap
        if title_font:
            _shadowed_text(page, title, title_font, w, bottom, align_bottom=True, blur=max(4, h // 250))
        return page.convert("RGB")
    th = _shadowed_text(page, title, title_font, w, margin, blur=max(4, h // 250)) if title_font else 0
    if starring_font:
        _shadowed_text(page, cover["starring"], starring_font, int(w * 0.8), margin + th + gap, blur=max(3, h // 400))
    return page.convert("RGB")
