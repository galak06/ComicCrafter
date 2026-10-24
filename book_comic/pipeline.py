"""Book PDF -> one comic page per chapter -> PNG pages and a combined PDF."""

import json
import logging
from pathlib import Path
from typing import Callable, Dict, Optional

from book_comic.book_text import extract_chapters
from book_comic.render import PageRenderer, save_pdf
from book_comic.script import ScriptWriter

logger = logging.getLogger(__name__)


def _cached(path: Path, build: Callable[[], object]):
    """Load JSON from path, or build it and save it, so reruns don't pay for the same LLM call."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = build()
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


def generate_book_comic(
    pdf_path: Path,
    output_dir: Path,
    first_chapter: int = 1,
    last_chapter: Optional[int] = None,
) -> Dict:
    """Make one comic page per chapter in [first_chapter, last_chapter].

    The character sheet and chapter scripts are cached in output_dir, so pages made in
    separate runs share the same characters. The PDF holds every page made so far.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    chapters = extract_chapters(pdf_path)
    last_chapter = last_chapter or chapters[-1].number
    selected = [c for c in chapters if first_chapter <= c.number <= last_chapter]
    logger.info(f"{len(chapters)} chapters found; drawing {len(selected)}")

    writer = ScriptWriter()
    cast = _cached(output_dir / "cast.json", lambda: writer.build_cast(chapters))
    renderer = PageRenderer(cast)

    pages = []
    for chapter in selected:
        panels = _cached(
            output_dir / f"script_{chapter.number:02d}.json",
            lambda: writer.script_chapter(chapter, cast),
        )
        pages.append(renderer.render_page(panels, output_dir / f"page_{chapter.number:02d}.png"))

    all_pages = sorted(output_dir.glob("page_*.png"))
    pdf = save_pdf(all_pages, output_dir / f"{pdf_path.stem}-comic.pdf")
    return {
        "status": "success",
        "pages": [str(p) for p in pages],
        "pdf": str(pdf),
        "pages_in_pdf": len(all_pages),
        "cost_usd": round(writer.total_cost + renderer.total_cost, 4),
    }
