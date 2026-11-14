"""The optional front-cover badge: print-safe corners, clear of the lettering and of the figure, never a reason to lose a cover."""

import numpy as np
import pytest
from PIL import Image

from book_comic import cover as cover_module
from book_comic.cover import HEAD_SAFE_MIN, render_cover
from book_comic.cover_badge import CALMER, MAX_HEIGHT, TOP_SAFE, WIDTH_RANGE, CoverBadge, badge_boxes, busyness, place_badge
from book_comic.cover_lettering import SAFE_BOTTOM, SAFE_TOP, SAFE_WIDTH, letter_cover
from conftest import FakeImages, FakeVision
from test_cover_print_safe import CAST, CLEAN, HEBREW, LONG, MARGIN_MM, PRINTERS, SHORT, H, W, inside_trim_mm, lettered_lines

MAGENTA = (255, 0, 255)
SMALL = (W // 3, H // 3)  # a third of the print size: the same shares, a ninth of the pixels
MID = {"title": "Dana and the Lighthouse", "starring": "Starring Dana", "footer": "For Dana, with love"}
ONLY_TITLE = {"title": "Dana"}
TINY = (W // 5, H // 5)


@pytest.fixture
def mark(tmp_path):
    """A square magenta badge file with a transparent border, and a factory for other shapes."""
    def make(size=(300, 300), colour=MAGENTA, name="mark.png"):
        picture = Image.new("RGBA", size, (0, 0, 0, 0))
        picture.paste(Image.new("RGBA", (size[0] - 20, size[1] - 20), (*colour, 255)), (10, 10))
        picture.save(tmp_path / name)
        return tmp_path / name
    make()
    return make


def art(size=SMALL):
    return Image.new("RGB", size, (90, 120, 160))


def badge_box(image, colour=MAGENTA):
    """(left, top, right, bottom) of the badge's solid colour on the lettered cover, or None when it was not drawn."""
    ys, xs = np.where(np.all(np.asarray(image) == colour, axis=2))
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(ys) else None


def white_boxes(image):
    """Lettering boxes as (left, top, right, bottom), from the print-safe test's row scan."""
    return [(left, top, right, bottom) for top, bottom, left, right in lettered_lines(image)]


def corner(box, size=SMALL):
    return ("top" if box[1] < size[1] / 2 else "bottom", "left" if box[0] < size[0] / 2 else "right")


def test_the_top_offset_is_the_lower_of_the_title_start_and_the_head_limit():
    assert TOP_SAFE == max(SAFE_TOP, HEAD_SAFE_MIN)


@pytest.mark.parametrize("cover, at_bottom", [(LONG, False), (HEBREW, True), ({}, False)])
def test_no_badge_and_an_unusable_badge_letter_the_cover_exactly_as_before(tmp_path, cover, at_bottom):
    (tmp_path / "notes.png").write_text("not a picture")
    plain = letter_cover(art(TINY), cover, title_at_bottom=at_bottom)
    assert letter_cover(art(TINY), cover, None, at_bottom, None).tobytes() == plain.tobytes()
    for unusable in (CoverBadge(tmp_path / "missing.png"), CoverBadge(tmp_path / "notes.png"), CoverBadge(tmp_path),
                     {"path": str(tmp_path / "missing.png")}, {"width": 0.2}, "mark.png", CoverBadge(""), CoverBadge(None)):
        assert letter_cover(art(TINY), cover, title_at_bottom=at_bottom, badge=unusable).tobytes() == plain.tobytes()


def test_a_badge_changes_only_its_own_box(mark):
    plain = np.asarray(letter_cover(art(), MID))
    badged = letter_cover(art(), MID, badge=CoverBadge(mark((300, 300))))
    left, top, right, bottom = badge_box(badged)
    changed = np.any(np.asarray(badged) != plain, axis=2)
    changed[top - 4:bottom + 4, left - 4:right + 4] = False  # the badge and its transparent border
    assert not changed.any()  # every line is where it was, at the size it was


@pytest.mark.parametrize("cover, rtl", [(MID, False), (HEBREW, True)])
def test_the_badge_sits_in_the_bottom_corner_where_reading_ends(mark, cover, rtl):
    lettered = letter_cover(art(), {**cover, "title": cover["title"][:12]}, badge=CoverBadge(mark()))
    assert corner(badge_box(lettered)) == ("bottom", "left" if rtl else "right")
    forced = letter_cover(art(), {**cover, "title": cover["title"][:12]}, badge=CoverBadge(mark(), rtl=not rtl))
    assert corner(badge_box(forced)) == ("bottom", "right" if rtl else "left")  # CoverBadge.rtl overrides the text
    as_dict = letter_cover(art(), {**cover, "title": cover["title"][:12]}, badge={"path": str(mark()), "width": 0.1})
    assert corner(badge_box(as_dict)) == ("bottom", "left" if rtl else "right")


def test_position_top_prefers_the_top_reading_end_corner(mark):
    assert corner(badge_box(letter_cover(art(), ONLY_TITLE, badge=CoverBadge(mark(), position="top")))) == ("top", "right")
    assert corner(badge_box(letter_cover(art(), ONLY_TITLE, badge=CoverBadge(mark(), position="nonsense")))) == ("bottom", "right")


def test_the_corners_are_tried_in_a_fixed_order():
    boxes = badge_boxes((100, 80), (1000, 2000), "bottom", False, SAFE_BOTTOM, SAFE_WIDTH)
    assert [corner(b, (1000, 2000)) for b in boxes] == [("bottom", "right"), ("bottom", "left"), ("top", "right"), ("top", "left")]
    assert boxes[0] == (790, 1700, 890, 1780) and boxes[3] == (110, 170, 210, 250)  # 11% in, ending 11% up, starting 8.5% down
    rtl = badge_boxes((100, 80), (1000, 2000), "top", True, SAFE_BOTTOM, SAFE_WIDTH)
    assert [corner(b, (1000, 2000)) for b in rtl] == [("top", "left"), ("top", "right"), ("bottom", "left"), ("bottom", "right")]


def test_a_taken_corner_passes_the_badge_to_the_next_free_one(mark):
    page = art((1000, 2000)).convert("RGBA")
    first, second, third, fourth = badge_boxes((140, 140), (1000, 2000), "bottom", False, SAFE_BOTTOM, SAFE_WIDTH)
    badge = CoverBadge(mark())
    assert place_badge(page.copy(), badge, [], False, SAFE_BOTTOM, SAFE_WIDTH) == first
    assert place_badge(page.copy(), badge, [first], False, SAFE_BOTTOM, SAFE_WIDTH) == second
    assert place_badge(page.copy(), badge, [first, second], False, SAFE_BOTTOM, SAFE_WIDTH) == third
    assert place_badge(page.copy(), badge, [first, second, third], False, SAFE_BOTTOM, SAFE_WIDTH) == fourth
    untouched = page.copy()
    assert place_badge(untouched, badge, [first, second, third, fourth], False, SAFE_BOTTOM, SAFE_WIDTH) is None
    assert untouched.tobytes() == page.tobytes()  # no free corner: no badge, and nothing raised
    near = (first[0] - 30, first[1], first[0] - 10, first[3])  # lettering 10 px beside the corner: closer than the 40 px gap
    assert place_badge(page.copy(), badge, [near], False, SAFE_BOTTOM, SAFE_WIDTH) == second


@pytest.mark.parametrize("cover", [SHORT, MID, LONG, HEBREW])
@pytest.mark.parametrize("at_bottom", [False, True])
@pytest.mark.parametrize("shape", [(300, 300), (600, 200)])
@pytest.mark.parametrize("position", ["bottom", "top"])
def test_the_badge_never_touches_the_title_starring_line_or_footer(mark, cover, at_bottom, shape, position):
    plain = letter_cover(art(), cover, title_at_bottom=at_bottom)
    badged = letter_cover(art(), cover, title_at_bottom=at_bottom, badge=CoverBadge(mark(shape), position=position))
    box = badge_box(badged)
    if box is None:
        assert badged.tobytes() == plain.tobytes()  # no free corner: the plain cover
        return
    gap = SMALL[1] // 50 - 12  # the 2% gap, less the file's transparent border and the lines' antialiased edge
    for left, top, right, bottom in white_boxes(plain):
        assert box[2] + gap <= left or right + gap <= box[0] or box[3] + gap <= top or bottom + gap <= box[1]
    assert white_boxes(badged) == white_boxes(plain)


def test_long_lettering_at_the_bottom_sends_the_badge_up_and_a_full_cover_gets_none(mark):
    """A wrapped footer fills the bottom band; a title of ordinary length at the top reaches both top corners."""
    badge = CoverBadge(mark())
    assert badge_box(letter_cover(art(), LONG, badge=badge)) is None
    assert corner(badge_box(letter_cover(art(), LONG, title_at_bottom=True, badge=badge))) == ("top", "right")
    assert corner(badge_box(letter_cover(art(), {**ONLY_TITLE, "footer": LONG["footer"]}, badge=badge))) == ("top", "right")
    assert badge_box(letter_cover(art(), {**MID, "footer": LONG["footer"]}, badge=badge)) is None  # the title reaches both top corners
    assert corner(badge_box(letter_cover(art(), MID, badge=badge))) == ("bottom", "right")


@pytest.mark.parametrize("width, expected", [(0.14, 0.14), (0.01, WIDTH_RANGE[0]), (0.9, WIDTH_RANGE[1]), (float("nan"), 0.14), ("wide", None)])
def test_the_width_is_a_share_of_the_cover_kept_in_range(mark, width, expected):
    box = badge_box(letter_cover(art(), ONLY_TITLE, badge=CoverBadge(mark((1000, 400)), width=width)))
    if expected is None:
        assert box is None  # an unusable width draws no badge
    else:
        assert abs((box[2] - box[0]) / SMALL[0] - expected) < 0.012  # less the file's transparent border


def test_a_tall_badge_is_scaled_down_to_the_height_limit(mark):
    left, top, right, bottom = badge_box(letter_cover(art(), ONLY_TITLE, badge=CoverBadge(mark((200, 1000)), width=0.2)))
    assert abs((bottom - top) / SMALL[1] - MAX_HEIGHT) < 0.006 and (right - left) < (bottom - top) / 4


@pytest.mark.parametrize("printer", PRINTERS)
@pytest.mark.parametrize("cover, at_bottom, position", [(MID, False, "bottom"), (HEBREW, False, "bottom"), (ONLY_TITLE, False, "top"),
                                                        (LONG, True, "bottom"), (HEBREW, True, "top")])
def test_the_badge_prints_inside_both_printers_margins(mark, printer, cover, at_bottom, position):
    """Full print size, measured as the print-safe test measures lettering (top, bottom, left, right)."""
    lettered = letter_cover(art((W, H)), cover, title_at_bottom=at_bottom, badge=CoverBadge(mark((400, 400)), width=0.2, position=position))
    left, top, right, bottom = badge_box(lettered)
    mm = inside_trim_mm((top - 14, bottom + 14, left - 14, right + 14), PRINTERS[printer])  # with the file's transparent border
    assert mm["bottom"] >= MARGIN_MM and mm["side"] >= MARGIN_MM
    assert mm["top"] >= 12.7  # a top badge starts at the head limit: inside the 12.7 mm margin on both printers


def test_a_white_badge_keeps_every_white_mark_inside_the_margins(mark):
    plain = lettered_lines(letter_cover(art((W, H)), MID))
    badged = lettered_lines(letter_cover(art((W, H)), MID, badge=CoverBadge(mark((400, 400), colour=(255, 255, 255)))))
    assert badged[:2] == plain[:2] and len(plain) == 3  # the title and starring line are measured as before
    for line in badged:
        for printer in PRINTERS.values():
            mm = inside_trim_mm(line, printer)
            assert mm["bottom"] >= MARGIN_MM and mm["side"] >= MARGIN_MM


BOOT, LEDGE = (120, 60, 20), (90, 120, 160)  # a large shape of the figure, and the flat setting behind it
CORNERS = {name: i for i, name in enumerate(["bottom-end", "bottom-start", "top-end", "top-start"])}  # the order tried, LTR


def scene(*shapes, size=SMALL, colour=BOOT):
    """Flat art with a large shape (a boot, a limb) covering half of each named corner box of a 14% badge."""
    picture, side = art(size), round(size[0] * 0.14)
    boxes = badge_boxes((side, side), size, "bottom", False, SAFE_BOTTOM, SAFE_WIDTH)
    for name in shapes:
        left, top, right, bottom = boxes[CORNERS[name]]
        picture.paste(colour, (left + side // 2, top - side // 4, right + side // 4, bottom + side // 4))
    return picture


def placed(picture, cover=ONLY_TITLE, **kwargs):
    return corner(badge_box(letter_cover(picture, cover, badge=CoverBadge(kwargs.pop("mark")), **kwargs)), picture.size)


def test_a_corner_on_a_large_shape_passes_the_badge_to_a_calm_one(mark):
    """Real cover 2026-11-13 (Hebrew): the badge sat on the hero's boot; the placement knew only the lettering."""
    assert placed(scene(), mark=mark()) == ("bottom", "right")  # flat art: the order as before
    assert placed(scene("bottom-end"), mark=mark()) == ("bottom", "left")
    assert placed(scene("bottom-end", "bottom-start"), mark=mark()) == ("top", "right")
    assert placed(scene("bottom-end", "bottom-start", "top-end"), mark=mark()) == ("top", "left")
    assert placed(scene("bottom-start", "top-end", "top-start"), mark=mark()) == ("bottom", "right")  # the first corner is the calm one
    # Every corner on a shape: still a badge, in the least busy corner, here a tie that the order decides.
    assert placed(scene(*CORNERS), mark=mark()) == ("bottom", "right")


def test_fine_texture_does_not_move_the_badge_and_a_slightly_calmer_corner_does_not_win(mark):
    """Windows, hatching and rock cracks are fine under a badge: only shapes about its own size count."""
    textured, side = art(), round(SMALL[0] * 0.14)
    first, second, *top = badge_boxes((side, side), SMALL, "bottom", False, SAFE_BOTTOM, SAFE_WIDTH)
    for x in range(first[0] - side, first[2] + side, 6):  # a grid of thin dark lines, as a far building's windows
        textured.paste((20, 30, 60), (x, first[1] - side, x + 2, first[3] + side))
    assert busyness(textured, first) < 3 and placed(textured, mark=mark()) == ("bottom", "right")
    assert busyness(scene("bottom-end"), first) > 20 > 1 > busyness(scene("bottom-end"), second)
    soft = scene("bottom-end", colour=(110, 135, 170))  # a shape barely different from the setting on the first corner,
    soft.paste((108, 134, 170), (second[0], second[1], second[0] + side // 2, second[3]))  # a smaller one on the second
    assert 0 < CALMER * busyness(soft, first) < busyness(soft, second) < busyness(soft, first)
    place = lambda picture: place_badge(picture.convert("RGBA"), CoverBadge(mark()), top, False, SAFE_BOTTOM, SAFE_WIDTH, art=picture)
    assert place(soft) == first  # not calmer by enough to leave the preferred corner
    assert place(scene("bottom-end")) == second and placed(soft, mark=mark()) == ("top", "right")  # flat sky is


def test_a_head_measured_below_the_top_corners_sends_the_badge_above_the_figure(mark):
    """The bottom band holds a full-body hero's legs and feet whatever the pixels say (a dark boot on dark rock)."""
    assert placed(scene(), mark=mark(), head_top=0.3) == ("top", "right")
    wide = mark((543, 376))  # the real badge's shape: its top corners end 14.9% down, above the real head at 17.6%
    assert placed(scene(), HEBREW | {"title": "מרדף בהרים"}, mark=wide, head_top=0.176) == ("top", "left")  # reading end
    assert placed(scene(), HEBREW | {"title": "מרדף בהרים"}, mark=wide, head_top=0.14) == ("top", "left")  # a little smaller, still above it
    assert placed(scene(), HEBREW | {"title": "מרדף בהרים"}, mark=wide, head_top=0.125) == ("bottom", "left")  # the head reaches them
    assert placed(scene("top-end"), mark=mark(), head_top=0.3) == ("top", "left")  # a raised prop in one top corner
    assert placed(scene("top-end", "top-start"), mark=mark(), head_top=0.3) == ("top", "right")  # still above the figure
    # A head that reaches the top corners' rows says nothing about them: the calmest corner, in the usual order.
    assert placed(scene(), mark=mark(), head_top=0.12) == ("bottom", "right")
    assert placed(scene("bottom-end"), mark=mark(), head_top=0.12) == ("bottom", "left")
    # A title that reaches both top corners leaves the bottom band, where the calm corner wins.
    assert placed(scene(), MID, mark=mark(), head_top=0.3) == ("bottom", "right")
    assert placed(scene("bottom-end"), MID, mark=mark(), head_top=0.3) == ("bottom", "left")


def test_the_corner_is_judged_on_the_unlettered_art_and_the_lettering_still_comes_first(mark):
    busy = scene("bottom-end")
    page = busy.convert("RGBA")
    first, second, third, fourth = badge_boxes((96, 96), SMALL, "bottom", False, SAFE_BOTTOM, SAFE_WIDTH)
    badge = CoverBadge(mark())
    assert place_badge(page.copy(), badge, [], False, SAFE_BOTTOM, SAFE_WIDTH) == first  # no art given: the first free corner
    assert place_badge(page.copy(), badge, [], False, SAFE_BOTTOM, SAFE_WIDTH, art=busy) == second
    assert place_badge(page.copy(), badge, [second, third, fourth], False, SAFE_BOTTOM, SAFE_WIDTH, art=busy) == first  # busy but the only free one
    assert place_badge(page.copy(), badge, [third], False, SAFE_BOTTOM, SAFE_WIDTH, art=art(), head_top=0.3) == fourth
    assert place_badge(page.copy(), badge, [first, second, third, fourth], False, SAFE_BOTTOM, SAFE_WIDTH, art=busy, head_top=0.3) is None


def cover_run(tmp_path, monkeypatch, cast=CAST, cover=MID, **kwargs):
    seen = []
    real = cover_module.letter_cover
    monkeypatch.setattr(cover_module, "letter_cover", lambda *a, **k: seen.append(k) or real(*a, **k))
    images = FakeImages([Image.new("RGB", (400, 600), (90, 120, 160))])
    path = render_cover(cast, {"scene": "Dana on the cliff", **cover}, (400, 600), tmp_path / "cover.png", images,
                        FakeVision(lambda p, i: {**CLEAN, "head_top": 300}), art_path=tmp_path / "art.png", **kwargs)
    return Image.open(path).convert("RGB"), seen[0], images.calls


def test_render_cover_without_a_badge_calls_the_lettering_as_before(tmp_path, monkeypatch, mark):
    plain, keywords, calls = cover_run(tmp_path, monkeypatch)
    assert keywords == {"title_at_bottom": False}  # no badge keyword at all
    badged, keywords, badged_calls = cover_run(tmp_path, monkeypatch, badge=CoverBadge(mark()))
    assert keywords["badge"].rtl is None and keywords["head_top"] == 0.3  # the measured head goes with the badge
    assert corner(badge_box(badged), (400, 600)) == ("bottom", "right")  # this title reaches both top corners
    assert badged_calls == calls  # the same draw: the badge never reaches the image model
    assert badge_box(Image.open(tmp_path / "art.png").convert("RGB")) is None  # the unlettered art stays clean
    missing, _, _ = cover_run(tmp_path, monkeypatch, badge=CoverBadge(tmp_path / "missing.png"))
    assert missing.tobytes() == plain.tobytes()
    above, _, _ = cover_run(tmp_path, monkeypatch, cover=ONLY_TITLE, badge=CoverBadge(mark()))
    assert corner(badge_box(above), (400, 600)) == ("top", "right")  # a short title: the corner above the measured head


def test_render_cover_takes_the_corner_from_the_comics_language(tmp_path, monkeypatch, mark):
    hebrew, keywords, _ = cover_run(tmp_path, monkeypatch, cast={**CAST, "language": "he"}, badge={"path": str(mark())})
    assert keywords["badge"].rtl is True and corner(badge_box(hebrew), (400, 600)) == ("bottom", "left")
    english, _, _ = cover_run(tmp_path, monkeypatch, cast={**CAST, "language": "en"}, badge=CoverBadge(mark()))
    assert corner(badge_box(english), (400, 600)) == ("bottom", "right")
    forced, _, _ = cover_run(tmp_path, monkeypatch, cast={**CAST, "language": "he"}, badge=CoverBadge(mark(), rtl=False))
    assert corner(badge_box(forced), (400, 600)) == ("bottom", "right")
    short, _, _ = cover_run(tmp_path, monkeypatch, cast={**CAST, "language": "he"}, cover=ONLY_TITLE, badge=CoverBadge(mark()))
    assert corner(badge_box(short), (400, 600)) == ("top", "left")  # above the head, on the side where Hebrew reading ends
