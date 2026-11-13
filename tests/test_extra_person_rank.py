"""The least-bad pick: a person who should not be in the picture ranks below any staging miss."""

import pytest
from PIL import Image

from book_comic.art_check import draw_checked, inspect_art
from book_comic.best_draw import hard_defect, pick_fallback
from book_comic.staging_tolerance import EXTRA_PERSON_NOTE
from conftest import FakeImages, FakeVision

RED, GREEN, BLUE = (255, 0, 0), (0, 128, 0), (0, 0, 255)
BASE = {"has_text": False, "bad_anatomy": False, "identity_mismatch": False, "design_mismatch": False, "scene_mismatch": False,
        "head_top": 400}
DRAWER = [{"subject": "drawer", "attribute": "state", "expected": "open"}]
# A small staging miss: the drawer is drawn closed, and the checker says so twice (scene and requirement row).
STAGING_MISS = {"scene_mismatch": True, "requirement_mismatch": True, "corrections": ["Draw the drawer open."],
                "requirement_checks": [{"index": 0, "observed": "closed", "matches": False}]}
EXTRA_PERSON = {"scene_mismatch": True, "extra_person": True, "corrections": ["Only the hero belongs in this room."],
                "requirement_checks": [{"index": 0, "observed": "open", "matches": True}]}


def colours(*names):
    return [Image.new("RGB", (10, 10), n) for n in names]


def judge(by_colour):
    return FakeVision(lambda p, i: {**BASE, **by_colour.get(i.getpixel((0, 0)), {})})


def test_an_extra_person_ranks_below_a_staging_miss_with_more_failed_checks():
    # Before: the extra person failed one flag and no row, the staging miss two flags and a row, so the stranger won.
    rejected = [(None, STAGING_MISS), (None, EXTRA_PERSON)]
    assert pick_fallback(rejected, DRAWER) == 0
    assert pick_fallback(list(reversed(rejected)), DRAWER) == 1


def test_the_kept_draw_of_three_is_the_one_without_the_stranger():
    images = FakeImages(colours("red", "green", "blue"))
    vision = judge({RED: EXTRA_PERSON, GREEN: STAGING_MISS, BLUE: EXTRA_PERSON})
    audit = []
    art = draw_checked(images, vision, "Hero opens the drawer.", [], "2:3", requirements=DRAWER, audit=audit, fallback=True)
    assert art.getpixel((0, 0)) == GREEN
    assert [r["checks"].get("extra_person") for r in audit] == [True, None, True]


def test_a_tie_in_flags_no_longer_goes_to_a_later_draw_with_a_stranger():
    images = FakeImages(colours("red", "green", "blue"))
    miss = {"scene_mismatch": True, "corrections": ["Turn the hero toward the window."]}
    vision = judge({RED: miss, GREEN: miss, BLUE: {"scene_mismatch": True, "extra_person": True}})
    assert draw_checked(images, vision, "scene", [], "2:3", fallback=True).getpixel((0, 0)) == GREEN


def test_an_extra_person_is_ranked_not_hard_so_a_page_still_gets_a_picture():
    images = FakeImages(colours("red", "green", "blue"))
    art = draw_checked(images, judge({c: EXTRA_PERSON for c in (RED, GREEN, BLUE)}), "scene", [], "2:3", fallback=True)
    assert art.getpixel((0, 0)) == BLUE and not hard_defect(art.info["comic_verification"])


def test_a_hard_defect_stays_out_even_against_an_extra_person():
    images = FakeImages(colours("red", "green", "blue"))
    vision = judge({RED: {"bad_anatomy": True}, GREEN: EXTRA_PERSON, BLUE: {"has_text": True}})
    assert draw_checked(images, vision, "scene", [], "2:3", fallback=True).getpixel((0, 0)) == GREEN


@pytest.mark.parametrize("correction", [
    "Remove the second person standing next to Hero",
    "Remove the extra background figure beside the desk.",
    "Erase the duplicate hero on the left.",
    "Delete the bystander in the foreground",
])
def test_a_correction_asking_to_remove_a_person_marks_the_draw_when_the_flag_is_missing(correction):
    found = inspect_art(Image.new("RGB", (64, 64)), FakeVision(lambda p, i: {**BASE, "scene_mismatch": True, "corrections": [correction]}),
                        context="Hero opens the drawer.")
    assert found["extra_person"] is True


@pytest.mark.parametrize("answer", [
    {"scene_mismatch": True, "corrections": ["Remove the woman's gloves."]},
    {"scene_mismatch": True, "corrections": ["Add the second character named in the brief."]},
    {"scene_mismatch": True, "corrections": ["Remove the gloves from the woman."]},
    {"scene_mismatch": True, "extra_person": False, "corrections": ["Draw the drawer open."]},
    {"scene_mismatch": False, "extra_person": True},  # a distant figure the checker did not call a mismatch
])
def test_other_rejections_and_accepted_draws_are_not_marked(answer):
    found = inspect_art(Image.new("RGB", (64, 64)), FakeVision(lambda p, i: {**BASE, **answer}), context="Hero opens the drawer.")
    assert "extra_person" not in found


def test_a_distant_figure_the_check_accepts_still_passes():
    images = FakeImages(colours("red"))
    draw_checked(images, FakeVision(lambda p, i: {**BASE, "extra_person": True}), "scene", [], "2:3")
    assert len(images.calls) == 1


def test_the_checker_is_asked_for_the_flag_only_when_it_has_a_brief():
    vision = FakeVision(lambda p, i: dict(BASE))
    inspect_art(Image.new("RGB", (64, 64)), vision, context="Hero opens the drawer.")
    inspect_art(Image.new("RGB", (64, 64)), vision)
    assert EXTRA_PERSON_NOTE in vision.prompts[0] and "extra_person," in vision.prompts[0].rsplit("exactly these fields", 1)[1]
    assert "extra_person" not in vision.prompts[1]
