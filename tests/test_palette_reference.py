"""RenderOptions.style_ref: a palette reference for every panel, drawn from but never checked against. Fake clients."""

import base64
from io import BytesIO

import pytest
from PIL import Image

from book_comic.art_check import draw_checked
from book_comic.check_tolerance import PALETTE_NOTE
from book_comic.image_prompts import EARLIER_PICTURES, REFERENCE_ROLES, describe_references
from book_comic.render import PageRenderer, RenderOptions, image_url
from book_comic.render_options import palette_reference
from book_comic.revise import REFERENCE_PX, REVISE_MARK
from conftest import FakeImages, FakeVision
from layout.panel_layout import LayoutManager

CAST = {"style": "comic", "characters": [{"name_en": "Dana", "look": "red coat"}]}
SMALL = LayoutManager(page_width=400, page_height=600, margin=10, gutter=10)
PANELS = [{"scene": "Wide shot: a"}, {"scene": "Close-up: b"}, {"scene": "Medium shot: c"}]
CLEAN = {"has_text": False, "bad_anatomy": False, "identity_mismatch": False, "design_mismatch": False, "scene_mismatch": False}
MARK = "palette and rendering-style reference"
# describe_references before the palette role existed, word for word
BEFORE = (
    "Attached references: {named}. "
    "Reference priority: the photo establishes likeness; the character sheet fixes the illustrated face, "
    "age cues, head-to-body proportions, hair, facial hair and exact garment construction. "
    "The specified age group controls depicted age; explicit appearance details override photo hair or accessories. "
    "Use the photo for unspecified details and retain recognizable facial identity within that age group. "
    "The earlier pictures of this story establish the environment and latest prop state unless the current scene explicitly changes them; "
    "they do not control camera framing. "
    "The current scene controls pose, expression, shot distance and camera angle; do not copy a prior composition. "
    "Keep recurring companions and objects recognizable by their fixed geometry and construction. "
)


class SeeingVision(FakeVision):
    """Also records every image list the check was sent."""

    def __init__(self, answer):
        super().__init__(answer)
        self.sent = []

    def ask_json(self, prompt, image, timeout=60):
        self.sent.append(image if isinstance(image, list) else [image])
        return super().ask_json(prompt, image, timeout)


def decoded(url):
    assert url.startswith("data:image/jpeg;base64,")
    return Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1])))


@pytest.fixture
def cover_art(tmp_path):
    """An unlettered cover at print size, with an alpha channel, as a PNG file."""
    path = tmp_path / "cover_art.png"
    Image.new("RGBA", (2063, 3150), (200, 120, 40, 255)).save(path)
    return path


def render(tmp_path, **options):
    images = FakeImages([Image.new("RGB", (64, 64), "white")])
    vision = SeeingVision(lambda p, i: {**CLEAN, "head_top": 400})
    PageRenderer(CAST, images, vision, SMALL, RenderOptions(**options)).render_page(PANELS, tmp_path / "page_01.png")
    return images.calls, vision


@pytest.mark.parametrize("roles", [["photo"], ["sheet"], ["photo", "sheet"], ["photo", "sheet", "previous"], ["photo", "panels"], ["style"]])
def test_without_a_palette_reference_the_reference_sentence_is_word_for_word_the_old_one(roles):
    named = "; ".join(f"reference image {i} is {REFERENCE_ROLES[role]}" for i, role in enumerate(roles, 1))
    assert describe_references(roles) == BEFORE.format(named=named)
    assert describe_references([]) == ""


def test_no_style_ref_draws_and_checks_exactly_as_before(tmp_path):
    plain, vision = render(tmp_path, photo="data:photo", sheet_path=tmp_path / "sheet.png", chain_panels=True, check_art=True)
    sheet, first, second, third = plain
    assert [len(c["references"]) for c in plain] == [1, 2, 3, 3] and first["references"][0] == "data:photo"
    assert all(MARK not in c["prompt"] for c in plain) and all(PALETTE_NOTE not in p for p in vision.prompts)
    assert EARLIER_PICTURES in first["prompt"] and EARLIER_PICTURES in sheet["prompt"]  # said for any references, as before
    art_checks = [images for images in vision.sent if len(images) > 1]
    assert [len(images) for images in art_checks] == [2, 3, 4, 4]  # the candidate and every reference


def test_every_panel_gets_the_palette_reference_last_and_downscaled(tmp_path, cover_art):
    calls, _ = render(tmp_path, photo="data:photo", sheet_path=tmp_path / "sheet.png", chain_panels=True, style_ref=cover_art)
    sheet, first, second, third = calls
    assert sheet["references"] == ["data:photo"] and MARK not in sheet["prompt"]  # the sheet is drawn without it
    assert [len(c["references"]) for c in (first, second, third)] == [3, 4, 4]
    for call in (first, second, third):
        assert call["references"][0] == "data:photo"  # the other references keep their places
        small = decoded(call["references"][-1])
        assert max(small.size) == REFERENCE_PX and small.mode == "RGB"
        assert len(call["references"][-1]) < 400_000
        assert "never copy its composition, figures, poses, setting or objects" in call["prompt"]
    assert "reference image 3 is a palette and rendering-style reference only" in first["prompt"]
    assert EARLIER_PICTURES not in first["prompt"]  # photo + sheet + palette: no earlier picture of the story is attached
    assert "reference image 3 is the previous panel" in second["prompt"] and "reference image 4 is a palette" in second["prompt"]
    assert EARLIER_PICTURES in second["prompt"] and EARLIER_PICTURES in third["prompt"]
    assert "do not copy a prior composition" in first["prompt"]


def test_the_palette_reference_alone_is_the_only_reference(tmp_path, cover_art):
    calls, _ = render(tmp_path, style_ref=str(cover_art))
    assert len(calls) == 3 and all(len(c["references"]) == 1 for c in calls)
    assert all("reference image 1 is a palette" in c["prompt"] and EARLIER_PICTURES not in c["prompt"] for c in calls)


def test_the_check_never_sees_the_palette_reference_and_is_told_so(tmp_path, cover_art):
    calls, vision = render(tmp_path, photo="data:photo", sheet_path=tmp_path / "sheet.png", chain_panels=True, check_art=True,
                           style_ref=cover_art)
    sheet_check, *panel_checks = [(images, prompt) for images, prompt in zip(vision.sent, vision.prompts) if "head_top" in prompt]
    assert PALETTE_NOTE not in sheet_check[1]
    assert [len(images) for images, _ in panel_checks] == [3, 4, 4]  # candidate, photo, sheet (, previous): one fewer than drawn
    for (images, prompt), call in zip(panel_checks, calls[1:]):
        assert images[1:] == call["references"][:-1]  # reference image N is still attached image N+1
        assert PALETTE_NOTE in prompt and "reference image N is attached image N+1" in prompt


def test_a_revision_draw_keeps_the_palette_reference_before_the_rejected_draw():
    red, blue = Image.new("RGB", (10, 10), "red"), Image.new("RGB", (10, 10), "blue")
    images = FakeImages([red, blue])
    vision = SeeingVision(lambda p, i: {**CLEAN, "has_text": i.getpixel((0, 0)) == (255, 0, 0)})
    brief = "scene. Attached references: reference image 1 is the sheet; reference image 2 is a palette."
    draw_checked(images, vision, brief, ["data:sheet"], "2:3", draw_only=["data:palette"])
    first, second = images.calls
    assert first["references"] == ["data:sheet", "data:palette"]
    assert second["prompt"].startswith(REVISE_MARK)  # "the last attached image" is still the rejected draw
    assert second["references"][:2] == ["data:sheet", "data:palette"] and len(second["references"]) == 3
    assert decoded(second["references"][2]).getpixel((0, 0))[0] > 200  # the red draw
    assert all(sent[1:] == ["data:sheet"] and PALETTE_NOTE in prompt for sent, prompt in zip(vision.sent, vision.prompts))


def test_draw_checked_without_draw_only_is_unchanged():
    images, vision = FakeImages([Image.new("RGB", (10, 10), "blue")]), SeeingVision(lambda p, i: dict(CLEAN))
    draw_checked(images, vision, "scene", ["data:sheet"], "2:3")
    assert images.calls[0]["references"] == ["data:sheet"] and vision.sent[0][1:] == ["data:sheet"]
    assert PALETTE_NOTE not in vision.prompts[0]


def test_the_accepted_forms_of_a_style_ref(tmp_path, cover_art):
    picture = Image.new("RGB", (3000, 2000), "teal")
    assert decoded(palette_reference(picture)).size == (REFERENCE_PX, 1024)
    assert decoded(palette_reference(image_url(picture))).size == (REFERENCE_PX, 1024)  # a PNG data URL is shrunk too
    assert decoded(palette_reference(cover_art)).size == decoded(palette_reference(str(cover_art))).size
    assert palette_reference("https://example.com/cover.png") == "https://example.com/cover.png"
    assert palette_reference(None) is None and palette_reference("") is None


@pytest.mark.parametrize("bad", ["missing.png", "notes.txt", "data:image/png;base64,AAAA", "data:broken"])
def test_an_unreadable_style_ref_draws_the_page_without_it(tmp_path, bad):
    (tmp_path / "notes.txt").write_text("not a picture")
    source = bad if bad.startswith("data:") else tmp_path / bad
    assert palette_reference(source) is None
    calls, _ = render(tmp_path, photo="data:photo", style_ref=source)
    assert all(c["references"] == ["data:photo"] and MARK not in c["prompt"] for c in calls)
