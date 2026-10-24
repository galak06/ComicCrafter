"""Draw comic-style speech bubbles with tails and narration captions."""

import math
import re
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from layout.bubble_planner import BubblePlan
from utils import get_logger

logger = get_logger(__name__)

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf",
    "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf",
    "comicbd.ttf",
    "comic.ttf",
    "DejaVuSans-Bold.ttf",
    "Arial.ttf",
]
# Comic Sans has no Hebrew glyphs, so Hebrew text gets its own fonts.
# (path, face index); SF Hebrew is skipped because it lacks commas, question marks and digits.
HEBREW_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Raanana.ttc", 1),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0),
    ("DejaVuSans-Bold.ttf", 0),
]
HEBREW_CHARS = re.compile(r"[֐-׿]")
Rect = Tuple[int, int, int, int]  # x, y, width, height
CAPTION_FILL = (243, 227, 181)
INK = (0, 0, 0)
PAPER = (255, 255, 255)


def is_rtl(text: str) -> bool:
    return bool(HEBREW_CHARS.search(text))


def _font(size: int, text: str = "") -> ImageFont.ImageFont:
    candidates = HEBREW_FONT_CANDIDATES if is_rtl(text) else [(name, 0) for name in FONT_CANDIDATES]
    for name, index in candidates:
        try:
            return ImageFont.truetype(name, size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return "\n".join(lines)


def _ellipse_edge(cx: float, cy: float, rx: float, ry: float, tx: float, ty: float) -> Tuple[float, float, float]:
    """Point on the ellipse edge facing (tx, ty), and the angle to it."""
    angle = math.atan2((ty - cy) / ry, (tx - cx) / rx)
    return cx + rx * math.cos(angle), cy + ry * math.sin(angle), angle


def _tail(cx: float, cy: float, rx: float, ry: float, target: Tuple[float, float], max_len: float) -> List[Tuple[float, float]]:
    """Triangle from inside the ellipse toward the speaker, stopping short of them."""
    ex, ey, angle = _ellipse_edge(cx, cy, rx, ry, *target)
    dx, dy = target[0] - ex, target[1] - ey
    dist = math.hypot(dx, dy) or 1.0
    length = min(dist * 0.7, max_len)
    tip = (ex + dx / dist * length, ey + dy / dist * length)

    half = 0.22  # radians either side of the edge point for the tail base
    base = [
        (cx + rx * 0.8 * math.cos(angle + s * half), cy + ry * 0.8 * math.sin(angle + s * half))
        for s in (-1, 1)
    ]
    return [base[0], tip, base[1]]


def _shrink(points: List[Tuple[float, float]], amount: float) -> List[Tuple[float, float]]:
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    out = []
    for x, y in points:
        d = math.hypot(x - cx, y - cy) or 1.0
        out.append((x - (x - cx) / d * amount, y - (y - cy) / d * amount))
    return out


def head_box(speaker: Tuple[float, float], size: Tuple[int, int]) -> Rect:
    """Rough rectangle around a speaker's head, from their mouth position."""
    w, h = size
    sx, sy = speaker[0] * w, speaker[1] * h
    return (int(sx - 0.07 * w), int(sy - 0.16 * h), int(0.14 * w), int(0.26 * h))


def _hits(a: Rect, b: Rect, gap: int) -> bool:
    return a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap and a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap


def _choose_position(
    size: Tuple[int, int],
    bubble: Tuple[int, int],
    desired: Tuple[float, float],
    speaker: Optional[Tuple[float, float]],
    obstacles: List[Rect],
) -> Tuple[int, int]:
    """Top-left corner for a bubble: free of obstacles, near the desired spot, preferably above the speaker."""
    w, h = size
    bw, bh = bubble
    gap = max(6, h // 80)
    best, best_score = None, float("inf")
    for y0 in range(5, max(6, h - bh - 5), max(4, h // 40)):
        for x0 in range(5, max(6, w - bw - 5), max(4, w // 60)):
            if any(_hits((x0, y0, bw, bh), o, gap) for o in obstacles):
                continue
            cx, cy = x0 + bw / 2, y0 + bh / 2
            score = math.hypot(cx - desired[0], cy - desired[1])
            if speaker:
                score += 0.5 * math.hypot(cx - speaker[0], cy - speaker[1])
                score += 0.3 * h if cy > speaker[1] else 0  # bubbles read best above the speaker
            if score < best_score:
                best, best_score = (x0, y0), score
    if best is None:
        return int(desired[0] - bw / 2), int(desired[1] - bh / 2)
    return best


def draw_speech_bubble(
    image: Image.Image,
    text: str,
    center: Tuple[float, float],
    speaker: Optional[Tuple[float, float]],
    placed: List[Tuple[int, int, int, int]],
) -> None:
    """Draw an oval bubble near center with a tail toward the speaker.

    Args:
        image: Panel image, drawn on in place
        text: Dialogue text
        center: Desired bubble center, normalized 0-1
        speaker: Speaker's mouth, normalized 0-1 (None points the tail down)
        placed: Areas to keep clear (heads, caption, earlier bubbles); updated in place
    """
    w, h = image.size
    draw = ImageDraw.Draw(image)
    font = _font(max(16, int(h * 0.04)), text)
    line_width = max(2, h // 220)

    # Wrap to a roughly 3:1 text block so the oval stays round rather than flat
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3]
    balanced = int(math.sqrt(draw.textlength(text, font=font) * line_height * 3))
    wrapped = _wrap(draw, text, font, min(int(w * 0.26), max(balanced, int(w * 0.08))))
    left, top, right, bottom = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center")
    tw, th = right - left, bottom - top
    rx, ry = tw * 0.72 + 14, th * 0.78 + 12  # ellipse radii that enclose the text block

    x0, y0 = _choose_position(
        (w, h),
        (int(2 * rx), int(2 * ry)),
        (center[0] * w, center[1] * h),
        (speaker[0] * w, speaker[1] * h) if speaker else None,
        placed,
    )
    placed.append((x0, y0, int(2 * rx), int(2 * ry)))
    cx, cy = x0 + rx, y0 + ry

    target = (speaker[0] * w, speaker[1] * h) if speaker else (cx, cy + ry + h * 0.1)
    tail = _tail(cx, cy, rx, ry, target, max_len=h * 0.14)

    box = [cx - rx, cy - ry, cx + rx, cy + ry]
    draw.polygon(tail, fill=INK)
    draw.ellipse([box[0] - line_width, box[1] - line_width, box[2] + line_width, box[3] + line_width], fill=INK)
    draw.polygon(_shrink(tail, line_width * 1.6), fill=PAPER)
    draw.ellipse(box, fill=PAPER)
    draw.multiline_text((cx - tw / 2 - left, cy - th / 2 - top), wrapped, font=font, fill=INK, align="center")


def draw_caption(image: Image.Image, text: str, corner: str, placed: List[Tuple[int, int, int, int]]) -> None:
    """Draw a rectangular narration caption in a top corner."""
    w, h = image.size
    draw = ImageDraw.Draw(image)
    font = _font(max(14, int(h * 0.04)), text)
    pad = max(6, h // 60)
    align = "right" if is_rtl(text) else "left"

    wrapped = _wrap(draw, text, font, int(w * 0.3))
    left, top, right, bottom = draw.multiline_textbbox((0, 0), wrapped, font=font, align=align)
    bw, bh = right - left + 2 * pad, bottom - top + 2 * pad
    margin = max(8, h // 40)
    x0 = margin if corner == "top-left" else w - bw - margin

    draw.rectangle([x0, margin, x0 + bw, margin + bh], fill=CAPTION_FILL, outline=INK, width=max(2, h // 300))
    draw.multiline_text((x0 + pad - left, margin + pad - top), wrapped, font=font, fill=INK, align=align)
    placed.append((x0, margin, bw, bh))


def render_dialogue(image: Image.Image, dialogue: List[str], caption: str, plan: BubblePlan) -> Image.Image:
    """Return a copy of the panel with its caption and speech bubbles drawn."""
    panel = image.convert("RGB").copy()
    # Every visible speaker's head is kept clear of all bubbles
    placed: List[Rect] = [head_box(s, panel.size) for s in plan.speakers if s]

    if caption:
        draw_caption(panel, caption, plan.caption_corner, placed)
    for text, center, speaker in zip(dialogue, plan.bubbles, plan.speakers):
        draw_speech_bubble(panel, text, center, speaker, placed)

    logger.debug(f"Drew {len(dialogue)} bubbles{' and a caption' if caption else ''}")
    return panel
