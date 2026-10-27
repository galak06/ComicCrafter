"""Cover art selection, seam detection and lettering, with fake clients."""

import pytest
from PIL import Image, ImageFont

from book_comic import cover as cover_module
from book_comic.cover import find_seam, panel_strip, render_cover
from book_comic.cover_lettering import FONTS_DIR, TITLE_FONT, letter_cover, one_line_font, resolve_font
from conftest import FakeImages, FakeVision

CAST = {"style": "comic", "characters": [{"name_en": "Dana", "look": "red coat"}],
        "props": [{"name": "the brass lantern", "look": "small brass hurricane lantern"}]}
COVER = {"scene": "Dana on the cliff", "title": "האור שחזר למגדלור", "starring": "בכיכוב דנה", "footer": ""}


def seamed(art):
    art = art.copy()
    art.paste((170, 172, 172), (0, 120, 400, 126))
    return art


def test_a_stacked_strip_seam_is_found_but_a_sky_is_not(noise):
    assert find_seam(seamed(noise())) == 126
    sky = noise()
    sky.paste((120, 160, 210), (0, 0, 400, 150))
    assert find_seam(sky) is None
    assert find_seam(noise()) is None


def test_the_cover_reference_shows_all_page_panels_in_order():
    assert panel_strip([]) is None
    strip = panel_strip([Image.new("RGB", (1800, 900), c) for c in ((200, 0, 0), (0, 200, 0), (0, 0, 200))])
    assert strip.height == 512
    assert [strip.getpixel((x, 256)) for x in (10, strip.width // 2, strip.width - 10)] == \
        [(200, 0, 0), (0, 200, 0), (0, 0, 200)]


@pytest.mark.parametrize("names, calls, colour", [
    (["clean"], 1, None),
    (["seamed", "clean"], 2, None),
    (["seamed", "seamed"], 2, None),  # both seamed: the seam is cut off
    (["high", "low"], 2, "red"),
    (["high", "high"], 2, "blue"),  # both too high: the second (equal) is fine, the head check never fails the job
    (["low"], 1, "red"),
    (["seamed", "high"], 2, "blue"),
    (["texted", "low"], 2, "red"),
    (["texted", "high"], 2, "blue"),
])
def test_cover_redraws_once_and_keeps_the_better_art(tmp_path, noise, monkeypatch, names, calls, colour):
    clean = noise()
    arts = {"clean": clean, "seamed": seamed(clean), "low": Image.new("RGB", (400, 600), "red"),
            "high": Image.new("RGB", (400, 600), "blue"), "texted": Image.new("RGB", (400, 600), "green")}
    heads = {(255, 0, 0): 0.4, (0, 0, 255): 0.1}

    def inspect(prompt, art):
        pixel = art.getpixel((0, 0))
        return {"head_top": heads.get(pixel, 0.5) * 1000, "has_text": pixel == (0, 128, 0)}

    lettered = []
    monkeypatch.setattr(cover_module, "letter_cover", lambda art, c, f: lettered.append(art) or art)
    images = FakeImages([arts[n] for n in names])
    render_cover(CAST, COVER, (400, 600), tmp_path / "cover.png", images, FakeVision(inspect),
                 panels=[Image.new("RGB", (300, 150))], references=["data:sheet"], reference_roles=["sheet"])
    assert len(images.calls) == calls
    art = lettered[0]
    assert art.size == (400, 600) and find_seam(art) is None
    if colour:
        assert art.getpixel((0, 0)) == Image.new("RGB", (1, 1), colour).getpixel((0, 0))
    prompt = images.calls[0]["prompt"]
    assert "small brass hurricane lantern" in prompt and "Absolutely no writing" in prompt
    assert "reference image 2 is the first page's panels" in prompt and len(images.calls[0]["references"]) == 2


def test_cover_lettering_shades_the_top_and_leaves_the_middle(tmp_path):
    art = Image.new("RGB", (400, 600), "white")
    lettered = letter_cover(art, {**COVER, "footer": "With love"})
    assert sum(lettered.getpixel((5, 5))) < 600
    assert lettered.getpixel((5, 300)) == (255, 255, 255)
    assert letter_cover(art, {"title": "Only a title"}).size == art.size  # starring and footer are optional


def test_cover_fonts_are_bundled_and_a_title_font_choice_falls_back():
    for name in ("Rubik-Black.ttf", "Assistant-SemiBold.ttf", "Assistant-Regular.ttf"):
        ImageFont.truetype(str(FONTS_DIR / name), 96)
        assert resolve_font(name, TITLE_FONT) == FONTS_DIR / name
    for bad in (None, "", "../../etc/passwd", "Missing.ttf", "Rubik-Black.otf", "/no/such/font.ttf"):
        assert resolve_font(bad, TITLE_FONT) == TITLE_FONT
    assert resolve_font(str(FONTS_DIR / "Assistant-Regular.ttf"), TITLE_FONT).name == "Assistant-Regular.ttf"


def test_cover_title_always_fits_one_line():
    title = "המצאת יום ההולדת הגדולה של סבא"
    assert one_line_font(TITLE_FONT, title, 400, 1800).getlength(title) <= 1800
    assert one_line_font(TITLE_FONT, "קצר", 150, 1800).size == 150
