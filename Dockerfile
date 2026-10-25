# Comic engine image: runs one comic job per container, then exits.
#   docker run --rm --env-file comic.env -v <work>:/work comic-engine python <script>
# Secrets are passed at run time and never baked into the image.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/engine:/engine/ComicCrafter

RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /engine/ComicCrafter
COPY requirements.comic.txt .
RUN pip install -r requirements.comic.txt

COPY . .

RUN useradd --uid 10001 --no-create-home comic && mkdir -p /work && chown comic /work
USER comic
WORKDIR /work

CMD ["python", "-c", "import book_comic.render, generation.openrouter_image_client, layout.bubble_planner, layout.panel_layout; print('comic engine ok')"]
