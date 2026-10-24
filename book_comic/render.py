"""Draw comic pages from page scripts using ComicCrafter's image, layout and lettering code."""

import logging
from io import BytesIO
from pathlib import Path
from typing import Dict, List

from PIL import Image

from generation.openrouter_image_client import OpenRouterImageClient, closest_aspect_ratio
from layout.bubble_planner import default_plan, plan_bubbles
from layout.comic_bubbles import is_rtl, render_dialogue
from layout.panel_layout import LayoutManager, LayoutType

logger = logging.getLogger(__name__)

NO_TEXT = (
    "a single full-bleed illustration filling the whole canvas edge to edge: no border, no frame, "
    "no panel lines, no blank boxes or rectangles, no text, no letters, no speech bubbles, "
    "no captions, no watermark"
)


class PageRenderer:
    """Renders one page per script and tracks image spend."""

    def __init__(self, cast: Dict):
        self.cast = cast
        self.looks = {c["name_en"].lower(): c for c in cast["characters"]}
        self.images = OpenRouterImageClient()
        self.layouts = LayoutManager()
        self.total_cost = 0.0

    def _character(self, name: str) -> Dict:
        return self.looks.get(name.strip().lower(), {"name_en": name, "look": ""})

    def _image_prompt(self, panel: Dict) -> str:
        people = "; ".join(
            f"{c['name_en']}: {c['look']}" for c in map(self._character, panel.get("characters", []))
        )
        return (
            f"Comic book panel. Art style: {self.cast.get('style', 'detailed comic book art')}.\n"
            f"Scene: {panel['scene']}\n"
            f"Characters (draw exactly as described): {people or 'none'}\n"
            f"Strictly {NO_TEXT}."
        )

    def _draw_panel(self, panel: Dict, size: tuple) -> Image.Image:
        try:
            data = self.images.generate_image(
                self._image_prompt(panel), aspect_ratio=closest_aspect_ratio(*size)
            )
            self.total_cost += self.images.last_cost
            return Image.open(BytesIO(data)).convert("RGB").resize(size, Image.Resampling.LANCZOS)
        except Exception as e:
            logger.warning(f"Panel image failed, using a gray placeholder: {e}")
            return Image.new("RGB", size, (200, 200, 200))

    def _letter(self, image: Image.Image, panel: Dict) -> Image.Image:
        dialogue = [d for d in panel.get("dialogue", []) if d.get("text")]
        caption = panel.get("caption", "")
        if not dialogue and not caption:
            return image

        texts = [d["text"] for d in dialogue]
        rtl = any(is_rtl(t) for t in texts + [caption])
        # Telling the vision model what each speaker looks like keeps tails on the right character
        speakers = [
            f"{c['name_en']} ({c['look'][:160]})" for c in (self._character(d.get("speaker", "")) for d in dialogue)
        ]
        plan = plan_bubbles(image, list(zip(speakers, texts)), bool(caption), rtl) if texts else None
        plan = plan or default_plan(len(texts))
        if rtl and not texts:
            plan.caption_corner = "top-right"
        return render_dialogue(image, texts, caption, plan)

    def render_page(self, panels: List[Dict], path: Path) -> Path:
        layout = self.layouts.create_layout(LayoutType.VERTICAL_STRIP, num_panels=len(panels))
        images = []
        for panel, slot in zip(panels, layout):
            size = tuple(slot.get_content_area()[2:])
            images.append(self._letter(self._draw_panel(panel, size), panel))

        page = self.layouts.compose_page(panels=images, layout=layout)
        page.save(path, format="PNG", optimize=True)
        logger.info(f"Saved page {path}")
        return path


def save_pdf(pages: List[Path], path: Path) -> Path:
    """Bundle page images into one PDF, in the given order."""
    images = [Image.open(p).convert("RGB") for p in pages]
    images[0].save(path, save_all=True, append_images=images[1:], resolution=300)
    return path
