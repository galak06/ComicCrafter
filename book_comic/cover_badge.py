"""An optional caller-supplied badge (a small brand mark) on the front cover, placed where it prints and covers nothing.

The engine only places the picture it is given. The badge never changes the lettering and never fails a cover:
when no corner is free, or the file cannot be read, the cover is lettered without it.
"""

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image

logger = logging.getLogger(__name__)

Box = Tuple[int, int, int, int]  # left, top, right, bottom in px

WIDTH_RANGE = (0.06, 0.2)  # a badge narrower than 6% of the cover is unreadable in print; wider than 20% competes with the title
MAX_HEIGHT = 0.14  # of the cover height: a tall mark is scaled down to this, keeping its shape
# Where a top badge starts: below the title's start (cover_lettering.SAFE_TOP) and below the line above which the
# printers' top margin begins (cover.HEAD_SAFE_MIN, 12.7 mm inside the trim on Lulu's comic and BookPod's B5).
# Repeated here because cover.py imports the lettering; tests/test_cover_badge.py holds the three together.
TOP_SAFE = 0.085
POSITIONS = ("bottom", "top")


@dataclass
class CoverBadge:
    """A picture drawn on the lettered front cover.

    Attributes:
        path: An image file, normally a PNG with transparency (its alpha is kept)
        width: Badge width as a share of the cover width, kept within WIDTH_RANGE (0.06 to 0.2)
        position: "bottom" (default) or "top": the band tried first. The corner is always tried on the
            reading-end side first (bottom-left on a Hebrew cover, bottom-right on an English one), so the badge
            stays away from where a line starts; see place_badge for the order of the other corners
        rtl: Reading direction of the cover; None takes it from cast["language"] (render_cover) or the cover's text
    """
    path: Union[str, Path]
    width: float = 0.14
    position: str = "bottom"
    rtl: Optional[bool] = None


def as_badge(badge) -> Optional[CoverBadge]:
    """A CoverBadge from a CoverBadge or a {"path", "width", "position", "rtl"} dict; None for anything else."""
    if isinstance(badge, CoverBadge):
        return badge
    if isinstance(badge, dict) and badge.get("path"):
        known = {key: badge[key] for key in ("path", "width", "position", "rtl") if key in badge}
        return CoverBadge(**known)
    return None


def _load(badge: CoverBadge, cover_size: Tuple[int, int]) -> Optional[Image.Image]:
    """The badge picture at its drawn size, or None when the file is missing, unreadable or not an image."""
    w, h = cover_size
    try:
        share = float(badge.width)
        if not math.isfinite(share):
            share = CoverBadge.width
        with Image.open(Path(badge.path)) as source:
            picture = source.convert("RGBA")
        width = min(max(share, WIDTH_RANGE[0]), WIDTH_RANGE[1]) * w
        scale = min(width / picture.width, MAX_HEIGHT * h / picture.height)
        return picture.resize((max(1, round(picture.width * scale)), max(1, round(picture.height * scale))), Image.Resampling.LANCZOS)
    except Exception as e:  # never a reason to lose the cover
        logger.warning(f"Cover badge not drawn: {type(e).__name__}")
        return None


def _clear(box: Box, taken: Sequence[Box], gap: int) -> bool:
    left, top, right, bottom = box
    return all(right + gap <= l or r + gap <= left or bottom + gap <= t or b + gap <= top for l, t, r, b in taken)


def badge_boxes(size: Tuple[int, int], cover_size: Tuple[int, int], position: str, rtl: bool,
                safe_bottom: float, safe_width: float) -> List[Box]:
    """The four corner boxes for a badge of `size`, in the order they are tried.

    Every box is inside the lettering's print-safe box: the side inset is the lettering's ((1 - SAFE_WIDTH) / 2),
    a bottom badge ends at SAFE_BOTTOM and a top badge starts at TOP_SAFE. Order: the preferred band's
    reading-end corner, its other corner, then the other band's reading-end corner and its other corner.
    """
    (bw, bh), (w, h) = size, cover_size
    inset = math.ceil(w * (1 - safe_width) / 2)
    xs = {"left": inset, "right": w - inset - bw}
    ys = {"bottom": h - math.ceil(h * safe_bottom) - bh, "top": math.ceil(h * TOP_SAFE)}
    end, start = ("left", "right") if rtl else ("right", "left")
    first = position if position in POSITIONS else "bottom"
    bands = (first, "top" if first == "bottom" else "bottom")
    return [(xs[side], ys[band], xs[side] + bw, ys[band] + bh) for band in bands for side in (end, start)]


def place_badge(page: Image.Image, badge, lettering: Sequence[Box], rtl: bool, safe_bottom: float, safe_width: float) -> Optional[Box]:
    """Draw the badge on the lettered RGBA page in the first corner that touches no lettering; returns its box.

    lettering: the boxes of the lines already drawn (title, starring line, footer). A corner is free when the
    badge stays one lettering gap (2% of the height) away from each of them. With no free corner, nothing is drawn.
    """
    badge = as_badge(badge)
    picture = _load(badge, page.size) if badge else None
    if picture is None:
        return None
    direction = badge.rtl if isinstance(badge.rtl, bool) else rtl
    gap = page.height // 50
    for box in badge_boxes(picture.size, page.size, badge.position, direction, safe_bottom, safe_width):
        if box[0] >= 0 and box[1] >= 0 and _clear(box, lettering, gap):
            page.alpha_composite(picture, (box[0], box[1]))
            return box
    logger.info("Cover badge not drawn: no corner is clear of the lettering")
    return None
