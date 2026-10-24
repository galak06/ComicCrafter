"""Turn book chapters into comic page scripts with an LLM on OpenRouter."""

import json
import os
from typing import Dict, List

import requests

from book_comic.book_text import Chapter

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PANELS_PER_PAGE = 3

CAST_PROMPT = """You are adapting the novel below into a comic book. Before drawing, the artist needs a
fixed character sheet so every character looks identical on every page.

Return JSON:
{{
  "style": "one sentence in English: art style, era, palette and mood that fit this book",
  "characters": [
    {{
      "name": "name exactly as written in the book",
      "name_en": "English transliteration",
      "look": "English, 30-50 words: gender, age, build, face, hair (color, length, style), eye color,
               skin tone, signature clothing and props, distinguishing marks"
    }}
  ]
}}
Include every character who speaks or appears in more than one chapter (at most 10). Base looks on the
book's descriptions; invent consistent details where the book is silent.

Novel:
{book}"""

CHAPTER_PROMPT = """You are writing one comic book page for chapter {number} ("{title}") of a novel.
The page has exactly {panels} panels, stacked top to bottom, that tell the chapter's key moments in order.

Character sheet (use these names):
{cast}

Return JSON:
{{
  "panels": [
    {{
      "scene": "English instructions for the illustrator, 40-70 words: who is in the shot (use name_en),
                what they are doing, their expressions, setting, lighting, camera angle. Compose the shot
                with open sky or plain background in the upper part of the frame. Never mention text,
                speech bubbles, boxes or empty space.",
      "characters": ["name_en of each character visible"],
      "caption": "short Hebrew narration (under 10 words) or empty string",
      "dialogue": [{{"speaker": "name_en", "text": "Hebrew line, under 12 words"}}]
    }}
  ]
}}
Rules:
- Panel 1's caption starts with "פרק {number}: {title}".
- At most 2 dialogue lines per panel; dialogue and captions in natural Hebrew, faithful to the chapter.
- Only characters visible in a panel may speak in it.
- Keep it PG-13: romance is shown through looks, embraces or a kiss, never nudity or explicit content.

Chapter text:
{text}"""


class ScriptWriter:
    """Calls an OpenRouter LLM and tracks what it spent."""

    def __init__(self, model: str = ""):
        self.model = model or os.environ["OPENROUTER_MODEL"]
        self.api_key = os.environ["OPENROUTER_API_KEY"]
        self.total_cost = 0.0

    def _ask_json(self, prompt: str) -> Dict:
        response = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            timeout=300,
        )
        response.raise_for_status()
        body = response.json()
        self.total_cost += float(body.get("usage", {}).get("cost") or 0)
        content = body["choices"][0]["message"]["content"]
        return json.loads(content[content.find("{"):content.rfind("}") + 1])

    def build_cast(self, chapters: List[Chapter]) -> Dict:
        """Character sheet and art style for the whole book."""
        book = "\n\n".join(f"פרק {c.number}: {c.title}\n{c.text}" for c in chapters)
        cast = self._ask_json(CAST_PROMPT.format(book=book))
        if not cast.get("characters"):
            raise ValueError("Character sheet came back empty")
        return cast

    def script_chapter(self, chapter: Chapter, cast: Dict) -> List[Dict]:
        """Panels (scene, characters, caption, dialogue) for one chapter's page."""
        cast_lines = "\n".join(
            f"- {c['name_en']} ({c['name']}): {c['look']}" for c in cast["characters"]
        )
        page = self._ask_json(CHAPTER_PROMPT.format(
            number=chapter.number,
            title=chapter.title,
            panels=PANELS_PER_PAGE,
            cast=cast_lines,
            text=chapter.text,
        ))
        panels = page.get("panels", [])[:PANELS_PER_PAGE]
        if not panels:
            raise ValueError(f"Chapter {chapter.number} script has no panels")
        return panels
