"""A top title block that misses the head by a little keeps the top with a smaller title, with fake clients.

Real cover 2026-11-14 (English preview, "Gadget Gone Wild" in Amatic SC at 1.6): the title was 6.1% of the height
tall (Rubik Black's is 4.6%), the block ended 16.9% down and the head began at 17.8%, 0.9% below it: 1.1% short of
the 2% gap. The title, the starring line and the dedication were lettered across the hero's shin and the robot
under an empty window. At 0.8 of its size the title ends the block 15.6% down.
"""

import pytest
from PIL import Image

from book_comic import cover as cover_module
from book_comic.cover import HEAD_GAP, render_cover, title_goes_bottom
from book_comic.cover_lettering import MIN_TITLE_SHRINK, SAFE_TOP, CoverFonts, letter_cover, top_block_end, top_title_shrink
from conftest import FakeImages, FakeVision
from test_cover_print_safe import CAST, CLEAN, H, W, lettered_lines

TALL = CoverFonts(title_scale=1.7)  # Rubik Black's capitals enlarged to a title 6.1% of the height tall, as the Amatic one was
COVER = {"title": "Gone Wild", "starring": "Starring Leo", "footer": "For Leo, keep on inventing"}
END = top_block_end((W, H), COVER, TALL)
NEAR = END + HEAD_GAP - 0.011  # the real head: 1.1% of the height short of the gap


def art():
    return Image.new("RGB", (W, H), (90, 120, 160))


def test_a_block_that_misses_the_head_by_a_little_keeps_the_top_with_a_smaller_title():
    assert round(END, 3) == 0.169  # where the real block ended
    shrink = top_title_shrink(NEAR, (W, H), COVER, TALL, HEAD_GAP)
    assert MIN_TITLE_SHRINK <= shrink < 1 and not title_goes_bottom(NEAR, (W, H), COVER, TALL)
    assert top_block_end((W, H), COVER, TALL, shrink) + HEAD_GAP <= NEAR  # the gap is there
    assert top_block_end((W, H), COVER, TALL, shrink + 0.025) + HEAD_GAP > NEAR  # and the title is no smaller than it has to be


def test_the_smaller_title_is_lettered_where_it_was_measured():
    shrink = top_title_shrink(NEAR, (W, H), COVER, TALL, HEAD_GAP)
    full_title, full_starring, footer = lettered_lines(letter_cover(art(), COVER, TALL))
    title, starring, same_footer = lettered_lines(letter_cover(art(), COVER, TALL, title_shrink=shrink))
    assert title[0] >= int(H * SAFE_TOP) and abs(starring[1] - top_block_end((W, H), COVER, TALL, shrink) * H) <= 2
    assert starring[1] <= (NEAR - HEAD_GAP) * H + 2 < full_starring[1]  # clear of the head now, not before
    ratio = (title[1] - title[0]) / (full_title[1] - full_title[0])
    assert abs(ratio - shrink) < 0.02 and title[3] - title[2] < full_title[3] - full_title[2]  # only the title is smaller
    assert starring[1] - starring[0] == full_starring[1] - full_starring[0] and same_footer == footer
    assert abs((title[2] + title[3]) - W) <= 4  # still centred


def test_a_title_that_fits_is_not_touched():
    assert top_title_shrink(END + HEAD_GAP, (W, H), COVER, TALL, HEAD_GAP) == 1.0
    assert letter_cover(art(), COVER, TALL, title_shrink=1.0).tobytes() == letter_cover(art(), COVER, TALL).tobytes()
    assert top_title_shrink(0.5, (W, H), {"starring": "Starring Leo"}, gap=HEAD_GAP) == 1.0  # no title to shrink
    assert top_title_shrink(0.05, (W, H), {"starring": "Starring Leo"}, gap=HEAD_GAP) is None


def test_a_head_inside_even_the_smallest_block_still_moves_the_title_to_the_bottom():
    lowest = top_block_end((W, H), COVER, TALL, MIN_TITLE_SHRINK) + HEAD_GAP
    assert top_title_shrink(lowest, (W, H), COVER, TALL, HEAD_GAP) == MIN_TITLE_SHRINK
    assert top_title_shrink(lowest - 0.001, (W, H), COVER, TALL, HEAD_GAP) is None and title_goes_bottom(lowest - 0.001, (W, H), COVER, TALL)


@pytest.mark.parametrize("head, expected", [("near", {"title_at_bottom": False, "title_shrink": 0.8}),
                                            ("clear", {"title_at_bottom": False}), ("high", {"title_at_bottom": True})])
def test_render_cover_letters_the_near_miss_at_the_top(tmp_path, monkeypatch, head, expected):
    head = {"near": NEAR, "clear": END + HEAD_GAP + 0.01, "high": 0.1}[head]
    seen = []
    monkeypatch.setattr(cover_module, "letter_cover", lambda art, c, f, **keywords: seen.append(keywords) or art)
    size = (W // 4, H // 4)
    render_cover(CAST, {"scene": "Leo in the workshop", **COVER}, size, tmp_path / "cover.png", FakeImages([Image.new("RGB", size, "red")]),
                 FakeVision(lambda p, i: {**CLEAN, "head_top": head * 1000}), fonts=TALL)
    assert len(seen) == 1 and seen[0].keys() == expected.keys() and seen[0]["title_at_bottom"] is expected["title_at_bottom"]
    if "title_shrink" in expected:  # measured at the cover's own size, a quarter of print size here
        assert MIN_TITLE_SHRINK <= seen[0]["title_shrink"] < 1
        assert top_block_end(size, COVER, TALL, seen[0]["title_shrink"]) + HEAD_GAP <= head
