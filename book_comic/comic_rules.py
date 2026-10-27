"""Comic craft rules shared by the script writer and the image prompts.

Rules that can be measured are checked in code: shot variety by the writer (shots_problem), text
painted into the art by art_check.inspect_art, reading order and gutters by the lettering and layout.
The rest (180-degree rule, action lines, contrast, colour mood) are prompt rules.
"""

from typing import Dict, List, Optional, Sequence

COMIC_SHOTS = ("Extreme long shot", "Wide shot", "Medium shot", "Close-up")
ESTABLISHING_SHOTS = ("Extreme long shot", "Wide shot")

# Writer rules, quoted in the chapter prompt
COMIC_SHOT_RULE = (
    "Camera: vary the distance and angle instead of drawing every panel from the same height and distance. "
    f"Use {', '.join(repr(s) for s in COMIC_SHOTS)}: an extreme long or wide shot to establish the place and mood, "
    "a medium shot for action and interaction, a close-up for strong emotion, a facial expression or a small "
    "important detail. Every page uses at least two different shots."
)
COMIC_BUBBLE_RULE = (
    'Bubble type: give every dialogue line exactly one "bubble": "speech" for words said out loud in a normal '
    'voice (the default); "thought" for inner thoughts or feelings nobody around hears; "shout" for shouting, '
    'alarm, bursting anger or a sudden loud noise; "whisper" for speaking quietly, telling a secret, or a weak, '
    'exhausted voice; "broadcast" for a voice from a device (phone, radio, TV, speaker) or a robot; "fear" for '
    'paralysing fear, deep shock or a cold, menacing tone; "song" for singing or humming. Most lines are '
    '"speech"; use the others only when the line calls for them.'
)

# Image rules for every story panel. Never mention "title" or "caption text" here: naming lettering
# makes the image model paint its own.
PANEL_RULES = (
    "Comic craft rules. "
    "Camera: draw exactly the shot named at the start of the scene (extreme long, wide, medium or close-up). "
    "180-degree rule: keep the camera on the same side of the action as the previous panel and keep each "
    "character's direction of travel, unless the scene says they turn around. "
    "Action lines: for fast motion, a jump or an impact, add dynamic action lines along the direction of movement; "
    "none for still moments. "
    "Contrast and focus: draw the main characters and the foreground with bolder outlines and the strongest contrast; "
    "the background with thinner lines, fewer details and lower contrast. "
    "Colour mood: let the palette carry the moment: cool blues for sadness, calm or cold; warm reds and oranges for "
    "danger, anger or excitement; soft warm light for joy and comfort. In black-and-white styles, build depth with "
    "hatching and a clear light side and shadow side. "
    "Consistency: each character's hairstyle, outfit and accessories are identical in every panel, recognisable from "
    "any angle or distance; never remove or add a coat, jacket or accessory. "
)
NO_TEXT_RULE = (
    "Absolutely no writing anywhere in the image: no letters, words, captions, labels, signs, speech "
    "bubbles or boxes with text. Objects that usually carry writing appear blank."
)


def props_rule(cast: Dict) -> str:
    """The story's recurring props (cast["props"]), drawn identically in every panel and on the cover."""
    props = [p for p in cast.get("props") or [] if p.get("name") and p.get("look")]
    if not props:
        return ""
    listed = "; ".join(f"{p['name']}: {p['look']}" for p in props)
    return (
        "Recurring props, drawn exactly as described every time they appear "
        f"(same shape, colour, material and size): {listed}. "
    )


def scene_shot(scene: str) -> Optional[str]:
    """The shot a scene starts with ("Medium shot: ..."), or None."""
    return next((shot for shot in COMIC_SHOTS if scene.strip().startswith(f"{shot}:")), None)


def shots_problem(panels: Sequence[Dict], establishing: bool = True) -> Optional[str]:
    """Why a page's shots break the camera rule, or None when they are fine.

    Args:
        panels: The page's panels, each with a "scene"
        establishing: The page opens a scene, so panel 1 must show the place
    """
    shots: List[Optional[str]] = [scene_shot(p.get("scene", "")) for p in panels]
    if any(shot is None for shot in shots):
        return "scene_without_shot"
    if establishing and shots and shots[0] not in ESTABLISHING_SHOTS:
        return "first_panel_not_establishing"
    if len(shots) > 1 and len(set(shots)) < 2:
        return "shots_not_varied"
    return None
