"""The optional back-cover badge: one centred spot clear of the panel, the blurb and the footer, inside the printers' margins."""

import numpy as np
import pytest
from PIL import Image

from book_comic import back_cover as back_module
from book_comic.back_cover import render_back_cover
from book_comic.back_cover_lettering import PANEL_TOP, letter_back_cover
from book_comic.cover_badge import SHRINKS, TOP_SAFE, CoverBadge, place_centred_badge
from book_comic.cover_lettering import SAFE_BOTTOM
from conftest import FakeImages, FakeVision
from test_back_cover import BACK, CAST, HE_BACK
from test_cover_badge import MAGENTA, SMALL, art, badge_box, mark  # noqa: F401 (mark is a fixture)
from test_cover_print_safe import MARGIN_MM, PRINTERS, H, W, inside_trim_mm, lettered_lines

FOOTER = {**BACK, "footer": "For Dana, with love"}
HE_FOOTER = {**HE_BACK, "footer": "בשביל סבא"}
LONG = {"tagline": "Terror flows through the pipes of the old house", "blurb": "A midnight call. A storm. A house that will not let go. " * 30,
        "footer": "For my dearest grandfather, with all the love in the world, from all of us at home"}  # a full panel, a two-line footer
GAP = SMALL[1] // 50


def lettered(back, size=SMALL, **badge):
    return letter_back_cover(art(size), back, badge=CoverBadge(**badge) if badge else None)


def test_no_badge_and_an_unusable_badge_letter_the_back_cover_exactly_as_before(tmp_path):
    plain = letter_back_cover(art(), FOOTER)
    (tmp_path / "broken.png").write_bytes(b"not a picture")
    for badge in (None, {}, CoverBadge(tmp_path / "missing.png"), {"path": str(tmp_path / "broken.png")}):
        assert letter_back_cover(art(), FOOTER, badge=badge).tobytes() == plain.tobytes()


@pytest.mark.parametrize("back", [BACK, HE_BACK, FOOTER, HE_FOOTER])
def test_the_badge_is_centred_at_the_bottom_above_the_footer_in_both_languages(mark, back):
    w, h = SMALL
    left, top, right, bottom = badge_box(lettered(back, path=mark()))
    assert abs((left + right) / 2 - w / 2) <= 1  # centred: the same spot right to left and left to right
    assert abs((right - left + 20 * (right - left) / 280) / w - 0.14) < 0.006  # 14% of the width with the file's border
    lines = lettered_lines(letter_back_cover(art(), back))
    if back.get("footer"):
        assert 0 <= lines[-1][0] - GAP - bottom <= 14  # one lettering gap above the footer line (and the file's border)
    else:
        assert 0 <= h - np.ceil(h * SAFE_BOTTOM) - bottom <= 14  # ends at the lettering's bottom margin
    assert top - GAP >= int(h * PANEL_TOP) + 1 and top > h / 2  # below the panel


def test_position_top_puts_the_badge_between_the_top_margin_and_the_panel(mark):
    w, h = SMALL
    for back in (BACK, HE_FOOTER, LONG):
        left, top, right, bottom = badge_box(lettered(back, path=mark(), position="top"))
        assert abs((left + right) / 2 - w / 2) <= 1
        assert top >= np.ceil(h * TOP_SAFE) and bottom + GAP <= int(h * PANEL_TOP)
        assert abs((top - np.ceil(h * TOP_SAFE)) - (int(h * PANEL_TOP) - GAP - bottom)) <= 2  # in the middle of those rows


def test_a_badge_changes_only_its_own_box_and_its_shadow(mark):
    plain, badged = np.asarray(letter_back_cover(art(), FOOTER)), np.asarray(lettered(FOOTER, path=mark()))
    left, top, right, bottom = badge_box(Image.fromarray(badged))
    ys, xs = np.where(np.any(plain != badged, axis=2))
    reach = 4 * max(3, SMALL[1] // 400) + 10  # the shadow's blur, and the file's transparent border
    assert xs.min() >= left - reach and xs.max() <= right + reach and ys.min() >= top - reach and ys.max() <= bottom + reach
    assert ys.max() < lettered_lines(Image.fromarray(plain))[-1][0]  # nothing changes on the footer's rows


def panel_bottom(image):
    """The last row of the dark text panel, read just inside its left edge (the art is one flat colour)."""
    column = np.asarray(image)[:, int(image.width * 0.11)]
    return int(np.where(np.any(column != column[0], axis=1))[0].max())


def test_a_long_blurb_and_a_two_line_footer_leave_the_badge_between_them_touching_neither(mark):
    plain = letter_back_cover(art(), LONG)
    end = panel_bottom(plain)
    footer_top = min(top for top, *_ in lettered_lines(plain) if top > end)
    left, top, right, bottom = badge_box(lettered(LONG, path=mark((400, 400)), width=0.2))
    assert top - 4 >= end + GAP and bottom + 4 <= footer_top - GAP + 1  # the file's border is 3 to 4 px at this size


@pytest.mark.parametrize("room, share", [(200, 1.0), (126, 1.0), (125, 0.975), (100, 0.775), (95, 0.75), (93, None)])
def test_too_few_rows_shrink_the_badge_down_to_three_quarters_and_then_draw_none(mark, room, share):
    """A 300 px square file at 14% of a 900 px page is 126 px: it ends at the last row, centred, or is not drawn."""
    page = Image.new("RGBA", (900, 1200), (90, 120, 160, 255))
    box = place_centred_badge(page, CoverBadge(mark()), 500, 500 + room)
    if share is None:
        assert box is None and page.getcolors() == [(900 * 1200, (90, 120, 160, 255))]
        return
    assert box[3] == 500 + room and box[1] >= 500 and box[2] - box[0] == round(126 * share)
    assert abs((box[0] + box[2]) / 2 - 450) <= 1 and share in SHRINKS


def test_a_narrow_badge_is_never_shrunk_below_the_readable_width(mark):
    page = Image.new("RGBA", (900, 1200), (90, 120, 160, 255))
    assert place_centred_badge(page, CoverBadge(mark(), width=0.06), 500, 600) is not None  # 54 px: fits at full size
    assert place_centred_badge(page, CoverBadge(mark(), width=0.06), 500, 550) is None  # would need to go under 6%


def test_the_shadow_is_drawn_under_the_badge_only_when_asked(mark):
    plain, shadowed = (Image.new("RGBA", (900, 1200), (200, 200, 200, 255)) for _ in range(2))
    box = place_centred_badge(plain, CoverBadge(mark()), 500, 700)
    assert place_centred_badge(shadowed, CoverBadge(mark()), 500, 700, shadow=4) == box
    assert plain.getpixel((box[0] - 2, box[3] - 20)) == (200, 200, 200, 255)
    assert shadowed.getpixel((box[0] + 8, box[3] - 4))[0] < 200  # the file's transparent border is darkened


def test_a_back_cover_without_text_carries_the_badge_at_the_bottom(mark):
    for position in ("bottom", "top"):
        left, top, right, bottom = badge_box(lettered({"tagline": "", "blurb": ""}, path=mark(), position=position))
        assert 0 <= SMALL[1] - np.ceil(SMALL[1] * SAFE_BOTTOM) - bottom <= 14


@pytest.mark.parametrize("printer", PRINTERS)
@pytest.mark.parametrize("back, position", [(FOOTER, "bottom"), (HE_BACK, "bottom"), (LONG, "bottom"), (HE_FOOTER, "top"), (LONG, "top")])
def test_the_badge_prints_inside_both_printers_margins(mark, printer, back, position):
    left, top, right, bottom = badge_box(lettered(back, size=(W, H), path=mark((400, 400)), position=position))
    mm = inside_trim_mm((top - 14, bottom + 14, left - 14, right + 14), PRINTERS[printer])  # with the file's transparent border
    assert mm["bottom"] >= MARGIN_MM and mm["side"] >= MARGIN_MM and mm["top"] >= 12.7


def run(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr(back_module, "find_seam", lambda art: None)
    images = FakeImages([Image.new("RGB", SMALL, (90, 120, 160))])
    vision = FakeVision(lambda prompt, image: {"has_text": False, "bad_anatomy": False, "head_top": None, "figure_visible": False})
    render_back_cover({**CAST, "language": "he"}, HE_FOOTER, SMALL, tmp_path / "back.png", images, vision, **kwargs)
    return Image.open(tmp_path / "back.png").convert("RGB"), images


def test_render_back_cover_draws_the_badge_on_the_lettered_back_cover_only(tmp_path, monkeypatch, mark):
    plain, _ = run(tmp_path, monkeypatch)
    for badge in (CoverBadge(mark()), {"path": str(mark()), "width": 0.14, "position": "bottom"}):
        badged, images = run(tmp_path, monkeypatch, badge=badge)
        assert len(images.calls) == 1 and badge_box(badged) is not None and badge_box(plain) is None
    top, _ = run(tmp_path, monkeypatch, badge={"path": str(mark()), "position": "top"})
    assert badge_box(top)[3] < SMALL[1] * PANEL_TOP


def test_render_back_cover_without_a_badge_calls_the_lettering_as_before(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(back_module, "letter_back_cover", lambda *args, **kwargs: seen.append((len(args), kwargs)) or args[0])
    run(tmp_path, monkeypatch)
    run(tmp_path, monkeypatch, badge=None)
    assert seen == [(3, {}), (3, {})]
