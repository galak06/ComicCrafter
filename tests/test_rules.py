"""Writer-side craft rules."""

from book_comic.comic_rules import COMIC_BUBBLE_RULE, props_rule, scene_shot, shots_problem
from layout.bubble_shapes import BUBBLE_KINDS


def panels(*scenes):
    return [{"scene": s} for s in scenes]


def test_shot_variety_rules():
    assert scene_shot("Close-up: Dana smiles") == "Close-up"
    assert scene_shot("Dana smiles") is None
    assert shots_problem(panels("Wide shot: a", "Close-up: b", "Medium shot: c")) is None
    assert shots_problem(panels("Wide shot: a", "b", "Close-up: c")) == "scene_without_shot"
    assert shots_problem(panels("Close-up: a", "Wide shot: b")) == "first_panel_not_establishing"
    assert shots_problem(panels("Close-up: a", "Wide shot: b"), establishing=False) is None
    assert shots_problem(panels("Wide shot: a", "Wide shot: b", "Wide shot: c")) == "shots_not_varied"


def test_the_bubble_rule_names_every_kind():
    for kind in BUBBLE_KINDS:
        assert f'"{kind}"' in COMIC_BUBBLE_RULE


def test_props_are_optional():
    assert props_rule({}) == ""
    assert props_rule({"props": [{"name": "lantern", "look": "small brass lantern"}]}).count("lantern: small brass") == 1
