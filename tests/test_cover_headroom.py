"""The headroom rule can never lose a cover: a revision that comes back worse is one failed draw, with fake clients.

Real run 2026-11-13 (English preview): draw 1 was sound art with the hair 4% down, the headroom revision came back
as a body without a head (head_top null), and the cover raised comic_art_check_unavailable with draw 1 in hand.
"""

import pytest
from PIL import Image

from book_comic import cover as cover_module
from book_comic.art_check import ArtCheckError
from book_comic.best_draw import hard_defect
from book_comic.cover import HEADROOM_FIX, render_cover
from book_comic.revise import REVISE_MARK, revision_prompt
from conftest import FakeImages, FakeVision

CAST = {"style": "comic", "characters": [{"name_en": "Dana", "look": "red coat"}]}
COVER = {"scene": "Dana on the cliff", "title": "Curiosity's Spark", "starring": "Starring Maya"}
CLEAN = {"has_text": False, "bad_anatomy": False, "identity_mismatch": False, "design_mismatch": False, "scene_mismatch": False}
COLOURS = ("red", "green", "blue")
HEADLESS = {**CLEAN, "head_top": None, "identity_mismatch": True, "scene_mismatch": True,
            "corrections": ["Depict the face rather than omitting the head entirely."]}


def render(tmp_path, monkeypatch, answers, audit=None, rejected=None):
    """render_cover over three fake draws answered in turn; returns (image calls, the art that was lettered)."""
    queue, lettered = iter(answers), []
    monkeypatch.setattr(cover_module, "letter_cover", lambda art, c, f, title_at_bottom: lettered.append(art) or art)
    images = FakeImages([Image.new("RGB", (400, 600), c) for c in COLOURS])
    render_cover(CAST, COVER, (400, 600), tmp_path / "cover.png", images, FakeVision(lambda p, i: dict(next(queue))), audit=audit,
                 on_reject=(lambda *a, **k: rejected.append(a)) if rejected is not None else None)
    assert (tmp_path / "cover.png").exists()
    return images.calls, lettered


def colour(art):
    return COLOURS[[Image.new("RGB", (1, 1), c).getpixel((0, 0)) for c in COLOURS].index(art.getpixel((0, 0)))]


def test_a_headless_headroom_revision_is_one_failed_draw_and_the_first_draw_is_kept(tmp_path, monkeypatch):
    audit, rejected = [], []
    answers = [{**CLEAN, "head_top": 40}, HEADLESS, {**CLEAN, "head_top": 30, "design_mismatch": True}]
    calls, lettered = render(tmp_path, monkeypatch, answers, audit, rejected)
    assert len(calls) == 3 and HEADROOM_FIX in calls[1]["prompt"]
    assert not calls[2]["prompt"].startswith(REVISE_MARK)  # draw 3 is a fresh draw, not an edit of the headless one
    assert colour(lettered[0]) == "red"  # the sound first draw, its head a little high
    assert [(r["accepted"], r.get("head_in_margin"), r.get("fallback")) for r in audit] == [(False, True, True), (False, None, None), (False, None, None)]
    assert audit[1]["checks"]["head_missing"] is True
    assert [(a[0], a[4 - 1]) for a in rejected] == [(2, False), (3, False)]  # an ordinary rejection, not "check unavailable"


def test_a_clean_third_draw_after_a_headless_revision_is_published(tmp_path, monkeypatch):
    calls, lettered = render(tmp_path, monkeypatch, [{**CLEAN, "head_top": 40}, HEADLESS, {**CLEAN, "head_top": 250}])
    assert len(calls) == 3 and colour(lettered[0]) == "blue"


def test_three_high_heads_keep_the_draw_whose_head_is_lowest(tmp_path, monkeypatch):
    audit = []
    calls, lettered = render(tmp_path, monkeypatch, [{**CLEAN, "head_top": h} for h in (40, 70, 50)], audit)
    assert len(calls) == 3 and colour(lettered[0]) == "green"
    assert [r.get("fallback") for r in audit] == [None, True, None]


def test_a_sound_high_head_draw_beats_a_later_draw_with_drift(tmp_path, monkeypatch):
    answers = [{**CLEAN, "head_top": 40}, {**CLEAN, "head_top": 300, "scene_mismatch": True}, {**CLEAN, "head_top": 300, "design_mismatch": True}]
    _, lettered = render(tmp_path, monkeypatch, answers)
    assert colour(lettered[0]) == "red"


def test_an_unanswered_check_after_a_sound_high_head_draw_does_not_lose_the_cover(tmp_path, monkeypatch):
    audit, rejected = [], []
    calls, lettered = render(tmp_path, monkeypatch, [{**CLEAN, "head_top": 40}, {}, {}], audit, rejected)
    assert len(calls) == 3 and colour(lettered[0]) == "red"  # the unchecked draws are never the ones published
    assert [a[3] for a in rejected] == [True, True]  # still recorded as "check unavailable"
    assert [r["accepted"] for r in audit] == [False, False, False] and audit[0]["fallback"] is True


@pytest.mark.parametrize("answers, calls", [
    ([{}], 1),  # the check never answered the first draw: as before, at once
    ([{**CLEAN, "head_top": 300, "design_mismatch": True}, {}], 2),  # nor a later one, with only a drifting draw in hand
])
def test_an_unanswered_check_without_a_sound_draw_still_stops_the_cover(tmp_path, answers, calls):
    queue = iter(answers)
    images = FakeImages([Image.new("RGB", (400, 600), c) for c in COLOURS])
    with pytest.raises(ArtCheckError, match="comic_art_check_unavailable"):
        render_cover(CAST, COVER, (400, 600), tmp_path / "cover.png", images, FakeVision(lambda p, i: dict(next(queue))))
    assert len(images.calls) == calls and not (tmp_path / "cover.png").exists()


def test_a_cover_without_a_head_on_every_draw_is_rejected_not_published(tmp_path):
    images = FakeImages([Image.new("RGB", (400, 600), c) for c in COLOURS])
    with pytest.raises(ArtCheckError, match="comic_cover_rejected"):
        render_cover(CAST, COVER, (400, 600), tmp_path / "cover.png", images, FakeVision(lambda p, i: {**CLEAN, "head_top": None}))
    assert len(images.calls) == 3 and not (tmp_path / "cover.png").exists()
    assert images.calls[1]["prompt"].startswith(REVISE_MARK) and "head" in images.calls[1]["prompt"].split("The original brief")[0]


def test_a_missing_head_is_a_hard_defect_with_its_own_revision_request():
    assert hard_defect({**CLEAN, "head_missing": True}) and not hard_defect(CLEAN)
    assert "whole head" in revision_prompt("brief", {**CLEAN, "head_missing": True})
