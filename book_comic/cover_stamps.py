"""Optional caller-supplied stamps on the back cover: opaque pictures (a logo tile, a barcode panel) in its bottom corners.

The engine only places the pictures it is given. A stamp is anchored to a bottom corner of the lettering's print-safe
box, the same corner in every language, and stands on the lettering's bottom margin. Stamps never move or resize the
text panel and never fail a back cover: with too little room under the text they are drawn smaller together, then
left out, and a file that cannot be read is skipped. The footer line is kept between them (back_cover_lettering).
"""

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image

logger = logging.getLogger(__name__)

Box = Tuple[int, int, int, int]  # left, top, right, bottom in px
Placed = Tuple[Image.Image, Box]

CORNERS = ("left", "right")
WIDTH_RANGE = (0.06, 0.25)  # of the cover width: narrower is unreadable in print, wider crowds the footer between the corners
MAX_HEIGHT = 0.25  # of the cover height: a taller picture is scaled down to this, keeping its shape
# With too little room under the text, every stamp is drawn at the largest of these shares of its size that fits them all.
SHRINKS = tuple(round(1 - i * 0.025, 3) for i in range(11))  # 1.0 down to 0.75


@dataclass
class CornerStamp:
    """An opaque picture drawn in a bottom corner of the lettered back cover.

    Attributes:
        path: An image file (its alpha, when it has one, is kept)
        corner: "left" or "right": the side of the cover as printed, the same in Hebrew and English
        width: Stamp width as a share of the cover width, kept within WIDTH_RANGE (0.06 to 0.25)
    """
    path: Union[str, Path]
    corner: str = "right"
    width: float = 0.14


def as_stamps(stamps) -> List[CornerStamp]:
    """CornerStamps from a list of CornerStamp or {"path", "corner", "width"} dicts; anything else is dropped."""
    found = []
    for stamp in stamps if isinstance(stamps, (list, tuple)) else ():
        if isinstance(stamp, dict) and stamp.get("path"):
            stamp = CornerStamp(**{key: stamp[key] for key in ("path", "corner", "width") if key in stamp})
        if isinstance(stamp, CornerStamp) and stamp.corner in CORNERS:
            found.append(stamp)
    return found


def _load(stamp: CornerStamp, cover_size: Tuple[int, int]) -> Optional[Image.Image]:
    """The stamp picture at its full drawn size, or None when the file is missing, unreadable or not an image."""
    w, h = cover_size
    try:
        share = float(stamp.width)
        if not math.isfinite(share):
            share = CornerStamp.width
        with Image.open(Path(stamp.path)) as source:
            picture = source.convert("RGBA")
        scale = min(min(max(share, WIDTH_RANGE[0]), WIDTH_RANGE[1]) * w / picture.width, MAX_HEIGHT * h / picture.height)
        return picture.resize((max(1, round(picture.width * scale)), max(1, round(picture.height * scale))), Image.Resampling.LANCZOS)
    except Exception as e:  # never a reason to lose the back cover
        logger.warning(f"Back cover stamp not drawn: {type(e).__name__}")
        return None


def _boxes(pictures: Sequence[Tuple[CornerStamp, Image.Image]], shrink: float, cover_size: Tuple[int, int],
           top: int, safe_bottom: float, safe_width: float) -> List[Optional[Placed]]:
    """Each picture at `shrink` of its size in its corner, or None for one that starts above `top`, is narrower than
    WIDTH_RANGE allows, or would touch a stamp placed before it."""
    w, h = cover_size
    inset, bottom, gap = math.ceil(w * (1 - safe_width) / 2), h - math.ceil(h * safe_bottom), h // 50
    placed: List[Optional[Placed]] = []
    for stamp, full in pictures:
        size = (max(1, round(full.width * shrink)), max(1, round(full.height * shrink)))
        left = inset if stamp.corner == "left" else w - inset - size[0]
        box = (left, bottom - size[1], left + size[0], bottom)
        fits = box[1] >= top and (shrink == 1 or size[0] >= WIDTH_RANGE[0] * w)
        apart = all(other is None or box[2] + gap <= other[1][0] or other[1][2] + gap <= box[0] for other in placed)
        placed.append((full if shrink == 1 else full.resize(size, Image.Resampling.LANCZOS), box) if fits and apart else None)
    return placed


def fit_stamps(stamps, cover_size: Tuple[int, int], top: int, safe_bottom: float, safe_width: float) -> List[Placed]:
    """Where the stamps go: (picture, box) for each one that is drawn, in the order given.

    Every stamp stands on the lettering's bottom margin (safe_bottom) with its outer edge on the lettering's side
    inset ((1 - safe_width) / 2), and must start at or below `top` (one lettering gap under the text). All stamps
    share one size: the largest of SHRINKS at which every one fits. When they do not all fit even at the smallest,
    those that fit at full size are kept and the others are left out. Nothing is searched and nothing overlaps.
    """
    pictures = [(stamp, picture) for stamp in as_stamps(stamps) if (picture := _load(stamp, cover_size)) is not None]
    if not pictures:
        return []
    for shrink in SHRINKS:
        placed = _boxes(pictures, shrink, cover_size, top, safe_bottom, safe_width)
        if all(placed):
            return placed
    kept = [item for item in _boxes(pictures, 1, cover_size, top, safe_bottom, safe_width) if item]
    logger.info(f"Back cover stamps: {len(pictures) - len(kept)} left out, no room under the text")
    return kept


def room_between(placed: Sequence[Placed], cover_width: int, gap: int) -> Optional[int]:
    """The widest line centred on the cover that stays `gap` away from every placed stamp; None without stamps."""
    if not placed:
        return None
    centre = cover_width / 2
    half = min(box[0] - centre if box[0] >= centre else centre - box[2] for _, box in placed)
    return max(0, int(2 * (half - gap)))


def draw_stamps(page: Image.Image, placed: Sequence[Placed]) -> None:
    """Draw the placed stamps on the RGBA page."""
    for picture, box in placed:
        page.alpha_composite(picture, (box[0], box[1]))
