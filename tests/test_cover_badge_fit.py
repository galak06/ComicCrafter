"""With a measured head the badge is drawn smaller to fit a top corner above it, and is left out over the figure.

Real cover 2026-11-14 (English preview): once the title was lettered at the top, the 289 px badge was 43 px short of
the top-left corner beside it and fell to the bottom-right corner, on the robot's arm and wheel; the other bottom
corner lay on the hero's boot. At 85% of its size it fits the top corner over the empty window.
"""

import pytest
from PIL import Image

from book_comic.cover_badge import ROUGH_LIMIT, SHRINKS, TOP_SAFE, WIDTH_RANGE, CoverBadge, badge_boxes, place_badge, roughness
from book_comic.cover_lettering import SAFE_BOTTOM, SAFE_WIDTH
from test_cover_badge import CORNERS, art, mark, scene  # noqa: F401 (mark is a fixture)
from test_cover_print_safe import H, W

SIDE = round(W * 0.14)  # the square test badge at full size: 289 px, the real badge's width
GAP = H // 50
BOTTOM_END, BOTTOM_START, TOP_END, TOP_START = badge_boxes((SIDE, SIDE), (W, H), "bottom", False, SAFE_BOTTOM, SAFE_WIDTH)
BLACK = (0, 0, 0)


def title(short_by):
    """A title box across the top that leaves each top corner `short_by` px short of the badge's clearance."""
    return (TOP_START[2] + GAP - short_by, 202, TOP_END[0] - GAP + short_by, 360)


def place(picture, lettering, **kwargs):
    page = picture.convert("RGBA")
    box = place_badge(page, CoverBadge(kwargs.pop("mark")), lettering, False, SAFE_BOTTOM, SAFE_WIDTH, art=picture, **kwargs)
    return box, page.convert("RGB").tobytes() != picture.tobytes()


def test_the_badge_is_drawn_a_little_smaller_to_fit_beside_the_title_above_the_head(mark):
    box, drawn = place(art((W, H)), [title(43)], mark=mark(), head_top=0.3)
    width = box[2] - box[0]
    assert drawn and box[1] == TOP_END[1] and box[2] == TOP_END[2]  # the top corner on the reading-end side, at the safe inset
    assert width == box[3] - box[1] == round(SIDE * 0.85)  # the largest step that fits: 246 px of 289
    assert box[0] - title(43)[2] >= GAP  # the clearance from the title is the usual one
    assert place(art((W, H)), [title(0)], mark=mark(), head_top=0.3)[0] == TOP_END  # a badge that fits is not touched


def test_the_badge_is_also_drawn_smaller_to_end_above_the_head(mark):
    head = (TOP_END[1] + SIDE * 0.9) / H  # the full badge would reach 10% of its height into the head's rows
    box, _ = place(art((W, H)), [], mark=mark(), head_top=head)
    assert box[1] == TOP_END[1] and box[3] <= head * H and box[3] - box[1] == round(SIDE * 0.9)


def test_without_a_measured_head_nothing_is_shrunk_or_refused(mark):
    rough = scene(*CORNERS, size=(W, H), colour=BLACK)
    assert place(art((W, H)), [title(43)], mark=mark())[0] == BOTTOM_END  # full size, the first free corner, as before
    assert place(rough, [title(43)], mark=mark())[0] == BOTTOM_END


def test_the_badge_never_shrinks_below_three_quarters_or_below_a_readable_width(mark):
    assert SHRINKS[0] == 1.0 and min(SHRINKS) == 0.75
    short = SIDE - round(SIDE * 0.75) + 1  # one pixel more than the smallest badge makes up
    assert place(art((W, H)), [title(short)], mark=mark(), head_top=0.3)[0] == BOTTOM_END  # full size, at the bottom
    narrow = CoverBadge(mark(), width=WIDTH_RANGE[0])  # already as narrow as a badge may be
    page = art((W, H)).convert("RGBA")
    box = place_badge(page, narrow, [(0, 0, W, 360)], False, SAFE_BOTTOM, SAFE_WIDTH, art=art((W, H)), head_top=0.3)
    assert box[2] - box[0] == round(W * WIDTH_RANGE[0]) and box[1] > H / 2


@pytest.mark.parametrize("shapes, expected", [((), BOTTOM_END), (("bottom-end",), BOTTOM_START), (("bottom-start",), BOTTOM_END),
                                               (("bottom-end", "bottom-start"), None)])
def test_a_bottom_corner_is_used_only_over_calm_art_and_no_badge_beats_one_on_the_figure(mark, shapes, expected):
    picture = scene(*shapes, size=(W, H), colour=BLACK)
    for name in shapes:
        assert roughness(picture, (BOTTOM_END, BOTTOM_START)[CORNERS[name]]) > ROUGH_LIMIT
    box, drawn = place(picture, [title(200)], mark=mark(), head_top=0.3)  # the title leaves no top corner, even shrunk
    assert box == expected and drawn is (expected is not None)


def test_roughness_is_the_colour_step_between_large_shapes():
    flat, half = art((W, H)), scene("bottom-end", size=(W, H), colour=BLACK)
    assert roughness(flat, BOTTOM_END) == 0 and roughness(half, BOTTOM_START) == 0
    assert 115 < roughness(half, BOTTOM_END) <= (90 + 120 + 160) / 3 + 1  # black against the (90, 120, 160) setting
    lined = art((W, H))
    for x in range(BOTTOM_END[0] - SIDE, BOTTOM_END[2] + SIDE, 12):  # thin dark lines, as a far building's windows
        lined.paste((20, 30, 60), (x, BOTTOM_END[1] - SIDE, x + 3, BOTTOM_END[3] + SIDE))
    assert roughness(lined, BOTTOM_END) < 20 < ROUGH_LIMIT
    assert TOP_END[1] == TOP_START[1] == round(H * TOP_SAFE)
