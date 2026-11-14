"""Cover lettering and the hero's head stay inside the printers' margin on the printed cover, with fake clients.

The printed cover (the Books repo's comicPrint `coverFront`) scales the 2063 x 3150 px art to cover the front
panel and its bleed, so the art's edges are cut away. PRINTERS repeats both printers' cuts.
"""

import numpy as np
import pytest
from PIL import Image

from book_comic import cover as cover_module
from book_comic.back_cover_lettering import letter_back_cover
from book_comic.cover import HEAD_GAP, HEAD_SAFE_MIN, HEADROOM_FIX, render_cover, title_goes_bottom
from book_comic.cover_lettering import MIN_TITLE_SHRINK, SAFE_TOP, letter_cover, top_block_end, top_title_shrink
from book_comic.revise import REVISE_MARK
from conftest import FakeImages, FakeVision

W, H = 2063, 3150
MARGIN_MM = 12.7 + 1  # Lulu's text margin inside the trim, and 1 mm to spare
# panel: the front's trim width + the outer bleed; sheet: the trim height + both bleeds; top_cut: art cut above the trim.
PRINTERS = {"lulu": {"panel": 168.275 + 3.175, "sheet": 260.35 + 2 * 3.175, "bleed": 3.175, "top_cut": None},
            "bookpod": {"panel": 165 + 3.2, "sheet": 235 + 2 * 3.2, "bleed": 3.2, "top_cut": 7.8}}
SHORT = {"title": "Curiosity's Spark", "starring": "Starring Maya"}  # BOOKS-45
LONG = {"title": "The Extraordinarily Long Birthday Adventure of Grandpa",
        "starring": "Starring Maximilian Alexander the Third of the Northern Lighthouse Islands",  # wraps to two lines
        "footer": "For my dearest grandfather, with all the love in the world, from all of us at home"}  # two lines
HEBREW = {"title": "המצאת יום ההולדת הגדולה והמופלאה של סבא", "starring": "בכיכוב דנה", "footer": "בשביל סבא"}
CAST = {"style": "comic", "characters": [{"name_en": "Dana", "look": "red coat"}]}
CLEAN = {"has_text": False, "bad_anatomy": False, "identity_mismatch": False, "design_mismatch": False, "scene_mismatch": False}


def lettered_lines(image):
    """(top, bottom, left, right) in px of each run of rows holding white lettering, top to bottom."""
    mask = np.asarray(image).min(axis=2) >= 250
    rows, lines, start = [*mask.any(axis=1), False], [], None
    for y, on in enumerate(rows):
        if on and start is None:
            start = y
        elif not on and start is not None:
            xs = np.where(mask[start:y].any(axis=0))[0]
            lines.append((start, y, int(xs.min()), int(xs.max()) + 1))
            start = None
    return lines


def inside_trim_mm(line, printer):
    """How far inside the printed trim a lettered line sits: top, bottom, and the nearer side (the outer one)."""
    top, bottom, left, right = line
    scale = max(printer["panel"] / W, printer["sheet"] / H)
    overflow = H * scale - printer["sheet"]
    above = overflow / 2 if printer["top_cut"] is None else min(max(printer["top_cut"] - printer["bleed"], 0), overflow)
    side = (W * scale - printer["panel"]) / 2 + printer["bleed"]
    return {"top": top * scale - above - printer["bleed"], "bottom": (H - bottom) * scale - (overflow - above) - printer["bleed"],
            "side": min(left, W - right) * scale - side}


@pytest.mark.parametrize("printer", PRINTERS)
@pytest.mark.parametrize("at_bottom", [True, False])
@pytest.mark.parametrize("cover, lines", [(SHORT, 2), (LONG, 5), (HEBREW, 3)])
def test_cover_lettering_prints_inside_the_margin(printer, at_bottom, cover, lines):
    found = lettered_lines(letter_cover(Image.new("RGB", (W, H), (90, 120, 160)), cover, title_at_bottom=at_bottom))
    assert len(found) == lines  # the title stays one line; a long starring line and footer wrap to two
    for line in found:
        mm = inside_trim_mm(line, PRINTERS[printer])
        assert mm["bottom"] >= MARGIN_MM and mm["side"] >= MARGIN_MM
        # A top title is 15.5 mm inside Lulu's trim (SAFE_TOP 0.07; it was 13.9 mm at 0.064) and 10.2 mm inside
        # BookPod's B5: past its own 5 mm text line with 1 mm to spare, short of Lulu's margin.
        assert mm["top"] >= (MARGIN_MM + 1 if printer == "lulu" else 5 + 1)


def test_the_bottom_title_block_of_books_45_moved_out_of_the_margin():
    """BOOKS-45: the starring line ended 4.2 mm above Lulu's trim and was cut off whole on BookPod's B5."""
    title, starring = lettered_lines(letter_cover(Image.new("RGB", (W, H), (90, 120, 160)), SHORT, title_at_bottom=True))
    assert round(inside_trim_mm(starring, PRINTERS["lulu"])["bottom"], 1) == 26.2
    assert round(inside_trim_mm(starring, PRINTERS["bookpod"])["bottom"], 1) == 14.3
    assert round(inside_trim_mm(title, PRINTERS["lulu"])["bottom"], 1) == 38.0
    assert title[1] - title[0] == 140 and (title[2], title[3]) == (361, 1706)  # the same face, size and centring as before


def test_the_back_cover_footer_prints_inside_the_margin():
    back = letter_back_cover(Image.new("RGB", (W, H), (90, 120, 160)), {"tagline": "", "blurb": "", "footer": LONG["footer"]})
    plain = letter_back_cover(Image.new("RGB", (W, H), (90, 120, 160)), {"tagline": "", "blurb": ""})
    assert not lettered_lines(plain)
    for line in lettered_lines(back):
        for printer in PRINTERS.values():
            mm = inside_trim_mm(line, printer)
            assert mm["bottom"] >= MARGIN_MM and mm["side"] >= MARGIN_MM


def test_the_head_limit_keeps_the_hair_inside_both_printers_top_margin():
    for printer in PRINTERS.values():
        assert inside_trim_mm((round(H * HEAD_SAFE_MIN), H, 0, W), printer)["top"] >= 13


def render(tmp_path, monkeypatch, heads, audit=None, rejected=None):
    """render_cover over fake draws whose check reports `heads` in turn; returns (image calls, title_at_bottom)."""
    answers = iter(heads)
    bottoms = []
    monkeypatch.setattr(cover_module, "letter_cover", lambda art, c, f, title_at_bottom: bottoms.append(title_at_bottom) or art)
    images = FakeImages([Image.new("RGB", (400, 600), c) for c in ("red", "green", "blue")])
    render_cover(CAST, {"scene": "Dana on the cliff", **SHORT}, (400, 600), tmp_path / "cover.png", images,
                 FakeVision(lambda p, i: {**CLEAN, "head_top": next(answers) * 1000}), audit=audit,
                 on_reject=(lambda *a, **k: rejected.append(a)) if rejected is not None else None)
    assert (tmp_path / "cover.png").exists()
    return images.calls, bottoms


def test_the_cover_brief_asks_for_setting_above_the_head(tmp_path, monkeypatch):
    calls, _ = render(tmp_path, monkeypatch, [0.3])
    assert len(calls) == 1
    assert "at least one eighth of the canvas height of that setting shows above the head" in calls[0]["prompt"]
    assert "title" not in calls[0]["prompt"].lower()  # naming it makes the model paint lettering


def test_a_head_in_the_top_margin_is_drawn_again_with_a_request_for_headroom(tmp_path, monkeypatch):
    audit, rejected = [], []
    calls, bottoms = render(tmp_path, monkeypatch, [0.048, 0.25], audit, rejected)  # BOOKS-45's hair began 4.8% down
    assert len(calls) == 2 and bottoms == [False]
    assert calls[1]["prompt"].startswith(REVISE_MARK) and HEADROOM_FIX in calls[1]["prompt"]
    assert [(r["accepted"], r.get("head_in_margin")) for r in audit] == [(False, True), (True, None)]
    assert rejected == []  # sound art: not recorded as a vision rejection


def test_a_head_just_below_the_margin_is_kept_without_another_draw(tmp_path, monkeypatch):
    calls, bottoms = render(tmp_path, monkeypatch, [0.09])
    assert len(calls) == 1 and bottoms == [True]  # the head would be under the top title block: the title moves to the bottom


# Real covers, 2026-11-13: both titles were lettered over the hero's legs with empty setting above heads at 17.6% and 19.1%.
TITLES = {"he": {"title": "מרדף בהרים", "starring": "בכיכוב דני"},  # two Hebrew words, no descenders
          "en": {"title": "Awakening Guardian", "starring": "Starring Danny", "footer": "For Danny, never stop running"},
          "short": SHORT, "long": LONG, "hebrew": HEBREW}


@pytest.mark.parametrize("cover", TITLES)
def test_the_top_block_is_measured_as_it_is_lettered(cover):
    lines = lettered_lines(letter_cover(Image.new("RGB", (W, H), (90, 120, 160)), {**TITLES[cover], "footer": ""}))
    end = top_block_end((W, H), TITLES[cover])
    assert lines[0][0] >= int(H * SAFE_TOP) and abs(lines[-1][1] - end * H) <= 2  # the last line's lowest lettered row
    assert 0.11 < end < 0.17  # the old fixed limit of 20% left 3% to 8% of the height unused under the block


def test_the_real_titles_need_thirteen_and_fifteen_percent_of_the_height():
    # 0.131 and 0.154 on the real covers; 0.6% more since SAFE_TOP moved from 0.064 to 0.07 (print_safe.CoverSafe)
    assert round(top_block_end((W, H), TITLES["he"]), 3) == 0.137 and round(top_block_end((W, H), TITLES["en"]), 3) == 0.16
    assert top_block_end((W, H), {}) == int(H * SAFE_TOP) / H  # nothing to letter at the top: only the margin
    assert top_block_end((W, H), {"title": "Go"}) < top_block_end((W, H), TITLES["he"])  # no starring line: a shorter block


@pytest.mark.parametrize("head, bottom", [(0.10, True), (0.13, True), (0.18, False), (0.25, False)])
@pytest.mark.parametrize("cover", TITLES)
def test_the_title_stays_at_the_top_when_the_head_starts_below_its_block(tmp_path, monkeypatch, head, bottom, cover):
    assert title_goes_bottom(head, (W, H), TITLES[cover]) is bottom
    bottoms = []
    monkeypatch.setattr(cover_module, "letter_cover", lambda art, c, f, title_at_bottom, **k: bottoms.append(title_at_bottom) or art)
    render_cover(CAST, {"scene": "Dana on the cliff", **TITLES[cover]}, (W // 4, H // 4), tmp_path / "cover.png",
                 FakeImages([Image.new("RGB", (W // 4, H // 4), "red")]), FakeVision(lambda p, i: {**CLEAN, "head_top": head * 1000}))
    assert bottoms == [bottom]


def test_the_title_moves_only_when_the_head_would_touch_its_block():
    for cover in TITLES.values():
        limit = top_block_end((W, H), cover) + HEAD_GAP  # one lettering gap between the starring line and the hair
        assert top_title_shrink(limit, (W, H), cover, gap=HEAD_GAP) == 1.0  # the title as it is
        assert MIN_TITLE_SHRINK <= top_title_shrink(limit - 0.001, (W, H), cover, gap=HEAD_GAP) < 1  # a little smaller, still at the top
        lowest = top_block_end((W, H), cover, title_shrink=MIN_TITLE_SHRINK) + HEAD_GAP  # the block with the smallest title
        assert title_goes_bottom(lowest - 0.001, (W, H), cover) and not title_goes_bottom(lowest, (W, H), cover)
    assert round(top_block_end((W, H), TITLES["he"]) + HEAD_GAP, 3) == 0.157  # the Hebrew cover's head, 0.176, clears it
    assert round(top_block_end((W, H), TITLES["en"]) + HEAD_GAP, 3) == 0.18  # the English cover's head, 0.191, clears it


def test_a_head_in_the_margin_on_every_draw_never_loses_the_cover(tmp_path, monkeypatch):
    audit = []
    calls, bottoms = render(tmp_path, monkeypatch, [0.04, 0.05, 0.06], audit)
    assert len(calls) == 3 and bottoms == [True]
    assert [r.get("fallback") for r in audit] == [None, None, True]  # the last draw is kept


# The Books app's strictest cover box (print_safe.APP_COVER_INSETS_PX: left, right, top, bottom px of the 2063 x 3150 art).
APP_BOX = (219, 219, 200, 246)
STAMP_COLOURS = {"logo": (15, 118, 110), "barcode": (250, 240, 200)}
BLURB = {"tagline": "The storm is only the beginning",
         "blurb": "When the old lighthouse goes dark, Maya and her grandfather follow a trail of strange lights along "
                  "the cliffs, through the drowned village and into the caves beneath the sea, where something has been "
                  "waiting for a hundred years.",
         "footer": "For my dearest grandfather, with all the love in the world, from all of us at home"}
HE_BLURB = {"tagline": "הסערה היא רק ההתחלה",
            "blurb": "כשהמגדלור הישן כבה, מאיה וסבא שלה יוצאים בעקבות אורות מוזרים לאורך הצוקים, דרך הכפר הטבוע ואל "
                     "המערות שמתחת לים, שם משהו מחכה כבר מאה שנה.", "footer": "בשביל סבא, באהבה"}
LONG_BLURB = {**BLURB, "blurb": " ".join([BLURB["blurb"]] * 6)}  # runs to the smallest blurb face


def changed_box(before, after):
    """(top, bottom, left, right) of every pixel the lettering changed, as lettered_lines gives a line."""
    ys, xs = np.where(np.any(np.asarray(before.convert("RGB")) != np.asarray(after), axis=2))
    return int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1


def inside_app_box(box_px):
    x, y, w, h = box_px
    return x >= APP_BOX[0] and x + w <= W - APP_BOX[1] and y >= APP_BOX[2] and y + h <= H - APP_BOX[3]


@pytest.fixture
def stamp_files(tmp_path):
    Image.new("RGB", (600, 470), STAMP_COLOURS["logo"]).save(tmp_path / "logo.png")
    Image.new("RGB", (520, 1060), STAMP_COLOURS["barcode"]).save(tmp_path / "barcode.png")
    return [{"path": str(tmp_path / "logo.png"), "corner": "right", "width": 0.14, "kind": "logo"},
            {"path": str(tmp_path / "barcode.png"), "corner": "left", "width": 0.12, "kind": "barcode"}]


@pytest.mark.parametrize("printer", PRINTERS)
@pytest.mark.parametrize("back", [BLURB, HE_BLURB, LONG_BLURB], ids=["en", "he", "long"])
def test_the_back_cover_blurb_panel_and_stamps_print_inside_the_margin(printer, back, stamp_files):
    """BOOKS-48: the blurb panel's edge printed 0.495 in inside Lulu's trim (80% wide); at 78% it is 14.4 mm."""
    plain = Image.new("RGB", (W, H), (90, 120, 160))
    report = []
    lettered = letter_back_cover(plain, back, stamps=stamp_files, report=report)
    kinds = [b["kind"] for b in report]
    assert kinds == ["blurb", "footer", "footer", "logo", "barcode"] or kinds == ["blurb", "footer", "logo", "barcode"]
    for box in report:
        assert box["page"] == "back" and inside_app_box(box["box_px"]), box
        x, y, w, h = box["box_px"]
        mm = inside_trim_mm((y, y + h, x, x + w), PRINTERS[printer])
        assert min(mm.values()) >= MARGIN_MM, box
    # Every changed pixel, the panel's shade and the lines' soft shadows too, against the printer's own margin plus
    # 1 mm (Lulu 12.7 mm, BookPod 5 mm): the footer's shadow reaches 17 px under its line, 12.9 mm inside BookPod's trim.
    own = (12.7 if printer == "lulu" else 5) + 1
    assert min(inside_trim_mm(changed_box(plain, lettered), PRINTERS[printer]).values()) >= own
    for kind, colour in STAMP_COLOURS.items():  # the stamps are where the report says
        ys, xs = np.where(np.all(np.asarray(lettered) == colour, axis=2))
        box = next(b["box_px"] for b in report if b["kind"] == kind)
        assert (int(xs.min()), int(ys.min()), int(xs.max()) - int(xs.min()) + 1, int(ys.max()) - int(ys.min()) + 1) == tuple(box)


# Four lines and more: the title (one line, however long), a starring line and a footer that each wrap to two.
BLOCK = {"title": "The Truly Extraordinary and Completely Unbelievable Summer Adventure of Grandpa Maximilian",
         "starring": LONG["starring"], "footer": LONG["footer"]}
HE_BLOCK = {"title": "ההרפתקה המופלאה והבלתי נשכחת של סבא מקסימיליאן והכלב שלו בקיץ של שנת אלפיים", "starring": "בכיכוב דנה, נועה, "
            "יואב, מאיה, עומר ודני מהשכונה הישנה ליד הים", "footer": "בשביל סבא, באהבה גדולה מכל המשפחה שלנו בבית ומכל החברים"}


@pytest.mark.parametrize("printer", PRINTERS)
@pytest.mark.parametrize("at_bottom", [True, False], ids=["bottom", "top"])
@pytest.mark.parametrize("cover", [BLOCK, HE_BLOCK], ids=["en", "he"])
def test_a_tall_front_block_prints_inside_the_margin_and_is_reported(printer, at_bottom, cover):
    report = []
    lettered = letter_cover(Image.new("RGB", (W, H), (90, 120, 160)), cover, title_at_bottom=at_bottom, report=report)
    lines = lettered_lines(lettered)
    assert len(lines) >= 4
    for line in lines:
        mm = inside_trim_mm(line, PRINTERS[printer])
        assert mm["bottom"] >= MARGIN_MM and mm["side"] >= MARGIN_MM
        assert mm["top"] >= (MARGIN_MM + 1 if printer == "lulu" else 5 + 1)
    assert sorted(b["kind"] for b in report) == ["footer", "subtitle", "title"]
    for box in report:
        assert box["page"] == "front" and inside_app_box(box["box_px"]), box
    for top, bottom, left, right in lines:  # every white line lies in a reported box
        assert any(b["box_px"][0] <= left and right <= b["box_px"][0] + b["box_px"][2] + 1 and
                   b["box_px"][1] <= top + 1 and bottom <= b["box_px"][1] + b["box_px"][3] + 1 for b in report)


def test_render_cover_and_render_back_cover_report_their_boxes(tmp_path):
    from book_comic.back_cover import render_back_cover
    front, back = [], []
    vision = FakeVision(lambda p, i: {**CLEAN, "head_top": 400, "figure_visible": False})
    render_cover(CAST, {"scene": "Dana on the cliff", **SHORT}, (W, H), tmp_path / "cover.png",
                 FakeImages([Image.new("RGB", (W, H), (90, 120, 160))]), vision, lettering_boxes=front)
    render_back_cover(CAST, {"scene": "The cliff at dusk", **BLURB}, (W, H), tmp_path / "back.png",
                      FakeImages([Image.new("RGB", (W, H), (90, 120, 160))]), vision, lettering_boxes=back)
    assert [b["kind"] for b in front] == ["title", "subtitle"] and all(inside_app_box(b["box_px"]) for b in front)
    assert [b["kind"] for b in back][:2] == ["blurb", "footer"] and all(inside_app_box(b["box_px"]) for b in back)
