"""Extract chapters from a book PDF."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

# Bidi control characters pdftotext leaves around Hebrew text
BIDI_MARKS = re.compile(r"[‎‏‪-‮⁦-⁩]")
CHAPTER_HEADING = re.compile(r"^\s*(?:פרק|Chapter)\s+(\d+)\s*$", re.MULTILINE | re.IGNORECASE)
PAGE_NUMBER_LINE = re.compile(r"^\s*\d+\s*$", re.MULTILINE)


@dataclass
class Chapter:
    number: int
    title: str
    text: str


def read_pdf_text(pdf_path: Path) -> str:
    """Return the PDF's text in logical reading order, without bidi marks or page breaks."""
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"], capture_output=True, text=True, check=True
    )
    return BIDI_MARKS.sub("", result.stdout).replace("\f", "\n")


def split_chapters(text: str) -> List[Chapter]:
    """Split book text on "פרק N" / "Chapter N" headings; the next non-empty line is the title."""
    headings = list(CHAPTER_HEADING.finditer(text))
    chapters = []
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = PAGE_NUMBER_LINE.sub("", text[heading.end():end]).strip()
        title, _, rest = body.partition("\n")
        chapters.append(Chapter(number=int(heading.group(1)), title=title.strip(), text=rest.strip()))
    return chapters


def extract_chapters(pdf_path: Path) -> List[Chapter]:
    chapters = split_chapters(read_pdf_text(pdf_path))
    if not chapters:
        raise ValueError(f"No chapter headings found in {pdf_path}")
    return chapters
