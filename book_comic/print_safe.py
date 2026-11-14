"""Where lettering may sit so it prints inside every comic printer's safe area: the one place the numbers come from.

The engine letters a comic before the printer is known (the Books app picks it from the order's country when it
builds the print files, and that choice can change after the pages are drawn). So every caption, balloon, note,
sound effect and cover line must be safe for all printers at once. PrintSafe holds that strictest box:

- page: insets in px of the 2063 x 3150 engine page (trim plus bleed as drawn), inside which every lettered pixel of
  an interior page stays. The panel art may still run to the layout's 100 px margin; only the lettering moves in.
- cover: shares of the cover art (the same 2063 x 3150 px) for the front and back cover lettering, the blurb panel
  and the stamps.

How each printer places an interior page (the Books app, comicPrintSupplier.ts):

- Lulu (6.625 x 10.25 in trim, text kept 0.5 in inside it): `containInSafeZone` fits the whole page into the trim,
  at 2063 px across 6.625 in (311.4 px/in). The page is then 10.116 in tall, centred, 0.067 in short of the trim at
  the top and at the bottom. 0.5 in plus 1 mm to spare is 168 px from the left and right edges, and
  (0.5 in + 1 mm - 0.067 in) x 311.4 = 148 px from the top and bottom.
- BookPod (B5, 165 x 235 mm, 5 mm safe area): the page is shrunk into the 155 x 225 mm safe box, so every pixel is
  already 5 mm inside the trim; 1 mm to spare asks 14 px at the top and bottom, and nothing at the sides.

DEFAULT_PRINT_SAFE takes the larger inset of the two on every side (Lulu's: 168, 168, 148, 148). The app computes
the same box from its printer configs and may pass it (RenderOptions.print_safe, render_cover / render_back_cover
print_safe); an engine called without it is still safe on both printers.

Covers: the printed cover scales the art to cover the front panel and its bleed, so the art's edges are cut away.
Lulu's comic (174.7 x 266.7 mm of art): the trim is 3.2 mm inside the art top and bottom and 4.8 mm at the outer
side. BookPod's B5 (168.2 x 256.8 mm of art): 7.8 mm cut at the top, 14 mm at the bottom, 3.2 mm at the outer side.

- top 0.07: a line starts 7% below the art's top: 15.5 mm (0.61 in) inside Lulu's trim and 10.2 mm inside
  BookPod's (5 mm). It was 0.064 (13.9 mm on Lulu, 1.2 mm to spare, measured 0.545 in on a real cover).
- bottom 0.11: lettering ends 11% above the art's bottom: 26.2 mm inside Lulu's trim, 14.2 mm inside BookPod's.
- width 0.78: lettering, the back cover's blurb panel and the stamps stay on the middle 78% of the width: 14.4 mm
  inside Lulu's side trims and 15.3 mm inside BookPod's. The blurb panel was 80% wide (12.6 mm, 0.495 in, on Lulu).

The Books app's own strictest box (comicPrintSafeBox, 1 mm tolerance, ceil'd) is APP_PAGE_INSETS_PX for a page and
APP_COVER_INSETS_PX for the cover art: the page default equals it, and the cover shares are at least as strict on
every side (227, 227, 220 and 347 px against 219, 219, 200 and 246; tests/test_page_print_safe.py holds them together).
"""

import math
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple, Union

MM_PER_IN = 25.4
TOLERANCE_MM = 1.0  # spare room on top of each printer's own margin (rounding, the printer's trim tolerance)
# The engine page: 6.625 x 10.25 in trim plus 0.125 in bleed per edge at 300 DPI (render.PRINT_PAGE_SIZE).
ENGINE_PAGE_PX = (math.ceil(6.875 * 300), math.ceil(10.5 * 300))  # (2063, 3150)

# Books app comicPrintSafeBox() (2026-11-14), px inward from each edge: (left, right, top, bottom).
APP_PAGE_INSETS_PX = (168, 168, 148, 148)  # all Lulu; BookPod's page alone needs 0, 0, 14, 14
APP_COVER_INSETS_PX = (219, 219, 200, 246)  # Lulu 219/219/200/200; BookPod's top-anchored crop drives the bottom

Bounds = Tuple[int, int, int, int]  # left, top, right, bottom in px: lettered pixels satisfy left <= x < right


@dataclass(frozen=True)
class Placement:
    """How a printer places the engine page on its interior trim: fitted (contain, centred) into fit_mm, a box
    centred on the trim, with lettering required margin_mm inside the trim."""
    name: str
    trim_mm: Tuple[float, float]
    fit_mm: Tuple[float, float]
    margin_mm: float

    def scale(self, page_px: Tuple[int, int] = ENGINE_PAGE_PX) -> float:
        """mm per engine px."""
        return min(self.fit_mm[0] / page_px[0], self.fit_mm[1] / page_px[1])

    def offsets(self, page_px: Tuple[int, int] = ENGINE_PAGE_PX) -> Tuple[float, float]:
        """(x, y) in mm from the trim's edge to the placed page's edge."""
        s = self.scale(page_px)
        return (self.trim_mm[0] - page_px[0] * s) / 2, (self.trim_mm[1] - page_px[1] * s) / 2

    def inside_trim_mm(self, box: Tuple[float, float, float, float], page_px: Tuple[int, int] = ENGINE_PAGE_PX) -> Dict[str, float]:
        """How far inside the trim a box [x, y, w, h] in engine page px prints, per side."""
        s = self.scale(page_px)
        ox, oy = self.offsets(page_px)
        x, y, w, h = box
        return {"left": ox + x * s, "right": ox + (page_px[0] - x - w) * s,
                "top": oy + y * s, "bottom": oy + (page_px[1] - y - h) * s}


LULU = Placement("lulu", (6.625 * MM_PER_IN, 10.25 * MM_PER_IN), (6.625 * MM_PER_IN, 10.25 * MM_PER_IN), 0.5 * MM_PER_IN)
BOOKPOD = Placement("bookpod", (165.0, 235.0), (155.0, 225.0), 5.0)
PLACEMENTS = (LULU, BOOKPOD)


@dataclass(frozen=True)
class PageInsets:
    """Insets in engine page px inside which interior lettering stays."""
    left: int
    right: int
    top: int
    bottom: int


@dataclass(frozen=True)
class CoverSafe:
    """Where cover lettering may sit, as shares of the cover art: it starts `top` below the top, ends `bottom` above
    the bottom, and is centred on `width` of the width (side inset (1 - width) / 2)."""
    top: float = 0.07
    bottom: float = 0.11
    width: float = 0.78

    def side_px(self, cover_width: int) -> int:
        return math.ceil(cover_width * (1 - self.width) / 2 - 1e-6)  # 1e-6: a px override round-trips exactly

    def bounds(self, size: Tuple[int, int]) -> Bounds:
        """(left, top, right, bottom) in px of the cover's lettering box."""
        w, h = size
        side = self.side_px(w)
        return side, int(h * self.top), w - side, h - math.ceil(h * self.bottom)


def placement_insets(placement: Placement, page_px: Tuple[int, int] = ENGINE_PAGE_PX,
                     tolerance_mm: float = TOLERANCE_MM) -> PageInsets:
    """The page insets that keep lettering margin_mm + tolerance_mm inside this printer's trim."""
    s = placement.scale(page_px)
    ox, oy = placement.offsets(page_px)
    need = placement.margin_mm + tolerance_mm
    side = max(0, math.ceil((need - ox) / s - 1e-9))
    end = max(0, math.ceil((need - oy) / s - 1e-9))
    return PageInsets(side, side, end, end)


def strictest(*insets: PageInsets) -> PageInsets:
    return PageInsets(*(max(getattr(i, key) for i in insets) for key in ("left", "right", "top", "bottom")))


@dataclass(frozen=True)
class PrintSafe:
    """The lettering's safe box for every printer at once: interior page insets (px) and the cover's shares."""
    page: PageInsets = field(default_factory=lambda: strictest(*(placement_insets(p) for p in PLACEMENTS)))
    cover: CoverSafe = field(default_factory=CoverSafe)

    def page_bounds(self, size: Tuple[int, int] = ENGINE_PAGE_PX) -> Bounds:
        """(left, top, right, bottom) in page px of the box lettered pixels stay inside. The insets are px of the
        2063 x 3150 engine page; a page of another size (a test layout, an A4 draft) has them scaled to its size."""
        w, h = size
        sx, sy = w / ENGINE_PAGE_PX[0], h / ENGINE_PAGE_PX[1]
        return (math.ceil(self.page.left * sx), math.ceil(self.page.top * sy),
                w - math.ceil(self.page.right * sx), h - math.ceil(self.page.bottom * sy))

    def panel_bounds(self, page_size: Tuple[int, int], origin: Tuple[int, int], panel_size: Tuple[int, int]) -> Bounds:
        """The page safe box in the coordinates of a panel drawn at `origin` (its art's top-left on the page),
        clipped to the panel: a side the box does not cut is the panel's own edge."""
        left, top, right, bottom = self.page_bounds(page_size)
        (ox, oy), (w, h) = origin, panel_size
        return (min(w, max(0, left - ox)), min(h, max(0, top - oy)),
                max(0, min(w, right - ox)), max(0, min(h, bottom - oy)))

    def to_dict(self) -> Dict:
        return {"page_inset_px": {k: getattr(self.page, k) for k in ("left", "right", "top", "bottom")},
                "cover_inset": {k: getattr(self.cover, k) for k in ("top", "bottom", "width")}}


DEFAULT_PRINT_SAFE = PrintSafe()
DEFAULT_COVER_SAFE = DEFAULT_PRINT_SAFE.cover


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"comic_print_safe_invalid: {name}")
    return value


def as_print_safe(value: Union[None, PrintSafe, Mapping]) -> PrintSafe:
    """A PrintSafe from None (the default), a PrintSafe, or a dict as the Books app sends it:

        {"page_inset_px": {"left": 168, "right": 168, "top": 148, "bottom": 148},
         "cover_inset": {"top": 0.07, "bottom": 0.11, "width": 0.78}}

    cover_inset may instead be given in px of the 2063 x 3150 cover: {"top_px", "bottom_px", "side_px"}. A key left
    out keeps its default. A negative, non-numeric or impossible value raises ValueError (comic_print_safe_invalid).
    """
    if value is None:
        return DEFAULT_PRINT_SAFE
    if isinstance(value, PrintSafe):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("comic_print_safe_invalid: not a mapping")
    page, cover = DEFAULT_PRINT_SAFE.page, DEFAULT_PRINT_SAFE.cover
    insets = value.get("page_inset_px") or {}
    page = PageInsets(*(int(math.ceil(_number(insets.get(k, getattr(page, k)), k))) for k in ("left", "right", "top", "bottom")))
    shares = value.get("cover_inset") or {}
    w, h = ENGINE_PAGE_PX
    top = _number(shares["top_px"], "top_px") / h if "top_px" in shares else _number(shares.get("top", cover.top), "top")
    bottom = _number(shares["bottom_px"], "bottom_px") / h if "bottom_px" in shares else _number(shares.get("bottom", cover.bottom), "bottom")
    width = 1 - 2 * _number(shares["side_px"], "side_px") / w if "side_px" in shares else _number(shares.get("width", cover.width), "width")
    if page.left + page.right >= w or page.top + page.bottom >= h or top + bottom >= 1 or not 0 < width <= 1:
        raise ValueError("comic_print_safe_invalid: the safe box is empty")
    return PrintSafe(page, CoverSafe(top, bottom, width))


def inside(box: Tuple[float, float, float, float], bounds: Bounds) -> bool:
    """Whether a box [x, y, w, h] lies inside bounds (left, top, right, bottom)."""
    x, y, w, h = box
    return x >= bounds[0] and y >= bounds[1] and x + w <= bounds[2] and y + h <= bounds[3]


def lettering_box(kind: str, page, box) -> Dict:
    """One entry of the lettering report: {"kind", "page", "box_px": [x, y, w, h]} (see README, Lettering boxes)."""
    return {"kind": kind, "page": page, "box_px": [int(v) for v in box]}


def check_page(boxes, bounds: Bounds) -> Optional[Dict]:
    """The first reported box outside bounds, or None when every one is inside."""
    return next((b for b in boxes if not inside(b["box_px"], bounds)), None)
