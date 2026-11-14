"""A pale, flat wall behind a close-up is scenery; a paper margin ends at the picture's straight edge."""

import pytest
from PIL import Image, ImageDraw

from book_comic.art_check import draw_checked
from book_comic.margins import MARGIN_CORRECTION, find_margins, trim_margins
from conftest import FakeImages, FakeVision

WALL = (232, 227, 216)
WHITE = (255, 255, 255)
CLEAN = {"has_text": False, "bad_anatomy": False, "identity_mismatch": False, "design_mismatch": False,
         "scene_mismatch": False, "head_top": 300}


def close_up(width=600, height=400, wall=WALL):
    """Head and shoulders in the middle of the frame, a flat pale wall to both sides up to the edges."""
    art = Image.new("RGB", (width, height), wall)
    draw = ImageDraw.Draw(art)
    cx = width // 2
    draw.polygon([(cx - 150, height), (cx - 90, height - 110), (cx + 90, height - 110), (cx + 150, height)], fill=(40, 90, 110))
    draw.ellipse((cx - 80, 60, cx + 80, height - 90), fill=(196, 150, 120))
    draw.ellipse((cx - 85, 45, cx + 85, 170), fill=(60, 40, 30))  # hair
    return art


def hand_detail(width=600, height=400):
    """A hand on the wall, the wall flat on all four sides."""
    art = Image.new("RGB", (width, height), WALL)
    ImageDraw.Draw(art).ellipse((220, 130, 380, 270), fill=(196, 150, 120))
    return art


def lit_wall(width=600, height=400):
    """The same close-up on a wall that gets slowly lighter toward the middle (soft light, no edge anywhere)."""
    art = Image.new("RGB", (width, height))
    for x in range(width):
        tone = 205 + round(40 * (1 - abs(x - width / 2) / (width / 2)))
        art.paste((tone, tone, tone - 8), (x, 0, x + 1, height))
    art.paste(close_up(200, height).crop((20, 0, 180, height)), (220, 0))
    return art


def on_paper(picture, left, top, right, bottom, paper=WHITE):
    canvas = Image.new("RGB", (picture.width + left + right, picture.height + top + bottom), paper)
    canvas.paste(picture, (left, top))
    return canvas


@pytest.mark.parametrize("art", [close_up(), close_up(900, 400), close_up(wall=(244, 244, 244)), hand_detail(), lit_wall()],
                         ids=["close-up", "wide close-up", "white wall", "hand on the wall", "softly lit wall"])
def test_a_close_up_on_a_pale_wall_has_no_margins(art):
    assert find_margins(art) is None
    assert trim_margins(art, 900 / 400) == (art, None)


def test_the_pale_wall_close_up_is_checked_as_drawn_and_not_redrawn():
    # The report: the margins check rejected such a close-up (scene_mismatch + MARGIN_CORRECTION, a wasted draw).
    images = FakeImages([close_up(900, 400)])
    seen = []
    art = draw_checked(images, FakeVision(lambda p, i: seen.append(i.copy()) or CLEAN), "Close-up: Hero by the wall.", [], "9:4",
                       size=(900, 400), audit=(audit := []))
    assert len(images.calls) == 1 and "margins_redraw" not in audit[0]["checks"]
    assert art.getpixel((5, 5)) == WALL and art.getpixel((450, 100)) != WALL  # the wall is still there, uncropped


@pytest.mark.parametrize("left,top,right,bottom", [(90, 0, 90, 0), (0, 50, 0, 50), (90, 50, 90, 50)])
def test_real_white_bands_around_the_same_close_up_are_still_margins(left, top, right, bottom):
    art = on_paper(close_up(), left, top, right, bottom)
    box = find_margins(art)
    assert box is not None
    assert abs(box[0] - left) <= 8 and abs(box[1] - top) <= 8
    assert abs(box[2] - (art.width - right)) <= 8 and abs(box[3] - (art.height - bottom)) <= 8


def test_a_white_banded_close_up_too_narrow_for_the_panel_is_still_redrawn():
    images = FakeImages([on_paper(close_up(300, 300), 300, 0, 300, 0), close_up(900, 300)])
    draw_checked(images, FakeVision(lambda p, i: CLEAN), "Close-up: Hero by the wall.", [], "3:1", size=(900, 300))
    assert len(images.calls) == 2 and MARGIN_CORRECTION in images.calls[1]["prompt"]


def test_a_white_banded_close_up_that_fits_is_trimmed_to_the_picture():
    picture, status = trim_margins(on_paper(close_up(600, 400), 30, 0, 30, 0), 600 / 400)
    assert status == "trimmed" and abs(picture.width - 600) <= 8
