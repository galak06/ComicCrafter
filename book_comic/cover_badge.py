"""An optional caller-supplied badge (a small brand mark) on the front cover, placed where it prints and covers nothing.

The engine only places the picture it is given. The badge never changes the lettering and never fails a cover:
when no corner is free, or the file cannot be read, the cover is lettered without it.

Among the corners clear of the lettering it keeps off the figure with what is already known, without a vision call:
the measured top of the head (the rows above it hold no body) and the unlettered art itself (a corner lying across a
large shape, such as a boot or a limb, loses to a calm one). Real covers 2026-11-13: the badge sat on the hero's boot.
With a measured head the badge is drawn a little smaller when that is what fits it beside the title above the head,
and a corner that is not above the head is used only over calm art: no badge is better than one on the figure or
the main prop (real cover 2026-11-14: 43 px short of the top corner, it was drawn on the robot).
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
# With a measured head, the badge is drawn at the largest of these shares of its size that fits a top corner above it.
SHRINKS = tuple(round(1 - i * 0.025, 3) for i in range(11))  # 1.0 down to 0.75
# With a measured head, a corner that is not above it is used only when the art under it is no rougher than this
# (roughness). Fitted on the eight bottom corners of the four real covers of 2026-11-13 and 2026-11-14 at print size:
# a far building 99, a ledge with a rope's hook 99, other ledges and rock 54 to 83; a robot's arm and wheel 124, a boot 153.
# The margin is thin (moving a corner 30 px gives 106 for the building and 110 for the robot), and busyness itself
# could not tell them apart (ledge 19.1, robot 19.0): this limit is a last resort after the top corners.
ROUGH_LIMIT = 112


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


def _resized(picture: Image.Image, shrink: float) -> Image.Image:
    size = (max(1, round(picture.width * shrink)), max(1, round(picture.height * shrink)))
    return picture if shrink == 1 else picture.resize(size, Image.Resampling.LANCZOS)


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


def roughness(art: Image.Image, box: Box) -> float:
    """The largest colour step inside `box` between shapes a sixteenth of its width and larger: the range of each
    channel after that blur, averaged (0 for a flat colour, 255 for black beside white)."""
    left, top, right, bottom = box
    sigma = max(1, round((right - left) / 16))
    pad = 3 * sigma
    area = (max(0, left - pad), max(0, top - pad), min(art.width, right + pad), min(art.height, bottom + pad))
    blurred = art.crop(area).convert("RGB").filter(ImageFilter.GaussianBlur(sigma))
    extrema = ImageStat.Stat(blurred.crop((left - area[0], top - area[1], right - area[0], bottom - area[1]))).extrema
    return sum(high - low for low, high in extrema) / 3


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
    the bottom band of a hero cover holds the legs and feet, and a dark boot on dark rock looks calm. When the badge
    fits no such corner at its size, it is drawn smaller (SHRINKS, never narrower than WIDTH_RANGE allows) if that
    fits one. Failing that, a free corner is used at full size only over art no rougher than ROUGH_LIMIT, and
    with none there is no badge. Without head_top nothing is shrunk and no corner is refused for its art.
    """
    badge = as_badge(badge)
    picture = _load(badge, page.size) if badge else None
    if picture is None:
        return None
    direction = badge.rtl if isinstance(badge.rtl, bool) else rtl
    gap, top_y = page.height // 50, math.ceil(page.height * TOP_SAFE)
    art = art if art is not None and art.size == page.size else None
    measured = isinstance(head_top, (int, float)) and math.isfinite(head_top)

    def free_corners(size):
        return [box for box in badge_boxes(size, page.size, badge.position, direction, safe_bottom, safe_width)
                if box[0] >= 0 and box[1] >= 0 and _clear(box, lettering, gap)]

    free, full = [], picture
    for shrink in SHRINKS if measured else ():
        if shrink < 1 and full.width * shrink < WIDTH_RANGE[0] * page.width:
            break
        picture = _resized(full, shrink)
        free = [box for box in free_corners(picture.size) if box[1] == top_y and box[3] <= head_top * page.height]
        if free:
            break
    if not free:  # no corner above the head, or no head to go by: the full badge in a free corner
        picture, free = full, free_corners(full.size)
        if not free:
            logger.info("Cover badge not drawn: no corner is clear of the lettering")
            return None
        if measured and art is not None:
            free = [box for box in free if roughness(art, box) <= ROUGH_LIMIT]
            if not free:
                logger.info("Cover badge not drawn: every free corner lies over a shape, none above the head")
                return None
    box = _calmest(art, free) if art is not None else free[0]
    page.alpha_composite(picture, (box[0], box[1]))
    return box
