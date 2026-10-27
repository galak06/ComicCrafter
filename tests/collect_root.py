"""pytest plugin (loaded from pytest.ini): collect the repo root as a plain directory.

The root is itself a package whose __init__.py imports the full, heavy stack (chromadb, langchain,
...). Collect it as a plain directory so the comic tests run with requirements.comic.txt only.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def pytest_collect_directory(path: Path, parent):
    if path == ROOT:
        return pytest.Dir.from_parent(parent, path=path)
    return None
