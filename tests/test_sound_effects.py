"""The optional panel field "sfx": a sound effect lettered by the engine over the finished art, never by the image model."""

import json
import math

import pytest
from PIL import Image, ImageChops, ImageDraw

import book_comic.sfx as sfx_module
from book_comic.render import PageRenderer, RenderOptions, print_layouts
from conftest import FakeImages, FakeVision
from layout.bubble_planner import plan_bubbles
from layout.captions import draw_note
from layout.comic_bubbles import _subjects, render_dialogue
from layout.lettering import LETTERING_FONT, overlap_area
from layout.sound_effects import (MAX_CHARS, MAX_HEIGHT, MAX_WIDTH, SFX_FONT, SIZE_STEPS, draw_sfx, lettering_ink,
                                  sfx_font, sfx_layer, sfx_text)

SIZE = (918, 472)  # a print strip panel at half size
CAST = {"style": "comic", "language": "en", "characters": [{"name_en": "Dana", "name": "דנה", "look": "red coat"}]}
CLEAN = {"head_top": 500, "has_text": False, "bad_anatomy": False, "identity_mismatch": False,
         "design_mismatch": False, "scene_mismatch": False}
PROTECTED = [[455, 310, 90, 190], [700, 580, 110, 250]]
PLAN = {"lines": [{"mouth": [498, 440], "bubble": [330, 300]}], "protected": PROTECTED}
PANEL = {"scene": "Wide shot: Dana by the old mine.", "characters": ["Dana"],
         "caption": "The old mine had been silent for forty years.",
         "dialogue": [{"speaker": "Dana", "text": "Did you hear that?"}], "note": "For Dana"}
HEBREW = {**PANEL, "caption": "המכרה הישן שתק ארבעים שנה.", "dialogue": [{"speaker": "Dana", "text": "שמעת את זה?"}],
          "note": "לדנה באהבה"}
SFX = {"en": "KRRRK!", "he": "בום!"}


def art(size=SIZE):
    return Image.new("RGB", size, "skyblue")


def renderer(answer=None, language="en", layouts=None, **options):
    vision = FakeVision(lambda p, i: {**CLEAN, **(PLAN if answer is None else answer)})
    return PageRenderer({**CAST, "language": language}, FakeImages([art((1024, 512))]), vision, layouts, RenderOptions(**options))


def sfx_entries(r):
    return [entry for entry in r.audit if entry.get("kind") == "sfx"]


def changed_box(before, after):
    return ImageChops.difference(before.convert("RGB"), after.convert("RGB")).getbbox()


@pytest.mark.parametrize("value", ["absent", "", "   ", None, 7, ["BOOM"]])
def test_a_panel_without_a_sound_effect_is_lettered_exactly_as_before(value):
    panel = dict(PANEL) if value == "absent" else {**PANEL, "sfx": value}
    r = renderer()
    lettered = r._letter(art(), panel)
    plan = plan_bubbles(art(), [("Dana (red coat)", "Did you hear that?")], True, False, vision=renderer().vision,
                        reserved_corners=["bottom-right"])
    # The same picture as the unchanged lettering functions draw when called directly, as _letter did before
    by_hand = draw_note(render_dialogue(art(), ["Did you hear that?"], PANEL["caption"], plan, kinds=["speech"], rtl=False,
                                        reserved=[changed_note_box(lettered)]), "For Dana", rtl=False)
    assert lettered.tobytes() == by_hand.tobytes()
    assert sfx_entries(r) == [] and len(r.vision.prompts) == 1 and "sound effect" not in r.vision.prompts[0]


def changed_note_box(lettered):
    """The note's rectangle (bottom-right corner), read back from a lettered panel."""
    w, h = lettered.size
    left, top, right, bottom = changed_box(art().crop((w // 2, h // 2, w, h)), lettered.crop((w // 2, h // 2, w, h)))
    return (w // 2 + left, h // 2 + top, right - left, bottom - top)


@pytest.mark.parametrize("language", ["en", "he"])
def test_a_sound_effect_is_drawn_inside_its_box_and_nowhere_else(language, monkeypatch):
    directions = []
    original = ImageDraw.ImageDraw.text
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", lambda self, *a, **k: (directions.append(k.get("direction")), original(self, *a, **k))[1])
    panel = PANEL if language == "en" else HEBREW
    plain = renderer(language=language)._letter(art(), panel)
    directions.clear()
    r = renderer({**PLAN, "sfx": [760, 300]}, language)
    lettered = r._letter(art(), {**panel, "sfx": SFX[language]})

    (entry,) = sfx_entries(r)
    x, y, w, h = entry["box"]
    assert entry == {"accepted": True, "kind": "sfx", "panel": None, "placed": True, "reason": None, "box": [x, y, w, h],
                     "requirements": [], "checks": {}} and json.dumps(r.audit)
    assert 0 <= x and 0 <= y and x + w <= SIZE[0] and y + h <= SIZE[1]
    left, top, right, bottom = changed_box(plain, lettered)  # the only pixels that differ from the panel without it
    assert x <= left and y <= top and right <= x + w and bottom <= y + h
    assert (right - left, bottom - top) == (w, h)  # the box is the tilted word's own bounding box
    # Hebrew goes through raqm as right-to-left; the word is one shaped string, never drawn letter by letter
    assert [d for d in directions if d] == ["rtl" if language == "he" else "ltr"]
    assert r._letter(art(), {**panel, "sfx": SFX[language]}).tobytes() == lettered.tobytes()  # no randomness


def test_hebrew_reads_right_to_left_and_the_word_is_tilted_as_one_piece():
    upright = Image.new("RGBA", (400, 120), (0, 0, 0, 0))
    font = sfx_font(40, "בום!")
    ImageDraw.Draw(upright).text((20, 20), "בום!", font=font, fill="white", direction="rtl")
    mark = Image.new("RGBA", (400, 120), (0, 0, 0, 0))
    ImageDraw.Draw(mark).text((20, 20), "!", font=font, fill="white")
    # The exclamation mark ends the word, so in Hebrew it is the leftmost glyph: its ink starts where the word's does.
    assert upright.getbbox()[0] == mark.getbbox()[0]
    hebrew, latin = sfx_layer("בום!", 40), sfx_layer("BOOM!", 40)
    for layer, rising_side in ((latin, "right"), (hebrew, "left")):  # each rises the way it is read
        alpha = layer.getchannel("A")
        third = layer.width // 3
        tops = {"left": alpha.crop((0, 0, third, layer.height)).getbbox()[1],
                "right": alpha.crop((layer.width - third, 0, layer.width, layer.height)).getbbox()[1]}
        assert tops[rising_side] < tops["left" if rising_side == "right" else "right"]
        assert layer.getbbox() == (0, 0, *layer.size)  # cropped to its ink: nothing of the rotation is cut off


def test_without_raqm_direction_the_word_is_still_drawn(monkeypatch):
    original = ImageDraw.ImageDraw.textbbox

    def no_raqm(self, *args, **kwargs):
        if "direction" in kwargs:
            raise KeyError("setting text direction, language or font features is not supported without libraqm")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "textbbox", no_raqm)
    panel = art()
    box, reason = draw_sfx(panel, "בום!", (0.5, 0.5), [])
    assert box and reason is None and changed_box(art(), panel)


def test_a_missing_glyph_falls_back_to_the_lettering_font():
    assert sfx_font(40, "KRRRK! בום!").path == str(SFX_FONT)
    assert sfx_font(40, "爆", str(LETTERING_FONT)).path != str(SFX_FONT)
    assert draw_sfx(art(), "爆", None, [])[1] is None  # still drawn (as the lettering font draws it), never an error


@pytest.mark.parametrize("language, point", [("en", [498, 400]), ("he", [498, 400]), ("en", None), ("he", None)])
def test_the_sound_effect_keeps_off_heads_protected_subjects_caption_bubbles_and_note(language, point):
    panel = PANEL if language == "en" else HEBREW
    answer = {**PLAN, **({"sfx": point} if point else {})}
    if language == "he":
        answer["lines"] = [{"mouth": [498, 440], "bubble": [680, 300]}]
    plain = renderer(answer, language)._letter(art(), panel)
    r = renderer(answer, language)
    lettered = r._letter(art(), {**panel, "sfx": SFX[language]})
    box = tuple(sfx_entries(r)[0]["box"])

    plan = plan_bubbles(art(), [("Dana", "x")], True, language == "he", vision=renderer(answer).vision)
    assert len(_subjects(plan, SIZE)) == 3  # the speaker's head and both protected rectangles
    assert all(overlap_area(box, subject) == 0 for subject in _subjects(plan, SIZE))
    ink = lettering_ink(art(), plain)  # caption, bubble with its tail, note
    assert ink.getbbox() and ink.crop((box[0], box[1], box[0] + box[2], box[1] + box[3])).getbbox() is None
    centre = (box[0] + box[2] / 2, box[1] + box[3] / 2)
    if point:  # the planner's point is on the speaker's head: the nearest free spot beside it is taken
        assert math.hypot(centre[0] - 0.498 * SIZE[0], centre[1] - 0.4 * SIZE[1]) < 0.25 * SIZE[0]
    else:  # no point: the upper corner read last (the caption has the one read first)
        assert centre[1] < SIZE[1] * 0.3
        assert centre[0] < SIZE[0] * 0.3 if language == "he" else centre[0] > SIZE[0] * 0.7


def test_a_free_planner_point_is_used_as_the_centre():
    panel = art()
    (x, y, w, h), _ = draw_sfx(panel, "BOOM!", (0.6, 0.7), [(0, 0, 200, 200)])
    assert abs(x + w / 2 - 0.6 * SIZE[0]) <= SIZE[0] // 60 and abs(y + h / 2 - 0.7 * SIZE[1]) <= SIZE[1] // 40


@pytest.mark.parametrize("near", [None, (2, 2), ("a", "b"), (float("nan"), 0.5), (0.5,), 3])
def test_an_unusable_point_starts_from_the_upper_reading_end_corner(near):
    edge = max(8, SIZE[1] // 40)
    (x, y, w, h), _ = draw_sfx(art(), "BOOM!", near, [], rtl=False)
    assert (x + w, y) == (pytest.approx(SIZE[0] - edge, abs=SIZE[0] // 60), edge)
    (x, y, w, h), _ = draw_sfx(art(), "BOOM!", near, [], rtl=True)
    assert (x, y) == (edge, edge)


def test_with_no_room_the_sound_effect_is_dropped_and_the_page_is_still_rendered(tmp_path):
    crowded = {"lines": [], "protected": [[0, 0, 1000, 1000]]}
    r = renderer(crowded)
    panel = art()
    assert draw_sfx(panel, "BOOM!", (0.5, 0.5), [(0, 0, *SIZE)]) == (None, "no_space") and changed_box(art(), panel) is None
    assert r._letter(art(), {"scene": "x", "sfx": "BOOM!"}).tobytes() == art().tobytes()
    assert sfx_entries(r) == [{"accepted": True, "kind": "sfx", "panel": None, "placed": False, "reason": "no_space",
                               "box": None, "requirements": [], "checks": {}}]
    assert r.lettering_checks == set() and len(r.vision.prompts) == 1

    r = renderer(crowded, layouts=print_layouts())
    page = r.render_page([{"scene": f"Wide shot: {n}", "sfx": "BOOM!"} for n in "abc"], tmp_path / "page.png")
    assert page.exists() and [(e["panel"], e["placed"], e["reason"]) for e in sfx_entries(r)] == [
        (1, False, "no_space"), (2, False, "no_space"), (3, False, "no_space")]
    r.current_stage = "lettering"
    assert r.failure_diagnostic() == {"stage": "lettering", "panel": 3, "failedChecks": [], "uncheckedChecks": []}


@pytest.mark.parametrize("error", [RuntimeError("font"), ValueError("comic_lettering_no_space"), OSError("no font")])
def test_any_failure_drops_the_sound_effect_without_a_second_planning_pass(monkeypatch, error):
    def broken(*args, **kwargs):
        raise error

    plain = renderer()._letter(art(), PANEL)
    monkeypatch.setattr(sfx_module, "draw_sfx", broken)
    r = renderer()
    lettered = r._letter(art(), {**PANEL, "sfx": "BOOM!"})
    assert lettered.tobytes() == plain.tobytes()
    assert [(e["placed"], e["reason"]) for e in sfx_entries(r)] == [(False, "error")]
    assert len(r.vision.prompts) == 1 and r.lettering_checks == set()  # no precise pass, no failure diagnostic


def test_the_size_starts_at_1_6_of_the_dialogue_type_and_shrinks_to_fit_the_cap():
    base = max(16, int(SIZE[1] * 0.05))
    widths = {step: sfx_layer("KRRRAAASH!", int(base * step)).size for step in SIZE_STEPS}
    (_, _, w, h), _ = draw_sfx(art(), "KRRRAAASH!", None, [])
    assert (w, h) == widths[1.6] and w <= SIZE[0] * MAX_WIDTH and h <= SIZE[1] * MAX_HEIGHT

    narrow = (int(widths[1.15][0] / MAX_WIDTH) + 1, SIZE[1])  # 1.15 just fits 45% of this width; 1.3 does not
    (_, _, w, h), _ = draw_sfx(art(narrow), "KRRRAAASH!", None, [])
    assert (w, h) == widths[1.15] and w <= narrow[0] * MAX_WIDTH

    floor = (int(widths[1.0][0] / MAX_WIDTH) + 1, SIZE[1])
    assert draw_sfx(art(floor), "KRRRAAASH!", None, [])[0][2:] == widths[1.0]
    too_narrow = (int(widths[1.0][0] / MAX_WIDTH) - 2, SIZE[1])  # below the dialogue size it is dropped, never shrunk
    assert draw_sfx(art(too_narrow), "KRRRAAASH!", None, []) == (None, "too_big")
    # type_height sizes it like the bubbles: a splash letters at the strip panel's size
    assert draw_sfx(art((918, 1416)), "KRRRAAASH!", None, [], type_height=SIZE[1])[0][2:] == widths[1.6]


def test_a_tight_spot_takes_a_smaller_size_before_giving_up():
    base = max(16, int(SIZE[1] * 0.05))
    big, small = sfx_layer("BOOM!", int(base * 1.6)).size, sfx_layer("BOOM!", base).size
    gap, edge = max(6, SIZE[1] // 80), max(8, SIZE[1] // 40)
    free_w, free_h = small[0] + 2 * gap + 16, small[1] + 2 * gap + 12  # room for the floor size only
    assert free_w < big[0] + 2 * gap
    obstacles = [(edge + free_w, 0, SIZE[0], SIZE[1]), (0, edge + free_h, SIZE[0], SIZE[1])]
    box, reason = draw_sfx(art(), "BOOM!", (0.5, 0.5), obstacles)
    assert reason is None and box[2] < big[0] and all(overlap_area(box, o) == 0 for o in obstacles)


def test_long_text_is_drawn_only_when_it_fits_and_never_wrapped():
    assert sfx_text("  KRRRK!\n  BOOM! ") == "KRRRK! BOOM!" and sfx_text(None) == "" and sfx_text(3) == ""
    assert draw_sfx(art(), "   ", None, []) == (None, "empty")
    long_text = "RUMBLE RUMBLE RUMBLE!"  # over 16 characters: fits only below the top size, on one line
    (_, _, w, h), _ = draw_sfx(art(), long_text, None, [])
    assert w <= SIZE[0] * MAX_WIDTH and h <= SIZE[1] * MAX_HEIGHT and h < sfx_layer("RUMBLE!", 36).height * 2.2
    assert draw_sfx(art(), "RUMBLE RUMBLE RUMBLE RUMBLE RUMBLE!", None, []) == (None, "too_big")
    assert draw_sfx(art(), "A" * (MAX_CHARS + 1), None, []) == (None, "too_long")
    r = renderer()
    assert r._letter(art(), {**PANEL, "sfx": "A" * 60}).tobytes() == renderer()._letter(art(), PANEL).tobytes()
    assert sfx_entries(r)[0]["reason"] == "too_long"
