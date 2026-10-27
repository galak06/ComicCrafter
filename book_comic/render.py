"""Draw comic pages from page scripts using ComicCrafter's image, layout and lettering code."""

import base64
import logging
import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageOps

from book_comic.art_check import draw_checked, request_art
from book_comic.image_prompts import NO_TEXT, panel_prompt, sheet_prompt  # noqa: F401  (NO_TEXT re-exported)
from generation.openrouter_image_client import OpenRouterImageClient, closest_aspect_ratio
from generation.vision_client import VisionClient
from layout.bubble_planner import default_plan, plan_bubbles
from layout.captions import draw_note, note_corner
from layout.comic_bubbles import is_rtl, render_dialogue
from layout.panel_layout import LayoutManager, LayoutType

logger = logging.getLogger(__name__)

# Print comic page: 6.625 x 10.25 in trim plus 0.125 in bleed per edge = 6.875 x 10.5 in, at 300 DPI
PRINT_DPI = 300
PRINT_PAGE_SIZE = (math.ceil(6.875 * PRINT_DPI), math.ceil(10.5 * PRINT_DPI))  # (2063, 3150)
RTL_LANGUAGES = {"he", "ar", "fa", "ur", "yi"}


@dataclass
class RenderOptions:
    """How pages are drawn. The defaults reproduce the plain one-call-per-panel renderer.

    Attributes:
        font_path: Lettering font file for bubbles, captions and notes (default: bundled + system fonts)
        fail_on_image_error: Raise when an image call fails instead of drawing a gray placeholder
        check_art: Ask the vision model whether the art has painted-in writing, and redraw it once if so
        chain_panels: Send the previous panel of the page as a reference, for continuity
        photo: Reference photo of the main character (http or data: URL)
        sheet_path: Where the main character's sheet is drawn once (and reused); it is then a reference
            for every panel. None draws no sheet
        dpi: DPI tag for saved page PNGs (e.g. PRINT_DPI); None leaves PIL's default
    """
    font_path: Optional[str] = None
    fail_on_image_error: bool = False
    check_art: bool = False
    chain_panels: bool = False
    photo: Optional[str] = None
    sheet_path: Optional[Path] = None
    dpi: Optional[int] = None


def image_url(image: Image.Image) -> str:
    """PNG data URL for a reference image."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def print_layouts() -> LayoutManager:
    """Layout manager for the print comic page size."""
    return LayoutManager(page_width=PRINT_PAGE_SIZE[0], page_height=PRINT_PAGE_SIZE[1])


class PageRenderer:
    """Renders one page per script and tracks image and vision spend."""

    def __init__(
        self,
        cast: Dict,
        images: Optional[OpenRouterImageClient] = None,
        vision: Optional[VisionClient] = None,
        layouts: Optional[LayoutManager] = None,
        options: Optional[RenderOptions] = None,
    ):
        self.cast = cast
        self.looks = {c["name_en"].lower(): c for c in cast["characters"]}
        self.images = images or OpenRouterImageClient()
        self.vision = vision or VisionClient()
        self.layouts = layouts or LayoutManager()
        self.options = options or RenderOptions()
        self._sheet: Optional[str] = None
        self._previous: Optional[Image.Image] = None

    @property
    def total_cost(self) -> float:
        return self.images.total_cost + self.vision.total_cost

    def _character(self, name: str) -> Dict:
        return self.looks.get(name.strip().lower(), {"name_en": name, "look": ""})

    def _rtl(self, texts: List[str]) -> bool:
        """Reading direction: cast["language"] when set, else detected from the text."""
        language = (self.cast.get("language") or "").lower()
        return language in RTL_LANGUAGES if language else any(is_rtl(t) for t in texts)

    def _art(self, prompt: str, references: List[str], aspect_ratio: str) -> Image.Image:
        if self.options.check_art:
            return draw_checked(self.images, self.vision, prompt, references, aspect_ratio)
        return request_art(self.images, prompt, references, aspect_ratio)

    def character_sheet(self) -> Optional[str]:
        """Data URL of the main character's sheet, drawn on first use when options.sheet_path is set."""
        path = self.options.sheet_path
        if self._sheet or not path:
            return self._sheet
        if not Path(path).exists():
            references = [self.options.photo] if self.options.photo else []
            prompt = sheet_prompt(self.cast, self.cast["characters"][0], ["photo"] if references else [])
            try:
                request_art(self.images, prompt, references, "2:3").save(path)
            except Exception as e:
                if self.options.fail_on_image_error:
                    raise
                logger.warning(f"Character sheet failed; drawing panels without it: {e}")
                return None
        with Image.open(path) as sheet:
            self._sheet = image_url(sheet.convert("RGB"))
        return self._sheet

    def _image_prompt(self, panel: Dict, roles: tuple = ()) -> str:
        people = "; ".join(
            f"{c['name_en']}: {c['look']}" for c in map(self._character, panel.get("characters", []))
        )
        return panel_prompt(self.cast, panel, people, roles)

    def _draw_panel(self, panel: Dict, size: tuple) -> Image.Image:
        roles, references = [], []
        for role, url in (("photo", self.options.photo), ("sheet", self.character_sheet())):
            if url:
                roles.append(role)
                references.append(url)
        if self.options.chain_panels and self._previous is not None:
            roles.append("previous")
            references.append(image_url(self._previous))
        try:
            art = self._art(self._image_prompt(panel, tuple(roles)), references, closest_aspect_ratio(*size))
            return ImageOps.fit(art, size, Image.Resampling.LANCZOS)
        except Exception as e:
            if self.options.fail_on_image_error:
                raise
            logger.warning(f"Panel image failed, using a gray placeholder: {e}")
            return Image.new("RGB", size, (200, 200, 200))

    def _letter(self, image: Image.Image, panel: Dict) -> Image.Image:
        dialogue = [d for d in panel.get("dialogue", []) if d.get("text")]
        caption = panel.get("caption", "")
        note = panel.get("note", "")
        if not dialogue and not caption and not note:
            return image

        texts = [d["text"] for d in dialogue]
        kinds = [d.get("bubble") or "speech" for d in dialogue]
        rtl = self._rtl(texts + [caption, note])
        # Telling the vision model what each speaker looks like keeps tails on the right character
        speakers = [
            f"{c['name_en']} ({c['look'][:160]})" for c in (self._character(d.get("speaker", "")) for d in dialogue)
        ]
        reserved = [note_corner(rtl)] if note else []
        plan = None
        if texts:
            plan = plan_bubbles(
                image, list(zip(speakers, texts)), bool(caption), rtl, vision=self.vision, reserved_corners=reserved
            )
        plan = plan or default_plan(len(texts))
        font = self.options.font_path
        lettered = render_dialogue(image, texts, caption, plan, kinds=kinds, rtl=rtl, font_path=font)
        return draw_note(lettered, note, rtl=rtl, font_path=font)

    def render_page(self, panels: List[Dict], path: Path) -> Path:
        """Draw, letter and compose one page. Unlettered art is kept as art_<page>_<n>.png beside it."""
        layout = self.layouts.create_layout(LayoutType.VERTICAL_STRIP, num_panels=len(panels))
        images = []
        self._previous = None
        for number, (panel, slot) in enumerate(zip(panels, layout), 1):
            size = tuple(slot.get_content_area()[2:])
            art = self._draw_panel(panel, size)
            art.save(path.parent / f"art_{path.stem}_{number}.png", format="PNG")
            self._previous = art
            images.append(self._letter(art, panel))

        page = self.layouts.compose_page(panels=images, layout=layout)
        dpi = {"dpi": (self.options.dpi, self.options.dpi)} if self.options.dpi else {}
        page.save(path, format="PNG", optimize=True, **dpi)
        logger.info(f"Saved page {path}")
        return path


def save_pdf(pages: List[Path], path: Path) -> Path:
    """Bundle page images into one PDF, in the given order."""
    images = [Image.open(p).convert("RGB") for p in pages]
    images[0].save(path, save_all=True, append_images=images[1:], resolution=300)
    return path
