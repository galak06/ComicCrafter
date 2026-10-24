import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.tasks import generate_comic  # noqa: E402

STORY = (
    "A young knight named Elara rides into the misty mountains to find a dragon "
    "said to be terrorizing nearby villages. "
    "At the mouth of a smoking cave, she meets the dragon, Ember, who is old and weary. "
    "Ember explains that he only steals sheep because hunters drove away his prey. "
    "Elara promises to stop the hunters if Ember leaves the villages in peace. "
    "Together they return to the valley, and the villagers cheer their unlikely alliance."
)

if __name__ == "__main__":
    # Synchronous call; use generate_comic.delay(...) to run async via a Celery worker.
    result = generate_comic(STORY, output_name="knight_and_dragon", max_scenes=4)
    print(result["status"])
    for page in result["pages"]:
        print(page)
