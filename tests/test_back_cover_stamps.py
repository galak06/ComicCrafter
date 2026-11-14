"""The back cover's optional corner stamps: on the print-safe bottom margin, under the text, with the footer between them."""

import numpy as np
import pytest
from PIL import Image

from book_comic import back_cover as back_module
from book_comic.back_cover import render_back_cover
from book_comic.back_cover_lettering import letter_back_cover
from book_comic.cover_lettering import SAFE_BOTTOM, SAFE_WIDTH
from book_comic.cover_stamps import SHRINKS, CornerStamp, as_stamps, fit_stamps, room_between
from conftest import FakeImages, FakeVision
from test_back_cover import BACK, CAST, HE_BACK
from test_cover_print_safe import MARGIN_MM, PRINTERS, H, W, inside_trim_mm, lettered_lines

SMALL = (W // 3, H // 3)
TEAL, CREAM = (15, 118, 110), (250, 240, 200)  # the two stamps: neither colour is in the art or the lettering
FOOTER = {**BACK, "footer": "For Dana, with love"}
HE_FOOTER = {**HE_BACK, "footer": "בשביל סבא"}
WIDE_FOOTER = {**BACK, "footer": "For my dearest grandfather, with all the love in the world, from all of us at home"}
GAP = SMALL[1] // 50


@pytest.fixture
def stamps(tmp_path):
    """A wide teal tile for the right corner and a tall cream panel for the left, as files; a factory for other shapes."""
    def make(logo=(600, 470), panel=(520, 1060), logo_width=0.14, panel_width=0.12):
        Image.new("RGB", logo, TEAL).save(tmp_path / "logo.png")
        Image.new("RGB", panel, CREAM).save(tmp_path / "panel.png")
        return [CornerStamp(tmp_path / "logo.png", "right", logo_width), {"path": str(tmp_path / "panel.png"), "corner": "left", "width": panel_width}]
    return make


def art(size=SMALL):
    return Image.new("RGB", size, (90, 120, 160))


def box_of(image, colour):
    ys, xs = np.where(np.all(np.asarray(image) == colour, axis=2))
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(ys) else None


def panel_bottom(image):
    """The last row of the dark text panel, read just inside its left edge above the stamps (the art is one flat colour)."""
    column = np.asarray(image)[: image.height * 2 // 3, int(image.width * 0.105)]
    return int(np.where(np.any(column != column[0], axis=1))[0].max())


def test_no_stamps_and_unusable_stamps_letter_the_back_cover_exactly_as_before(tmp_path):
    plain = letter_back_cover(art(), FOOTER)
    (tmp_path / "broken.png").write_bytes(b"not a picture")
    unusable = [CornerStamp(tmp_path / "missing.png"), {"path": str(tmp_path / "broken.png")}, {"corner": "left"}, "logo.png",
                {"path": "x.png", "corner": "top"}]
    for given in ((), None, [], unusable):
        assert letter_back_cover(art(), FOOTER, stamps=given).tobytes() == plain.tobytes()
    assert as_stamps(unusable) == [CornerStamp(tmp_path / "missing.png"), CornerStamp(str(tmp_path / "broken.png"))]


@pytest.mark.parametrize("back", [BACK, HE_BACK, FOOTER, HE_FOOTER])
def test_the_logo_stands_bottom_right_and_the_panel_bottom_left_in_both_languages(stamps, back):
    w, h = SMALL
    lettered = letter_back_cover(art(), back, stamps=stamps())
    logo, panel = box_of(lettered, TEAL), box_of(lettered, CREAM)
    inset, bottom = int(np.ceil(w * (1 - SAFE_WIDTH) / 2)), h - int(np.ceil(h * SAFE_BOTTOM))
    assert (logo[2], logo[3]) == (w - inset, bottom) and (panel[0], panel[3]) == (inset, bottom)  # the same corners and bottom line
    assert logo[2] - logo[0] == round(0.14 * w) and panel[2] - panel[0] == round(0.12 * w)
    assert 2 <= (panel[3] - panel[1]) / (logo[3] - logo[1]) <= 2.5
    assert min(logo[1], panel[1]) >= panel_bottom(letter_back_cover(art(), back)) + GAP  # under the text panel


def test_stamps_change_nothing_but_their_own_boxes_when_the_footer_fits_between_them(stamps):
    plain, stamped = np.asarray(letter_back_cover(art(), FOOTER)), np.asarray(letter_back_cover(art(), FOOTER, stamps=stamps()))
    changed = np.any(plain != stamped, axis=2)
    for left, top, right, bottom in (box_of(Image.fromarray(stamped), TEAL), box_of(Image.fromarray(stamped), CREAM)):
        changed[top:bottom, left:right] = False
    assert not changed.any()


def test_a_wide_footer_is_wrapped_between_the_stamps_and_touches_neither(stamps):
    w, h = SMALL
    plain = letter_back_cover(art(), WIDE_FOOTER)
    stamped = letter_back_cover(art(), WIDE_FOOTER, stamps=stamps())
    logo, panel = box_of(stamped, TEAL), box_of(stamped, CREAM)
    end = panel_bottom(plain)
    before = [line for line in lettered_lines(plain) if line[0] > end]
    after = [line for line in lettered_lines(stamped) if line[0] > end]
    assert min(left for _, _, left, _ in before) < panel[2] or max(right for *_, right in before) > logo[0]  # it would have run under them
    assert len(after) > len(before)  # wrapped onto more lines
    for top, bottom, left, right in after:
        assert left >= panel[2] + GAP and right <= logo[0] - GAP
        assert bottom <= h - int(np.ceil(h * SAFE_BOTTOM)) + 2 and abs((left + right) / 2 - w / 2) <= 2  # still centred on the bottom margin


def test_room_between_is_the_centred_width_clear_of_every_stamp():
    picture = Image.new("RGBA", (10, 10))
    assert room_between([], 1000, 20) is None
    assert room_between([(picture, (800, 0, 900, 10))], 1000, 20) == 560  # one stamp narrows both sides: the line stays centred
    assert room_between([(picture, (800, 0, 900, 10)), (picture, (100, 0, 260, 10))], 1000, 20) == 440


@pytest.mark.parametrize("room, shrink, drawn", [(600, 1.0, 2), (505, 1.0, 2), (500, 0.975, 2), (380, 0.75, 2), (370, None, 1), (200, None, 0)])
def test_too_little_room_shrinks_both_stamps_together_then_leaves_out_what_does_not_fit(stamps, room, shrink, drawn):
    """At print size the tile is 289 x 226 px and the panel 248 x 505 px: both share one size, down to three quarters."""
    bottom = H - int(np.ceil(H * SAFE_BOTTOM))
    placed = fit_stamps(stamps(), (W, H), bottom - room, SAFE_BOTTOM, SAFE_WIDTH)
    assert len(placed) == drawn
    if shrink:
        assert shrink in SHRINKS and [box[2] - box[0] for _, box in placed] == [round(289 * shrink), round(248 * shrink)]
    elif drawn:  # the tall panel is left out; the tile fits at full size
        assert placed[0][1] == (W - 227 - 289, bottom - 226, W - 227, bottom)
    assert all(box[1] >= bottom - room and box[3] == bottom and picture.size == (box[2] - box[0], box[3] - box[1]) for picture, box in placed)


def test_stamps_never_touch_each_other_and_sizes_stay_in_range(stamps, tmp_path):
    placed = fit_stamps(stamps(logo_width=0.9, panel_width=0.01), SMALL, 0, SAFE_BOTTOM, SAFE_WIDTH)
    assert [box[2] - box[0] for _, box in placed] == [round(0.25 * SMALL[0]), round(0.06 * SMALL[0])]  # kept within 6% to 25%
    same_corner = [CornerStamp(tmp_path / "logo.png", "right"), CornerStamp(tmp_path / "panel.png", "right")]
    assert len(fit_stamps(same_corner, SMALL, 0, SAFE_BOTTOM, SAFE_WIDTH)) == 1  # the second would lie on the first
    tall = fit_stamps(stamps(panel=(100, 2000)), SMALL, 0, SAFE_BOTTOM, SAFE_WIDTH)
    assert tall[1][1][3] - tall[1][1][1] == round(0.25 * SMALL[1])  # a tall picture is scaled down to a quarter of the height


def test_a_back_cover_without_text_still_carries_the_stamps(stamps):
    lettered = letter_back_cover(art(), {"tagline": "", "blurb": ""}, stamps=stamps())
    assert box_of(lettered, TEAL) and box_of(lettered, CREAM)


@pytest.mark.parametrize("printer", PRINTERS)
@pytest.mark.parametrize("back", [FOOTER, HE_BACK, WIDE_FOOTER])
def test_the_stamps_and_the_footer_print_inside_both_printers_margins(stamps, printer, back):
    lettered = letter_back_cover(art((W, H)), back, stamps=stamps())
    end = panel_bottom(letter_back_cover(art((W, H)), back))
    footer = [line for line in lettered_lines(lettered) if line[0] > end]
    for left, top, right, bottom in (box_of(lettered, TEAL), box_of(lettered, CREAM)):
        footer.append((top, bottom, left, right))
    for line in footer:
        mm = inside_trim_mm(line, PRINTERS[printer])
        assert mm["bottom"] >= MARGIN_MM and mm["side"] >= MARGIN_MM and mm["top"] >= 12.7


def run(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr(back_module, "find_seam", lambda art: None)
    images = FakeImages([Image.new("RGB", SMALL, (90, 120, 160))])
    vision = FakeVision(lambda prompt, image: {"has_text": False, "bad_anatomy": False, "head_top": None, "figure_visible": False})
    render_back_cover({**CAST, "language": "he"}, HE_FOOTER, SMALL, tmp_path / "back.png", images, vision, **kwargs)
    return Image.open(tmp_path / "back.png").convert("RGB"), images


def test_render_back_cover_draws_the_stamps_on_the_lettered_back_cover(tmp_path, monkeypatch, stamps):
    plain, _ = run(tmp_path, monkeypatch)
    stamped, images = run(tmp_path, monkeypatch, stamps=stamps())
    assert len(images.calls) == 1 and box_of(plain, TEAL) is None
    assert box_of(stamped, TEAL)[0] > SMALL[0] / 2 > box_of(stamped, CREAM)[2]  # a Hebrew cover: still logo right, panel left


def test_render_back_cover_without_stamps_calls_the_lettering_as_before(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(back_module, "letter_back_cover", lambda *args, **kwargs: seen.append((len(args), kwargs)) or args[0])
    run(tmp_path, monkeypatch)
    run(tmp_path, monkeypatch, stamps=[])
    assert seen == [(3, {}), (3, {})]
