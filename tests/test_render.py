"""PageRenderer and the script writer with fake clients: references, art checks, fallbacks, old scripts."""

import pytest
from PIL import Image

from book_comic.art_check import draw_checked, inspect_art
from book_comic.book_text import Chapter
from book_comic.render import PageRenderer, RenderOptions
from book_comic.script import ScriptWriter
from conftest import FakeImages, FakeVision
from layout.panel_layout import LayoutManager

CAST = {
    "style": "comic",
    "characters": [{"name_en": "Dana", "look": "red coat"}, {"name_en": "Omer", "look": "green cap"}],
    "props": [{"name": "the brass lantern", "look": "small brass hurricane lantern"}],
}
OLD_PANEL = {"scene": "Dana and Omer at the gate", "characters": ["Dana", "Omer"], "caption": "Morning.",
             "dialogue": [{"speaker": "Omer", "text": "Hi"}]}
SMALL = LayoutManager(page_width=400, page_height=600, margin=10, gutter=10)


def renderer(images, vision=None, **options):
    return PageRenderer(CAST, images, vision or FakeVision(), SMALL, RenderOptions(**options))


def test_an_old_script_renders_with_the_defaults(tmp_path):
    images = FakeImages([Image.new("RGB", (64, 64), "white")])
    vision = FakeVision(lambda p, i: [{"mouth": [500, 500], "bubble": [500, 200]}])
    path = renderer(images, vision).render_page([OLD_PANEL] * 3, tmp_path / "page_01.png")
    assert Image.open(path).size == (400, 600)
    assert len(images.calls) == 3 and all(c["references"] == [] for c in images.calls)  # one plain call per panel
    assert "small brass hurricane lantern" in images.calls[0]["prompt"] and "180-degree rule" in images.calls[0]["prompt"]
    assert "Omer (green cap)" in vision.prompts[0]  # the speaker's own look, not the first character's
    assert sorted(p.name for p in tmp_path.glob("art_*")) == [f"art_page_01_{n}.png" for n in (1, 2, 3)]


def test_a_failed_image_is_gray_by_default_and_fails_the_job_when_asked(tmp_path):
    error = RuntimeError("HTTP 402")
    path = renderer(FakeImages(error=error)).render_page([{"scene": "s"}], tmp_path / "page_01.png")
    assert Image.open(path).getpixel((200, 300)) == (200, 200, 200)
    with pytest.raises(RuntimeError):
        renderer(FakeImages(error=error), fail_on_image_error=True).render_page([{"scene": "s"}], tmp_path / "p.png")


def test_sheet_photo_and_previous_panel_are_references(tmp_path):
    images = FakeImages([Image.new("RGB", (64, 64), "white")])
    r = renderer(images, photo="data:photo", sheet_path=tmp_path / "sheet.png", chain_panels=True, dpi=300)
    path = r.render_page([{"scene": "Wide shot: a"}, {"scene": "Close-up: b"}], tmp_path / "page_01.png")
    sheet, first, second = images.calls
    assert "three-quarter pose" in sheet["prompt"] and sheet["references"] == ["data:photo"]
    assert len(first["references"]) == 2 and first["references"][0] == "data:photo"
    assert len(second["references"]) == 3 and "reference image 3 is the previous panel" in second["prompt"]
    assert "the previous panel of this page" not in first["prompt"]
    assert round(Image.open(path).info["dpi"][0]) == 300
    r.render_page([{"scene": "Wide shot: c"}], tmp_path / "page_02.png")
    assert len(images.calls) == 4  # the sheet is drawn once per book


def test_art_with_painted_text_is_drawn_once_more():
    red, blue = Image.new("RGB", (10, 10), "red"), Image.new("RGB", (10, 10), "blue")
    images = FakeImages([red, blue])
    art = draw_checked(images, FakeVision(lambda p, i: {"has_text": i.getpixel((0, 0)) == (255, 0, 0)}), "scene", ["ref"], "2:3")
    assert art.getpixel((0, 0)) == (0, 0, 255) and len(images.calls) == 2
    assert "Absolutely no writing" in images.calls[1]["prompt"]
    images = FakeImages([red, blue])
    def broken(prompt, image):
        raise RuntimeError("down")
    assert draw_checked(images, FakeVision(broken), "scene", [], "2:3").getpixel((0, 0)) == (255, 0, 0)
    assert len(images.calls) == 1  # a failed check never blocks the art


def test_art_with_a_third_hand_is_drawn_once_more_with_the_anatomy_rule():
    red, blue = Image.new("RGB", (10, 10), "red"), Image.new("RGB", (10, 10), "blue")
    images = FakeImages([red, blue])
    art = draw_checked(images, FakeVision(lambda p, i: {"has_text": False, "bad_anatomy": i.getpixel((0, 0)) == (255, 0, 0)}), "scene", [], "2:3")
    assert art.getpixel((0, 0)) == (0, 0, 255) and len(images.calls) == 2
    assert images.calls[1]["prompt"].startswith("scene Human anatomy:")
    assert "Absolutely no writing" not in images.calls[1]["prompt"]  # only the broken rule is repeated
    images = FakeImages([red, blue])
    assert draw_checked(images, FakeVision(lambda p, i: {"has_text": False, "bad_anatomy": False}), "scene", [], "2:3") \
        .getpixel((0, 0)) == (255, 0, 0) and len(images.calls) == 1


def test_every_drawing_of_a_person_asks_for_ordinary_human_anatomy():
    from book_comic.image_prompts import panel_prompt, sheet_prompt
    rule = "exactly two arms and two hands"
    assert rule in panel_prompt(CAST, {"scene": "Medium shot: Dana works"}, "Dana: red coat")
    assert rule in sheet_prompt(CAST, CAST["characters"][0])


def test_bubble_kinds_and_notes_reach_the_lettering(tmp_path):
    panel = {**OLD_PANEL, "dialogue": [{"speaker": "Omer", "text": "Hi", "bubble": "shout"}], "note": "With love"}
    vision = FakeVision(lambda p, i: [{"mouth": [500, 500], "bubble": [500, 200]}])
    plain = renderer(FakeImages([Image.new("RGB", (64, 64), "white")]), vision)
    art = Image.new("RGB", (380, 180), "white")
    assert plain._letter(art, panel).tobytes() != plain._letter(art, OLD_PANEL).tobytes()
    assert "bottom-right corners" in vision.prompts[0]  # the note's corner is kept bubble-free


def test_language_overrides_text_direction():
    r = renderer(FakeImages([Image.new("RGB", (8, 8))]))
    assert r._rtl(["שלום"]) and not r._rtl(["hello"])
    r.cast = {**CAST, "language": "he"}
    assert r._rtl(["hello"])


def test_the_writer_retries_once_for_the_camera_rule():
    flat = {"panels": [{"scene": "Wide shot: a"}] * 3}
    varied = {"panels": [{"scene": "Wide shot: a"}, {"scene": "Close-up: b"}, {"scene": "Medium shot: c"}]}
    writer = ScriptWriter.__new__(ScriptWriter)
    prompts, answers = [], [flat, varied]
    writer._ask_json = lambda prompt: prompts.append(prompt) or answers.pop(0)
    cast = {"characters": [{"name": "דנה", "name_en": "Dana", "look": "red coat"}]}
    assert writer.script_chapter(Chapter(1, "Start", "text"), cast) == varied["panels"]
    assert '"bubble"' in prompts[0] and "shots_not_varied" in prompts[1]
    answers[:] = [flat, flat]
    assert writer.script_chapter(Chapter(1, "Start", "text"), cast) == flat["panels"]  # kept, not lost


def colours(*names):
    return [Image.new("RGB", (10, 10), n) for n in names]


def judge(flags):
    """Vision fake: the answer for each colour of art, by its top-left pixel."""
    return FakeVision(lambda p, i: flags.get(i.getpixel((0, 0)), {}))


RED, GREEN, BLUE = (255, 0, 0), (0, 128, 0), (0, 0, 255)
HANDS, TEXT, CLEAN = {"bad_anatomy": True}, {"has_text": True}, {}


def test_a_third_draw_happens_when_the_second_is_still_bad():
    images = FakeImages(colours("red", "green", "blue"))
    art = draw_checked(images, judge({RED: HANDS, GREEN: HANDS, BLUE: CLEAN}), "scene", [], "2:3")
    assert art.getpixel((0, 0)) == BLUE and len(images.calls) == 3


def test_the_best_of_three_is_kept_when_all_are_bad():
    images = FakeImages(colours("red", "green", "blue"))
    both = {"bad_anatomy": True, "has_text": True}
    art = draw_checked(images, judge({RED: both, GREEN: TEXT, BLUE: HANDS}), "scene", [], "2:3")
    assert art.getpixel((0, 0)) == GREEN and len(images.calls) == 3  # no extra hands beats no text
    images = FakeImages(colours("red", "green", "blue"))
    art = draw_checked(images, judge({RED: HANDS, GREEN: HANDS, BLUE: HANDS}), "scene", [], "2:3")
    assert art.getpixel((0, 0)) == RED  # a tie keeps the earliest


def test_a_clean_first_draw_costs_one_image_and_one_vision_call():
    images, vision = FakeImages(colours("red")), judge({})
    draw_checked(images, vision, "scene", [], "2:3")
    assert len(images.calls) == 1 and len(vision.prompts) == 1


def test_only_redraws_carry_the_negative_prompt():
    images = FakeImages(colours("red", "blue"))
    draw_checked(images, judge({RED: HANDS}), "scene", [], "2:3")
    first, second = images.calls
    assert first["negative_prompt"] is None and first["prompt"] == "scene"
    assert "third hand" in second["negative_prompt"]


@pytest.mark.parametrize("answer, bad", [
    ({"has_text": False, "bad_anatomy": False, "people": 1, "hands_visible": 3}, True),
    ({"has_text": False, "bad_anatomy": False, "people": 2, "hands_visible": 4}, False),
    ({"has_text": False, "bad_anatomy": False, "people": 1, "hands_visible": 2}, False),
    ({"has_text": False, "bad_anatomy": True, "people": 1, "hands_visible": 2}, True),
    ({"has_text": False, "bad_anatomy": False}, False),
    ({"bad_anatomy": False, "people": "one", "hands_visible": 9}, False),
])
def test_more_than_two_hands_per_person_is_bad_anatomy(answer, bad):
    found = inspect_art(Image.new("RGB", (2000, 1000)), FakeVision(lambda p, i: answer))
    assert found["bad_anatomy"] is bad and set(found) == {"head_top", "has_text", "bad_anatomy"}


def test_the_sheet_is_redrawn_when_flagged_and_drawn_once_when_clean(tmp_path):
    images = FakeImages(colours("red", "blue"))
    r = renderer(images, judge({RED: HANDS}), check_art=True, sheet_path=tmp_path / "bad.png")
    r.character_sheet()
    assert len(images.calls) == 2 and Image.open(tmp_path / "bad.png").getpixel((0, 0)) == BLUE
    images = FakeImages(colours("red"))
    r = renderer(images, judge({}), check_art=True, sheet_path=tmp_path / "ok.png")
    r.character_sheet()
    assert len(images.calls) == 1
    images = FakeImages(colours("red"))  # without check_art the sheet is never inspected
    vision = judge({RED: HANDS})
    renderer(images, vision, sheet_path=tmp_path / "plain.png").character_sheet()
    assert len(images.calls) == 1 and vision.prompts == []
