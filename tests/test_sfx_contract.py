"""The "sfx" contract: prompts, vision calls, sfx-only panels and splashes (drawing: test_sound_effects.py)."""

import hashlib
import json

import pytest
from PIL import Image

from book_comic.image_prompts import panel_prompt
from book_comic.render import PageRenderer, RenderOptions, print_layouts
from conftest import FakeImages, FakeVision
from layout.bubble_planner import SFX_REQUEST, _prompt, plan_bubbles
from layout.sound_effects import sfx_layer
from test_sound_effects import CAST, PLAN, PROTECTED, art, changed_box, renderer, sfx_entries


def test_without_sfx_the_planner_prompt_is_byte_identical_to_the_one_before_this_field():
    cases = [([("Dana (red coat)", "Hi there")], True, False, ()),
             ([("A", "x"), ("B", "שלום")], False, True, ("bottom-left",)), ([], False, False, ())]
    digests = [hashlib.sha256(_prompt(*case).encode()).hexdigest()[:16] for case in cases]
    assert digests == ["e57fd4067ec6fe14", "81379893dc971705", "afb70001912e7ef2"]  # measured at 753fbe8
    for case in cases:
        assert _prompt(*case, sfx="") == _prompt(*case)
        assert _prompt(*case, sfx="BOOM!") == _prompt(*case) + SFX_REQUEST.format(text="BOOM!")


def test_a_panel_with_only_a_sound_effect_is_lettered_with_one_planning_call():
    """Chosen: an sfx-only panel makes the one existing planning call (for the faces and the point), never a second."""
    r = renderer({"lines": [], "protected": PROTECTED, "sfx": [300, 300]})
    lettered = r._letter(art(), {"scene": "x", "sfx": "THUD"})
    (entry,) = sfx_entries(r)
    assert entry["placed"] and changed_box(art(), lettered) and len(r.vision.prompts) == 1
    assert SFX_REQUEST.format(text="THUD") in r.vision.prompts[0]
    quiet = renderer()  # nothing to letter: still no call at all
    assert quiet._letter(art(), {"scene": "x"}).tobytes() == art().tobytes() and quiet.vision.prompts == []


@pytest.mark.parametrize("answer", [{"lines": []}, {"lines": [], "protected": [[1, 2]]}, {"lines": "?"}, "garbage"])
def test_an_unusable_plan_for_a_sound_effect_alone_leaves_it_out_after_one_call(answer):
    vision = FakeVision(lambda p, i: answer)
    r = PageRenderer(CAST, FakeImages([art()]), vision, None, RenderOptions())
    assert r._letter(art(), {"scene": "x", "sfx": "THUD"}).tobytes() == art().tobytes()  # faces unknown: not risked
    assert [(e["placed"], e["reason"]) for e in sfx_entries(r)] == [(False, "no_plan")]
    assert len(vision.prompts) == 1 and r.lettering_checks == set()


def test_a_splash_takes_one_bubble_and_a_sound_effect(tmp_path):
    splash = {"scene": "Wide shot: Dana stands on the cliff at dawn.", "characters": ["Dana"],
              "caption": "The city still slept.", "dialogue": [{"speaker": "Dana", "text": "Here it begins!"}], "sfx": "BOOM!"}
    answer = {"lines": [{"mouth": [500, 600], "bubble": [500, 880]}], "protected": [[400, 450, 200, 250]], "sfx": [250, 500]}
    r = renderer(answer, layouts=print_layouts())
    plain = renderer(answer, layouts=print_layouts())
    page = r.render_page([splash], tmp_path / "page.png")
    plain.render_page([{k: v for k, v in splash.items() if k != "sfx"}], tmp_path / "plain.png")
    (entry,) = sfx_entries(r)
    assert entry["placed"] and entry["panel"] == 1
    assert changed_box(Image.open(page), Image.open(tmp_path / "plain.png"))
    strip_height = print_layouts().create_layout(print_layouts().auto_layout(3), num_panels=3)[0].get_content_area()[3]
    top_size = sfx_layer("BOOM!", int(max(16, int(strip_height * 0.05)) * 1.6)).size
    assert tuple(entry["box"][2:]) == top_size  # sized like a strip panel's, as the splash's other lettering is
    with pytest.raises(ValueError, match="comic_splash_lettering"):  # the one-bubble rule is unchanged
        r.render_page([{**splash, "dialogue": splash["dialogue"] * 2}], tmp_path / "two.png")


def test_the_image_model_and_the_art_check_never_hear_about_the_sound_effect(tmp_path):
    panels = [{"scene": f"Wide shot: Dana at the mine, {n}.", "characters": ["Dana"], "caption": "Night fell.",
               "dialogue": [{"speaker": "Dana", "text": "Listen!"}]} for n in "abc"]
    loud = [{**panel, "sfx": "PRIVATE_KABOOM"} for panel in panels]
    runs = []
    for number, script in enumerate((panels, loud)):
        r = renderer(layouts=print_layouts(), check_art=True, sheet_path=tmp_path / f"sheet{number}.png")
        r.render_page(script, tmp_path / f"page{number}.png")
        runs.append(r)
    quiet, noisy = runs
    assert noisy.images.calls == quiet.images.calls and len(quiet.images.calls) == 4  # the sheet and three panels
    assert not any("KABOOM" in json.dumps(call) for call in noisy.images.calls)
    planning = [p for p in noisy.vision.prompts if "KABOOM" in p]
    assert len(planning) == 3 and all(p.startswith("This is a comic book panel. Speech bubbles") for p in planning)
    assert [p for p in noisy.vision.prompts if "KABOOM" not in p] == [p for p in quiet.vision.prompts if "Speech bubbles" not in p]
    assert len(noisy.vision.prompts) == len(quiet.vision.prompts)  # not one more vision call
    for panel in ({"scene": "Close-up: a door slams."}, panels[0]):
        assert panel_prompt(CAST, {**panel, "sfx": "PRIVATE_KABOOM"}, "Dana: red coat") == panel_prompt(CAST, panel, "Dana: red coat")


def test_the_planner_parses_the_optional_point_tolerantly():
    def planned(value, ask="BOOM!"):
        vision = FakeVision(lambda p, i: {**PLAN, **({} if value == "absent" else {"sfx": value})})
        return plan_bubbles(art(), [("Dana", "Hi")], False, vision=vision, sfx=ask)

    assert planned([250, 750]).sfx == (0.25, 0.75)
    for bad in ("absent", None, "left", [1], [1, "a"], [5000, 2], [-1, 5], [True, 3], [float("nan"), 3], {"x": 1}, 7):
        plan = planned(bad)
        assert plan is not None and plan.sfx is None and plan.protected_checked  # the plan itself is never spoiled
    assert planned([250, 750], ask="").sfx is None  # not asked for: ignored
