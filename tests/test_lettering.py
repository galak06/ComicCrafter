"""Bubbles, captions, notes, fonts and page layout, drawn for real (no network)."""

import numpy as np
from PIL import Image

from layout.bubble_planner import BubblePlan
from layout.bubble_shapes import BUBBLE_KINDS
from layout.captions import draw_note
from layout.comic_bubbles import _font, draw_speech_bubble, render_dialogue
from layout.lettering import LETTERING_FONT
from layout.panel_layout import LayoutManager, LayoutType
from book_comic.render import PRINT_PAGE_SIZE


def test_the_page_gutters_between_panels_are_identical():
    for manager in (LayoutManager(), LayoutManager(page_width=PRINT_PAGE_SIZE[0], page_height=PRINT_PAGE_SIZE[1])):
        layout = manager.create_layout(LayoutType.VERTICAL_STRIP, num_panels=3)
        gaps = [below.y - (above.y + above.height) for above, below in zip(layout, layout[1:])]
        assert len(set(gaps)) == 1 and gaps[0] > 0
        assert len({(panel.x, panel.width) for panel in layout}) == 1  # full-width rows, read top to bottom


def test_print_page_size_is_6_875_by_10_5_inches_at_300_dpi():
    assert PRINT_PAGE_SIZE == (2063, 3150)


def test_every_bubble_kind_draws_its_own_shape_and_keeps_clear():
    drawn = {}
    for kind in BUBBLE_KINDS + ("unknown",):
        panel, placed = Image.new("RGB", (700, 420), (196, 214, 226)), [(0, 0, 700, 60)]
        draw_speech_bubble(panel, "שלום, מה שלומך?", (0.4, 0.3), (0.7, 0.7), placed, kind)
        assert len(placed) == 2  # its box is reserved for the next bubble
        assert placed[1][1] >= 60  # never over an earlier box (the caption band here)
        drawn[kind] = np.asarray(panel)
    assert (drawn["unknown"] == drawn["speech"]).all()  # an unknown kind is a plain speech bubble
    assert len({drawn[kind].tobytes() for kind in BUBBLE_KINDS}) == len(BUBBLE_KINDS)


def test_render_dialogue_draws_each_lines_kind():
    plan = BubblePlan(speakers=[(0.7, 0.7)], bubbles=[(0.4, 0.3)])
    art = Image.new("RGB", (700, 420), "white")
    speech = np.asarray(render_dialogue(art, ["Hi there"], "", plan))
    shout = np.asarray(render_dialogue(art, ["Hi there"], "", plan, kinds=["shout"]))
    assert not (speech == shout).all()


def test_a_latin_name_in_hebrew_lettering_is_drawn_not_boxes():
    assert LETTERING_FONT.is_file()
    font = _font(48, "המדדים הכינו את zovek למראה")
    glyph = lambda text: bytes(font.getmask(text))  # noqa: E731
    missing = glyph("")  # a code point no font maps: the empty box
    for letter in "zovek":
        assert glyph(letter) != missing
    assert glyph("ש") != missing


def test_a_font_path_setting_replaces_the_default_faces():
    font = _font(30, "hello", font_path=str(LETTERING_FONT))
    assert font.getname()[0] == "Assistant"
    assert _font(30, "hello", font_path="/missing/font.ttf") is not None  # falls back, never raises


def test_a_caption_moved_to_the_later_corner_keeps_the_bubble_below_it():
    art = Image.new("RGB", (800, 500), "white")
    # The speaker's head sits under the top-right corner, so the RTL caption moves top-left, and the
    # planner asked for the bubble at the top right: reading order puts it below the caption.
    plan = BubblePlan(speakers=[(0.85, 0.2)], bubbles=[(0.85, 0.08)])
    lettered = render_dialogue(art, ["שלום!"], "הקריינות נקראת לפני הבועה.", plan)
    ink = np.asarray(lettered.convert("L")) < 128
    bubble_rows = np.where(ink[:, 420:].any(axis=1))[0]
    caption_rows = np.where(ink[:, :380].any(axis=1))[0]
    assert len(bubble_rows) and len(caption_rows)
    assert bubble_rows.min() > caption_rows.max() - 2


def test_the_caption_starts_in_the_reading_first_corner_whatever_the_model_picked():
    art = Image.new("RGB", (800, 500), "white")
    plan = BubblePlan(speakers=[], bubbles=[], caption_corner="top-left")
    ink = np.asarray(render_dialogue(art, [], "בוקר שקט בסדנה.", plan).convert("L")) < 128
    assert ink[:, 400:].any() and not ink[:, :400].any()  # Hebrew: top-right
    plan.caption_corner = "top-right"
    ink = np.asarray(render_dialogue(art, [], "A quiet morning.", plan).convert("L")) < 128
    assert ink[:, :400].any() and not ink[:, 400:].any()  # left-to-right: top-left


def test_a_note_goes_in_the_last_read_bottom_corner():
    art = Image.new("RGB", (800, 500), "white")
    assert draw_note(art, "") is art
    rtl = np.asarray(draw_note(art, "באהבה מסבתא").convert("L")) < 128
    assert rtl[250:, :400].any() and not rtl[:250].any() and not rtl[:, 400:].any()
    ltr = np.asarray(draw_note(art, "With love").convert("L")) < 128
    assert ltr[250:, 400:].any() and not ltr[:, :400].any()
