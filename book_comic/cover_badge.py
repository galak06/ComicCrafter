"""An optional caller-supplied badge (a small brand mark) on the front cover, placed where it prints and covers nothing.

The engine only places the picture it is given. The badge never changes the lettering and never fails a cover:
when no corner is free, or the file cannot be read, the cover is lettered without it.

Among the corners clear of the lettering it keeps off the figure with what is already known, without a vision call:
the measured top of the head (the rows above it hold no body) and the unlettered art itself (a corner lying across a
large shape, such as a boot or a limb, loses to a calm one). Real covers 2026-11-13: the badge sat on the hero's boot.
"""

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageFilter, ImageStat

logger = logging.getLogger(__name__)

Box = Tuple[int, int, int, int]  # left, top, right, bottom in px

WIDTH_RANGE = (0.06, 0.2)  # a badge narrower than 6% of the cover is unreadable in print; wider than 20% competes with the title
MAX_HEIGHT = 0.14  # of the cover height: a tall mark is scaled down to this, keeping its shape
# Where a top badge starts: below the title's start (cover_lettering.SAFE_TOP) and below the line above which the
# printers' top margin begins (cover.HEAD_SAFE_MIN, 12.7 mm inside the trim on Lulu's comic and BookPod's B5).
# Repeated here because cover.py imports the lettering; tests/test_cover_badge.py holds the three together.
TOP_SAFE = 0.085
POSITIONS = ("bottom", "top")
# How busy the art is under a corner: the spread of its colours after a blur of an eighth of the badge width. The blur
# wipes out line work (windows, hatching, rock cracks: fine under a badge) and keeps shapes about the badge's own size
# (a boot on a ledge, a limb, a held prop). Measured on the two real covers of 2026-11-13 at print size: plain sky 1,
# far buildings 16, a ledge with half a boot on it 22, cliffs against the sky 23 to 27.
BLUR = 1 / 8
# A later corner replaces an earlier one only when it is calmer by a quarter and more: near-equal corners keep the order.
CALMER = 0.75


@dataclass
class CoverBadge:
    """A picture drawn on the lettered front cover.

    Attributes:
        path: An image file, normally a PNG with transparency (its alpha is kept)
        width: Badge width as a share of the cover width, kept within WIDTH_RANGE (0.06 to 0.2)
        position: "bottom" (default) or "top": the band tried first. The corner is always tried on the
            reading-end side first (bottom-left on a Hebrew cover, bottom-right on an English one), so the badge
            stays away from where a line starts; see place_badge for the order of the other corners and for
            when a calmer corner, or the band above the measured head, is taken instead
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


def busyness(art: Image.Image, box: Box) -> float:
    """How much large-scale shape the art has inside `box` (0 for a flat colour, BLUR for the scale)."""
    left, top, right, bottom = box
    sigma = max(1, round((right - left) * BLUR))
    pad = 3 * sigma  # the blur at the box's edge sees what lies just outside it
    area = (max(0, left - pad), max(0, top - pad), min(art.width, right + pad), min(art.height, bottom + pad))
    blurred = art.crop(area).convert("RGB").filter(ImageFilter.GaussianBlur(sigma))
    return sum(ImageStat.Stat(blurred.crop((left - area[0], top - area[1], right - area[0], bottom - area[1]))).stddev) / 3


def _calmest(art: Image.Image, boxes: Sequence[Box]) -> Box:
    """The first box, unless a later one is calmer by CALMER (and by more than rounding noise on flat art)."""
    best, least = boxes[0], busyness(art, boxes[0])
    for box in boxes[1:]:
        busy = busyness(art, box)
        if busy < least * CALMER - 0.5:
            best, least = box, busy
    return best


def place_badge(page: Image.Image, badge, lettering: Sequence[Box], rtl: bool, safe_bottom: float, safe_width: float,
                art: Optional[Image.Image] = None, head_top: Optional[float] = None) -> Optional[Box]:
    """Draw the badge on the lettered RGBA page in a corner that touches no lettering; returns its box.

    lettering: the boxes of the lines already drawn (title, starring line, footer). A corner is free when the
    badge stays one lettering gap (2% of the height) away from each of them. With no free corner, nothing is drawn.
    art: the unlettered cover art. Without it the first free corner is taken (the order of badge_boxes). With it,
    a later free corner is taken instead when the art under it is calmer by a quarter or more (busyness, CALMER).
    head_top: the top of the hero's head as a share of the height, when it was measured. Free top corners that end
    above it lie over setting, not over the figure, so they are the only ones considered (the calmer of them):
    the bottom band of a hero cover holds the legs and feet, and a dark boot on dark rock looks calm.
    """
    badge = as_badge(badge)
    picture = _load(badge, page.size) if badge else None
    if picture is None:
        return None
    direction = badge.rtl if isinstance(badge.rtl, bool) else rtl
    gap = page.height // 50
    free = [box for box in badge_boxes(picture.size, page.size, badge.position, direction, safe_bottom, safe_width)
            if box[0] >= 0 and box[1] >= 0 and _clear(box, lettering, gap)]
    if not free:
        logger.info("Cover badge not drawn: no corner is clear of the lettering")
        return None
    if isinstance(head_top, (int, float)) and math.isfinite(head_top):
        top_y = math.ceil(page.height * TOP_SAFE)
        free = [box for box in free if box[1] == top_y and box[3] <= head_top * page.height] or free
    box = _calmest(art, free) if art is not None and art.size == page.size else free[0]
    page.alpha_composite(picture, (box[0], box[1]))
    return box
