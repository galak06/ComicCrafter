"""The panel field "sfx": a sound effect the engine letters over the finished, checked art.

It is never part of an image prompt and never fails a page: a sound effect that cannot be placed is left out
and the panel is returned as it was lettered. Each one leaves an entry in the renderer's audit:

    {"accepted": True, "kind": "sfx", "panel": 2, "placed": True, "reason": None, "box": [x, y, w, h],
     "requirements": [], "checks": {}}

"accepted" is always True (it is never a rejected draw). When "placed" is False, "box" is None and "reason"
is "no_plan" (the planner's answer was unusable, so faces are unknown), "too_long", "too_big", "no_space"
or "error".
"""

import logging
from typing import Optional

from PIL import Image

from layout.bubble_planner import BubblePlan, plan_bubbles
from layout.comic_bubbles import _subjects
from layout.sound_effects import draw_sfx, lettering_ink, sfx_text  # noqa: F401  (sfx_text re-exported)

logger = logging.getLogger(__name__)


def letter_sfx(renderer, art: Image.Image, lettered: Image.Image, text: str, rtl: bool,
               type_height: Optional[int] = None, plan: Optional[BubblePlan] = None) -> Image.Image:
    """The lettered panel with its sound effect, or unchanged when it cannot be placed. Never raises.

    plan is the bubble plan the panel was lettered with (its "sfx" point rode that same vision call). A panel
    with nothing else to letter passes None: the planner is then asked once, and an unusable answer leaves
    the sound effect out, with no second (precise) pass.
    """
    entry = {"accepted": True, "kind": "sfx", "panel": renderer.current_panel, "placed": False, "reason": None,
             "box": None, "requirements": [], "checks": {}}
    result = lettered
    try:
        if plan is None:
            plan = plan_bubbles(art, [], False, rtl, vision=renderer.vision, sfx=text)
        if plan is None or not plan.protected_checked:
            entry["reason"] = "no_plan"
        else:
            panel = lettered.convert("RGB")
            box, entry["reason"] = draw_sfx(panel, text, plan.sfx, _subjects(plan, panel.size), rtl, type_height,
                                            ink=lettering_ink(art, lettered), font_path=renderer.options.font_path)
            if box:
                result = panel
                entry.update(placed=True, box=list(box))
    except Exception as error:  # decoration only: the page is never lost to its sound effect
        logger.warning(f"Sound effect left out: {error}")
        result = lettered
        entry.update(placed=False, reason="error", box=None)
    renderer.audit.append(entry)
    return result
