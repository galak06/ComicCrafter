"""How pages are drawn (RenderOptions), and the optional palette reference a caller may attach to every panel."""

import base64
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, Union

from PIL import Image

from book_comic.revise import data_url

logger = logging.getLogger(__name__)

StyleRef = Union[str, Path, Image.Image]


@dataclass
class RenderOptions:
    """How pages are drawn. The defaults reproduce the plain one-call-per-panel renderer.

    Attributes:
        font_path: Lettering font file for bubbles, captions and notes (default: bundled + system fonts)
        fail_on_image_error: Raise when an image call fails instead of drawing a gray placeholder
        check_art: Ask the vision model whether the art (and the character sheet) has painted-in writing or extra
            hands or design/scene drift, with at most three draws; unchecked art raises, and so does a
            sheet or panel whose three draws all have a hard defect (a panel otherwise keeps its least-bad draw)
        chain_panels: Send the previous panel of the page as a reference, for continuity
        photo: Reference photo of the main character (http or data: URL)
        sheet_path: Where the main character's sheet is drawn once (and reused); it is then a reference
            for every panel. None draws no sheet
        dpi: DPI tag for saved page PNGs (e.g. PRINT_DPI); None leaves PIL's default
        rejected_dir: When set, every draw the art check rejects (panel, cover, sheet) is saved there as
            <stage>_p<panel>_d<draw>.png plus a .json of failed check names and reasons (at most 12 per renderer)
        style_ref: A picture whose palette, line work, lighting and texture every panel should match, normally the
            comic's unlettered front cover art: an image file path (str or Path), an open PIL image, or a data: URL
            (each sent as a JPEG of at most 1536 px), or an http(s) URL (sent as it is). It is the last reference of
            each panel draw (role "palette"), never of the character sheet, and the art check never sees it. A
            file that cannot be read draws the panels without it. None (the default) changes nothing
    """
    font_path: Optional[str] = None
    fail_on_image_error: bool = False
    check_art: bool = False
    chain_panels: bool = False
    photo: Optional[str] = None
    sheet_path: Optional[Path] = None
    dpi: Optional[int] = None
    rejected_dir: Optional[Path] = None
    style_ref: Optional[StyleRef] = None


def palette_reference(source: Optional[StyleRef]) -> Optional[str]:
    """The style_ref as a reference URL for the image model, or None when there is none or it cannot be read.

    A panel draw carries up to four references and is repeated up to three times, so the picture goes as a
    reference-size JPEG (revise.data_url), not as the cover's multi-megabyte print PNG. A page is never lost
    over its palette reference: an unreadable one is logged and left out.
    """
    if source is None or source == "":
        return None
    try:
        if isinstance(source, Image.Image):
            return data_url(source)
        text = str(source)
        if text.startswith(("http://", "https://")):
            return text  # the provider fetches it; the engine makes no network call to shrink it
        if text.startswith("data:"):
            with Image.open(BytesIO(base64.b64decode(text.split(",", 1)[1]))) as image:
                return data_url(image)
        with Image.open(Path(text)) as image:
            return data_url(image)
    except (OSError, ValueError, IndexError) as e:
        logger.warning(f"Palette reference unreadable; drawing panels without it: {type(e).__name__}")
        return None
