"""Turn a book PDF into a comic, one page per chapter.

Usage:
    python examples/book_example.py <book.pdf> [first_chapter] [last_chapter]
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.tasks import generate_book_comic  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    pdf_path = sys.argv[1]
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    last = int(sys.argv[3]) if len(sys.argv) > 3 else None

    # Call synchronously; use generate_book_comic.delay(...) to run on a Celery worker instead
    result = generate_book_comic(pdf_path, first_chapter=first, last_chapter=last)

    print(f"Status: {result['status']}  (cost ${result['cost_usd']})")
    for page in result["pages"]:
        print(page)
    print(f"PDF ({result['pages_in_pdf']} pages): {result['pdf']}")
