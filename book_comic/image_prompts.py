"""Image-model prompts for character sheets, story panels and covers.

None of the lettering (captions, dialogue, titles) is ever sent to the image model.
"""

from typing import Dict, Sequence

from book_comic.comic_rules import NO_TEXT_RULE, PANEL_RULES, props_rule

NO_TEXT = (
    "a single full-bleed illustration filling the whole canvas edge to edge: no border, no frame, "
    "no panel lines, no blank boxes or rectangles, no text, no letters, no speech bubbles, "
    "no captions, no watermark"
)

# What each kind of reference image is, for the sentence that introduces them
REFERENCE_ROLES = {
    "photo": "the real person's identity: keep their recognizable face, age, skin tone and hair",
    "sheet": "the approved character design: same face, hair, outfit and marks",
    "previous": "the previous panel of this page",
    "panels": "the first page's panels side by side",
}

PANEL_CRAFT = (
    "Use the exact emotion stated in the scene: make it readable through the eyes, eyebrows, mouth and head angle. "
    "Depict one instant of the stated action, with one clear focal hierarchy: face or gesture first, the important "
    "story object second, and the setting supporting them. Use deliberate foreground, middle ground and background "
    "depth, coherent perspective, motivated lighting and readable contrast around the focal action. Keep hands "
    "anatomically plausible and gaze directed toward the action. Avoid duplicate limbs, merged objects and extra "
    "copies of a character. Do not invent scars, moles, jewelry or costume changes that are not described. "
)


def describe_references(roles: Sequence[str]) -> str:
    """One sentence naming each attached reference image in order ("" when there are none)."""
    if not roles:
        return ""
    named = "; ".join(f"reference image {i} is {REFERENCE_ROLES[role]}" for i, role in enumerate(roles, 1))
    return f"Attached references: {named}. "


def panel_prompt(cast: Dict, panel: Dict, people: str, roles: Sequence[str] = ()) -> str:
    """Prompt for one story panel.

    Args:
        cast: Character sheet (style, characters, optional props)
        panel: The panel's script (scene, characters)
        people: "name: look; ..." for the characters visible in the panel
        roles: Kinds of the attached reference images, in order (see REFERENCE_ROLES)
    """
    previous = ""
    if "previous" in roles:
        previous = (
            "Keep the previous panel's location, architecture, furniture, props, lighting, time of day and outfits; "
            "change only what this scene describes. "
        )
    return (
        f"Comic book panel. Art style: {cast.get('style', 'detailed comic book art')}.\n"
        f"Scene: {panel['scene']}\n"
        f"Characters (draw exactly as described): {people or 'none'}\n"
        f"{describe_references(roles)}{previous}{PANEL_CRAFT}{PANEL_RULES}{props_rule(cast)}"
        "Leave open background (sky, foliage, wall) along the top of the frame; keep heads below it.\n"
        f"Strictly {NO_TEXT}. {NO_TEXT_RULE}"
    )


def sheet_prompt(cast: Dict, character: Dict, roles: Sequence[str] = ()) -> str:
    """Prompt for a full-body character reference sheet, drawn before any panel."""
    return (
        "Draw one full-body comic character in a relaxed three-quarter pose on a plain background, no text. "
        f"{describe_references(roles)}"
        "Make a usable production character reference: the entire silhouette and footwear are visible, hands are "
        "separate from the torso, and clothing layers and accessories are easy to identify. Use natural proportions "
        "for the character's age, one coherent illustrated medium, clean facial detail and a few crisp clothing and "
        f"hair details. Character: {character.get('name_en', '')}: {character.get('look', '')}. "
        f"Style: {cast.get('style', 'detailed comic book art')}. {NO_TEXT_RULE}"
    )


def cover_prompt(cast: Dict, cover: Dict, roles: Sequence[str] = ()) -> str:
    """Prompt for a portrait cover. Never "title" or "text" in the composition lines: naming them makes
    the model paint lettering, and asking for an empty top made it stack a second strip with a seam."""
    hero = (cast.get("characters") or [{}])[0]
    strip = ""
    if "panels" in roles:
        strip = (
            "Draw every story prop and companion, the setting's key features and the outfits exactly as they look "
            "in the first page's panels. They are only a reference: the cover stays one single scene. "
        )
    return (
        f"Full-page portrait comic illustration. Art style: {cast.get('style', 'detailed comic book art')}. "
        f"Scene: {cover.get('scene', '')} Main character: {hero.get('name_en', '')}: {hero.get('look', '')} "
        f"{describe_references(roles)}{strip}"
        "Show the emotion clearly in the eyes and mouth. Build a clear focal hierarchy around the main character's "
        "face, gesture and the story's meaningful prop or clue. Make the silhouette readable at thumbnail size, with "
        "layered depth, coherent perspective and motivated light. Suggest the central tension without revealing the "
        "resolution. One single continuous scene fills the whole canvas edge to edge, with no bands, strips, panels, "
        "borders, frames or dividing lines. Show the main character from the knees up or full length, standing lower "
        "in the frame: the top of the head is about one third of the way down the canvas, with more of the setting "
        "(its sky, ceiling or upper wall) above it, and let the bottom edge fade slightly darker. "
        f"{props_rule(cast)}{NO_TEXT_RULE}"
    )
