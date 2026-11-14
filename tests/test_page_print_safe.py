"""Every lettered pixel of an interior page prints inside the safe area of every comic printer, with fake clients.

The engine letters before the printer is known, so one page must pass both placements (book_comic/print_safe.py):
Lulu fits the 2063 x 3150 page into its 6.625 x 10.25 in trim and keeps text 0.5 in inside it; BookPod shrinks
the page into its 155 x 225 mm safe box (5 mm). Both the reported boxes and the actual lettering ink are measured.
"""

import numpy as np
import pytest
from PIL import Image

from book_comic.print_safe import (APP_COVER_INSETS_PX, APP_PAGE_INSETS_PX, BOOKPOD, DEFAULT_PRINT_SAFE, ENGINE_PAGE_PX,
                                   LULU, PrintSafe, as_print_safe, placement_insets)
from book_comic.render import PAGE_LAYOUTS, PRINT_PAGE_SIZE, PageRenderer, RenderOptions, print_layouts
from conftest import FakeImages, FakeVision
from layout.lettering import LETTERING_FONT
from layout.panel_layout import LayoutType

FONT = str(LETTERING_FONT)
ART = (127, 151, 163)  # flat art: every pixel that differs from it after lettering is lettering ink
PLACEMENTS = {"lulu": LULU, "bookpod": BOOKPOD}
CAST = {"style": "ink comic", "characters": [{"name_en": "Hero", "name": "Noa", "look": "teal blazer"},
                                             {"name_en": "Friend", "name": "Dan", "look": "red cap"}]}
TEXT = {
    False: {"caption": "The wind grew stronger over the distant hills, but the way to the old tower was finally clear "
                       "and close. Noa knew she had to get there before dark.",
            "short": "A deep groan echoes through the structure.",
            "lines": ["I know the way. Stay close to the wall!", "Wait for me, this bag is heavy!"],
            "note": "For Noa, with all our love", "sfx": "KRRRAAASH!"},
    True: {"caption": "הרוח התחזקה מעל הגבעות הרחוקות, אבל הדרך אל המגדל הישן כבר הייתה ברורה וקרובה. נועה ידעה שהיא "
                      "חייבת להגיע לשם לפני רדת החשכה.",
           "short": "רעם עמוק מהדהד בכל המבנה.",
           "lines": ["אני יודעת את הדרך. הישארו קרוב לקיר!", "חכי לי, התיק הזה כבד!"],
           "note": "לנועה, באהבה מכולנו", "sfx": "בום!"},
}
# Where the planner sends the bubbles (0-1000): hard against the corners and the bottom edge, mouths at the edges,
# so the old 5 px search and the tails toward the speakers ran into the trim.
# (A mouth in a bottom corner would put the head under the note, which refuses the panel before any bubble.)
EDGE_PLAN = {"lines": [{"mouth": [15, 640], "bubble": [30, 990]}, {"mouth": [985, 600], "bubble": [990, 995]},
                       {"mouth": [10, 20], "bubble": [0, 0]}, {"mouth": [990, 10], "bubble": [1000, 0]}],
             "protected": [[420, 300, 160, 400]], "sfx": [995, 995]}


def panels(rtl, content, splash):
    t = TEXT[rtl]
    if splash:
        return [{"scene": "Wide shot: the tower", "caption": t["caption"],
                 "dialogue": [{"speaker": "Hero", "text": t["lines"][0]}]}]
    long_captions = content == "long captions"
    return [{"scene": f"Wide shot: panel {n}",
             "caption": t["caption"] if long_captions else (t["short"] if n == 1 else ""),
             "dialogue": [{"speaker": "Hero", "text": t["lines"][0]}]
             + ([] if long_captions else [{"speaker": "Friend", "text": t["lines"][1], "bubble": kind}]),
             **({"note": t["note"]} if n == 3 else {}),
             **({"sfx": t["sfx"]} if content == "wide bottom balloons" else {})}
            for n, kind in zip((1, 2, 3), ("speech", "shout", "thought"))]


def render(tmp_path, rtl, content, splash, print_safe=None, plan=EDGE_PLAN):
    cast = {**CAST, "language": "he" if rtl else "en"}
    renderer = PageRenderer(cast, FakeImages([Image.new("RGB", (64, 64), ART)]), FakeVision(lambda p, i: dict(plan)),
                            print_layouts(), RenderOptions(font_path=FONT, print_safe=print_safe))
    path = renderer.render_page(panels(rtl, content, splash), tmp_path / "page.png", page=7)
    return renderer, path


def lettering_ink(renderer, path):
    """Mask of every page pixel the lettering changed: the page against its unlettered art composed the same way."""
    count = len(list(path.parent.glob(f"art_{path.stem}_*.png")))
    arts = [Image.open(path.parent / f"art_{path.stem}_{n}.png").convert("RGB") for n in range(1, count + 1)]
    layout = renderer.layouts.create_layout(PAGE_LAYOUTS[count], num_panels=count)
    plain = np.asarray(renderer.layouts.compose_page(arts, layout))
    return np.any(np.asarray(Image.open(path).convert("RGB")) != plain, axis=2)


def ink_box(mask):
    ys, xs = np.where(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) - int(xs.min()) + 1, int(ys.max()) - int(ys.min()) + 1


@pytest.mark.parametrize("printer", PLACEMENTS)
@pytest.mark.parametrize("rtl", [False, True], ids=["ltr", "rtl"])
@pytest.mark.parametrize("splash, content", [(False, "long captions"), (False, "wide bottom balloons"),
                                             (True, "long captions")], ids=["strip-captions", "strip-balloons", "splash"])
def test_every_lettered_pixel_prints_inside_the_printers_safe_area(tmp_path, printer, rtl, splash, content):
    renderer, path = render(tmp_path, rtl, content, splash)
    placement = PLACEMENTS[printer]
    boxes = renderer.lettering_boxes
    kinds = {b["kind"] for b in boxes}
    assert "caption" in kinds and "balloon" in kinds and all(b["page"] == 7 for b in boxes)
    if not splash:
        assert "note" in kinds
        if content == "wide bottom balloons":
            assert "sfx" in kinds
    margin = placement.margin_mm
    for box in boxes:
        assert min(placement.inside_trim_mm(box["box_px"]).values()) >= margin, box
    ink = lettering_ink(renderer, path)
    assert min(placement.inside_trim_mm(ink_box(ink)).values()) >= margin
    covered = np.zeros_like(ink)  # the report covers every inked pixel
    for box in boxes:
        x, y, w, h = box["box_px"]
        covered[y:y + h, x:x + w] = True
    assert not (ink & ~covered).any()


@pytest.mark.parametrize("rtl", [False, True], ids=["ltr", "rtl"])
def test_the_caption_takes_the_reading_first_top_corner_of_the_safe_box(tmp_path, rtl):
    renderer, _ = render(tmp_path, rtl, "long captions", False, plan={**EDGE_PLAN, "protected": []})
    left, top, right, _ = DEFAULT_PRINT_SAFE.page_bounds()
    first = next(b for b in renderer.lettering_boxes if b["kind"] == "caption")["box_px"]
    assert first[1] == top  # the top panel's caption sits on the safe box's top edge
    if rtl:
        assert first[0] + first[2] == right  # Hebrew: top-right, on the safe box's right edge
    else:
        assert first[0] == left  # English: top-left


@pytest.mark.parametrize("rtl", [False, True], ids=["ltr", "rtl"])
def test_a_face_under_the_reading_first_corner_sends_the_caption_to_the_other_one(tmp_path, rtl):
    face = [700, 0, 300, 450] if rtl else [0, 0, 300, 450]  # under the reading-first corner of every panel
    renderer, _ = render(tmp_path, rtl, "long captions", False, plan={**EDGE_PLAN, "protected": [face]})
    left, _, right, _ = DEFAULT_PRINT_SAFE.page_bounds()
    caption = next(b for b in renderer.lettering_boxes if b["kind"] == "caption")["box_px"]
    assert caption[0] == left if rtl else caption[0] + caption[2] == right
    layout = renderer.layouts.create_layout(LayoutType.VERTICAL_STRIP, num_panels=3)
    cx, _, cw, _ = layout[0].get_content_area()
    fx, fw = cx + face[0] * cw // 1000, face[2] * cw // 1000
    assert caption[0] >= fx + fw or caption[0] + caption[2] <= fx  # the caption is clear of the face


def test_a_stricter_box_from_the_app_moves_the_lettering_in(tmp_path):
    strict = {"page_inset_px": {"left": 260, "right": 260, "top": 240, "bottom": 240}}
    renderer, path = render(tmp_path, False, "wide bottom balloons", False, print_safe=strict)
    bounds = as_print_safe(strict).page_bounds()
    x, y, w, h = ink_box(lettering_ink(renderer, path))
    assert x >= bounds[0] and y >= bounds[1] and x + w <= bounds[2] and y + h <= bounds[3]


def test_lettering_with_no_safe_spot_is_refused_never_drawn_unsafe(tmp_path):
    tiny = {"page_inset_px": {"left": 900, "right": 900, "top": 148, "bottom": 148}}  # 263 px wide
    with pytest.raises(ValueError, match="comic_lettering_no_space"):
        render(tmp_path, False, "long captions", False, print_safe=tiny)
    assert not (tmp_path / "page.png").exists()


def test_the_default_box_is_the_strictest_printer_and_matches_the_app():
    assert ENGINE_PAGE_PX == PRINT_PAGE_SIZE
    page = DEFAULT_PRINT_SAFE.page
    assert (page.left, page.right, page.top, page.bottom) == APP_PAGE_INSETS_PX == (168, 168, 148, 148)
    assert placement_insets(LULU) == page
    bookpod = placement_insets(BOOKPOD)
    assert (bookpod.left, bookpod.right, bookpod.top, bookpod.bottom) == (0, 0, 14, 14)
    # The cover shares are at least as strict as the app's cover box on every side.
    left, top, right, bottom = DEFAULT_PRINT_SAFE.cover.bounds(ENGINE_PAGE_PX)
    w, h = ENGINE_PAGE_PX
    assert left >= APP_COVER_INSETS_PX[0] and w - right >= APP_COVER_INSETS_PX[1]
    assert top >= APP_COVER_INSETS_PX[2] and h - bottom >= APP_COVER_INSETS_PX[3]
    # The default page box prints 0.5 in + 1 mm inside Lulu's trim, and the whole page is inside BookPod's 5 mm.
    edge = (page.left, page.top, w - page.left - page.right, h - page.top - page.bottom)
    assert min(LULU.inside_trim_mm(edge).values()) >= 12.7 + 1 - 0.01
    assert min(BOOKPOD.inside_trim_mm((0, 0, w, h)).values()) >= 5


def test_an_override_round_trips_and_a_bad_one_fails_before_any_image_call():
    custom = as_print_safe({"page_inset_px": {"left": 200}, "cover_inset": {"top_px": 230, "bottom_px": 400, "side_px": 250}})
    assert (custom.page.left, custom.page.right) == (200, 168)
    assert custom.cover.bounds(ENGINE_PAGE_PX)[:2] == (250, 230)
    assert as_print_safe(custom.to_dict()) == custom and as_print_safe(None) == PrintSafe()
    images = FakeImages([Image.new("RGB", (64, 64), ART)])
    for bad in ({"page_inset_px": {"left": -1}}, {"page_inset_px": {"top": "x"}}, {"page_inset_px": {"left": 1100, "right": 1100}},
                {"cover_inset": {"width": 1.5}}, "lulu"):
        with pytest.raises(ValueError, match="comic_print_safe_invalid"):
            PageRenderer(CAST, images, FakeVision(), print_layouts(), RenderOptions(print_safe=bad))
    assert images.calls == []


def test_without_the_safe_box_the_lettering_prints_in_lulus_margin_as_on_books_48(tmp_path):
    """The measurement has teeth: lettered to the panel edges only (the old rule), the captions sit at about
    0.44 in and the bubbles nearer still on Lulu, as BOOKS-48 measured."""
    renderer, path = render(tmp_path, False, "wide bottom balloons", False,
                            print_safe={"page_inset_px": {"left": 0, "right": 0, "top": 0, "bottom": 0}})
    caption = next(b for b in renderer.lettering_boxes if b["kind"] == "caption")
    assert round(min(LULU.inside_trim_mm(caption["box_px"]).values()) / 25.4, 2) == 0.44
    assert min(LULU.inside_trim_mm(ink_box(lettering_ink(renderer, path))).values()) < LULU.margin_mm
