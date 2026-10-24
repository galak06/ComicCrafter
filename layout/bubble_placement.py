"""Collision avoidance for speech bubbles within a panel."""

from typing import List, Tuple

Rect = Tuple[int, int, int, int]  # x, y, width, height

MARGIN = 5
GAP = 10


def _overlaps(a: Rect, b: Rect) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw + GAP and bx < ax + aw + GAP and ay < by + bh + GAP and by < ay + ah + GAP


def _fits(rect: Rect, image_size: Tuple[int, int]) -> bool:
    x, y, w, h = rect
    return x >= MARGIN and y >= MARGIN and x + w <= image_size[0] - MARGIN and y + h <= image_size[1] - MARGIN


def place_bubble(rect: Rect, placed: List[Rect], image_size: Tuple[int, int]) -> Rect:
    """Move a bubble so it doesn't overlap bubbles already placed.

    Tries shifting right, then left, then up past each colliding bubble.
    Falls back to the original position if nothing fits.

    Args:
        rect: Desired bubble rectangle (x, y, width, height)
        placed: Rectangles of bubbles already drawn on this panel
        image_size: Panel (width, height)

    Returns:
        Rectangle to draw the bubble at
    """
    x, y, w, h = rect
    for _ in range(len(placed) + 1):
        hit = next((p for p in placed if _overlaps((x, y, w, h), p)), None)
        if hit is None:
            return (x, y, w, h)

        hx, hy, hw, hh = hit
        candidates = [
            (hx + hw + GAP, y, w, h),
            (hx - w - GAP, y, w, h),
            (x, hy - h - GAP, w, h),
        ]
        free = [c for c in candidates if _fits(c, image_size) and not any(_overlaps(c, p) for p in placed)]
        if free:
            return free[0]
        x, y = candidates[2][0], max(MARGIN, candidates[2][1])
    return rect
