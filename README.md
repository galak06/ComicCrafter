# ComicCrafter 🎨📚

**A zero-cost multi-agent AI system for automatic comic generation from text**

ComicCrafter transforms your stories into visual comics using free AI APIs. No expensive GPUs, no local model training, and no paid API subscriptions required!

## ✨ Features

- 🤖 **Multi-Agent Architecture**: Coordinated agents for story analysis, prompt generation, and layout planning
- 🎯 **Character Consistency**: RAG-based character memory using ChromaDB for visual consistency across panels
- 🎨 **Multiple AI Providers**: 
  - **Text Generation**: Groq (Llama 3.3), Google Gemini 2.5
  - **Image Generation**: HuggingFace Inference API (FLUX.1-dev)
- 📐 **Smart Layouts**: Automatic panel layout with multiple preset options
- 💬 **Dialogue Support**: Automatic speech bubble and caption overlays
- 🆓 **Zero Cost**: Uses only free API tiers

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- API keys (all free):
  - [Groq API Key](https://console.groq.com/keys) OR [Google API Key](https://makersuite.google.com/app/apikey)
  - [HuggingFace Token](https://huggingface.co/settings/tokens)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Absirkhan/ComicCrafter.git
   cd ComicCrafter
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install the package**
   ```bash
   pip install -e .
   ```

4. **Configure API keys**
   ```bash
   copy .env.example .env
   ```
   
   Edit `.env` and add your API keys:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   GOOGLE_API_KEY=your_google_api_key_here
   HUGGINGFACE_TOKEN=your_huggingface_token_here
   ```

### Basic Usage

```python
from comiccrafter import ComicCrafter

# Your story
story = """
A brave knight discovers a dragon's lair in the mountains.
The dragon offers the knight a challenge: solve three riddles or face battle.
The knight cleverly solves all three riddles.
Impressed, the dragon becomes the knight's ally.
"""

# Initialize ComicCrafter
crafter = ComicCrafter(llm_provider="groq")

# Generate comic
pages = crafter.generate_comic(
    story_text=story,
    style="fantasy comic book style",
    max_scenes=4,
    add_dialogue=True,
    output_name="dragon_knight"
)

print(f"Generated {len(pages)} pages!")
```

### Run the Example

```bash
python examples/basic_example.py
```

### Run the Web Interface (FastAPI)

For an easy-to-use web interface with REST API:

```bash
python run_api.py
```

Then open your browser to:
- **Web Interface**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

The web interface provides:
- ✨ Interactive story input form
- 🎨 Real-time generation progress
- 🖼️ Instant preview of generated comics
- 📊 Job status tracking
- 🔌 Full REST API for integration

## 🌐 Web API

ComicCrafter includes a FastAPI web application for easy testing and integration.

### Start the API Server

```bash
python run_api.py
```

### Web Interface Features

- **Story Input**: Easy form for entering your story
- **Style Customization**: Choose visual style and parameters
- **Real-time Progress**: Watch generation progress live
- **Instant Preview**: View generated comics immediately
- **Job Management**: Track and manage multiple generation jobs

### REST API Endpoints

- `POST /api/generate` - Generate comic from text
- `GET /api/status/{job_id}` - Check generation status
- `GET /api/output/{filename}` - Download comic page
- `GET /api/jobs` - List all jobs
- `DELETE /api/jobs/{job_id}` - Delete job

For detailed API documentation, see [docs/API_GUIDE.md](docs/API_GUIDE.md) or visit http://localhost:8000/docs after starting the server.

### Python Client Example

```python
from examples.api_client_example import ComicCrafterClient

client = ComicCrafterClient()
job_id = client.generate_comic(
    story_text="Your story here...",
    style="comic book style"
)

# Wait for completion
status = client.wait_for_completion(job_id)

# Download results
files = client.download_all_outputs(job_id, Path("./output"))
```

## 📕 Book Comics (`book_comic`)

`book_comic` turns a book PDF into one comic page per chapter plus a cover
(`examples/book_example.py`, Celery task `generate_book_comic`). It needs only
`requirements.comic.txt`, poppler's `pdftotext` (`brew install poppler` /
`apt-get install poppler-utils`; the Docker image has it) and `OPENROUTER_API_KEY` /
`OPENROUTER_MODEL` (optional `OPENROUTER_IMAGE_MODEL`, `OPENROUTER_VISION_MODEL`).

```bash
pip install -r requirements.comic.txt
python examples/book_example.py book.pdf 1 3   # runs the pipeline synchronously, no Celery
```

### Celery worker

`worker/tasks.py` queues the same jobs on Celery with Redis (`CELERY_BROKER_URL`,
`CELERY_RESULT_BACKEND`, default `redis://localhost:6379/0`). Its tasks write story text with
OpenRouter (`llm_provider="openrouter"`, model from `OPENROUTER_MODEL`); Groq setups keep using
`GROQ_API_KEY` with `llm_provider="groq"`.

```bash
pip install -r requirements.worker.txt        # comic runtime + celery[redis]
pip install -r requirements.txt               # only for the generate_comic task (core.ComicCrafter)
redis-server &                                # or any reachable Redis
celery -A worker.tasks worker --loglevel=info
```

Queue a job from Python with `generate_book_comic.delay("book.pdf", first_chapter=1, last_chapter=3)`.

- **Bubble kinds**: each dialogue line has a `bubble`: `speech`, `thought`, `shout`, `whisper`,
  `broadcast`, `fear` or `song`, each with its own outline, tail and text size. Unknown or missing
  kinds are drawn as speech. The script writer picks one per line.
- **Lettering**: a bundled Hebrew + Latin font (`assets/fonts/Assistant-SemiBold.ttf`), so Latin names
  inside Hebrew text are drawn on any system. Use your own with `RenderOptions(font_path=...)` or
  `render_dialogue(..., font_path=...)`. Captions wrap at 46% of the image width (other widths are
  tried when the lettering does not fit). A caption is always fixed in a top corner of its image, on strip
  panels and full-page splashes alike: the corner read first (top-left, top-right in Hebrew), or the other
  top corner when the first would cover a face or another protected subject. It never floats lower; when
  both corners cover a subject, the text shape that covers least is used. No bubble or bubble tail touches
  the caption: a bubble goes where its tail misses it. A caption in the corner read second keeps the band
  above its bottom free of bubbles, so the caption is read first. An optional
  `note` is drawn in the last-read bottom corner.
- **Sound effects**: a panel's optional `sfx` (one short line, Hebrew or English) is lettered by the engine
  after the art check and after the caption, bubbles and note: Rubik Black, white with a black outline,
  1.6 times the dialogue size, tilted 7° as one piece. It is never named in an image prompt, and a sound
  effect the model paints itself is still a text defect. Its spot rides the bubble planner's one vision call
  (an optional `"sfx": [x, y]` beside the source of the noise); without a point it goes to the upper corner
  read last. It keeps off faces, protected subjects and all other lettering, shrinks down to the dialogue
  size to stay within 45% of the panel's width and 30% of its height, and is left out (never an error, never
  a redraw) when it does not fit; `PageRenderer.audit` gets a `{"kind": "sfx", "placed": ..., "reason": ...}`
  entry either way. A panel with only an `sfx` makes that one planning call; splashes take one too.
- **Image quality**: the writer starts every scene with a shot label. Panel 1 must be an establishing
  shot and every page needs at least two different shots; a page that breaks this rule is written once
  more. Image prompts include the comic craft rules, a strong no-text rule and the book's recurring
  props. The pipeline draws a character sheet once per book. Each panel then gets the sheet, the
  previous panel and an optional photo as reference images. A vision check redraws art (up to three draws, the best kept) if the
  model painted text or an extra hand into it; the character sheet is checked the same way. Image and vision costs are counted in `cost_usd`.
- **Cover**: `cover.png` is drawn from `cast.json`'s `cover`, using page one's panels as a reference
  strip. A seam (a second strip stacked on top) is detected and cropped off. The title and starring line
  stay at the top whenever the head starts at least 2% of the height below that block, measured for the
  cover's own title and faces (`cover_lettering.top_block_end`: about 13% to 16% of the height, so heads
  from about 15% to 18% down keep a top title); only a head that would touch the block gets its title
  block at the bottom instead. A head in the printers' top margin
  (above 8.5% of the height) is drawn again, and that rule never loses a cover: when no later draw is
  accepted (a revision that came back worse, a defect, a check that did not answer), the sound draw whose
  head is lowest is kept. A draw whose check finds no head at all (`head_missing`) is a rejected draw
  like a wrong face, never published; a check that never answered still stops the cover when no sound
  draw is in hand. The cover is
  lettered with a shade, a one-line shadowed title, a starring line and a footer, all inside the
  printers' text margin on the printed cover (`cover_lettering.SAFE_TOP`, `SAFE_BOTTOM`, `SAFE_WIDTH`:
  12.7 mm inside the trim after Lulu's and BookPod's cover crops). It is placed first in the PDF.
- **Cover badge** (optional): `render_cover(..., badge=CoverBadge(path, width=0.14, position="bottom", rtl=None))`
  (`book_comic.cover_badge`, or the same fields as a dict; also `letter_cover(..., badge=...)`) draws a
  caller-supplied picture, normally a PNG with transparency, on the lettered cover. `width` is a share of the
  cover width (kept within 0.06 to 0.2; a tall picture is scaled down to 14% of the height). It goes in one
  of four corners that stay 2% of the height away from every lettered line, tried in this order: the
  `position` band's reading-end corner (bottom-left in Hebrew, bottom-right in English), that band's other
  corner, then the other band's two corners in the same order. Among the free corners it keeps off the
  figure, without a vision call: when the head was measured (`render_cover`, or `letter_cover(...,
  head_top=...)`) and a free top corner ends above it, only such corners are used, because the bottom band
  of a hero cover holds the legs and feet; and a later corner replaces an earlier one when the unlettered
  art under it is calmer by a quarter or more (`cover_badge.busyness`: the spread of colours after a blur
  of an eighth of the badge width, so line work does not count and a boot or a limb does). The corners are inside the lettering's print-safe box (11% in
  from each side, ending at `SAFE_BOTTOM`, a top badge starting 8.5% down). Reading direction comes from
  `cast["language"]`, else the cover's text, unless `rtl` is set. The badge never moves or resizes
  lettering, is not drawn on `art_path`, and never fails a cover: with no free corner, or a missing or
  unreadable file, the cover is saved without it. Without `badge` the cover is pixel for pixel the same.
- **Full-page splash**: `PageRenderer.render_page` takes 3 panels (a vertical strip) or 1 panel (a
  full-page splash, `LayoutType.FULL_PAGE`: one portrait image in the strip's outer frame, with the same
  references and art check, a splash prompt, and at most one caption and one bubble lettered at a strip
  panel's type size). Any other count raises `ValueError`.
- **Print size** (optional): `book_comic.render.print_layouts()` gives 6.875 × 10.5 in pages
  (2063 × 3150 px), and `RenderOptions(dpi=PRINT_DPI)` tags the PNGs at 300 DPI.

`RenderOptions` defaults reproduce the plain renderer: one call per panel, no references and a gray
placeholder when an image fails. Set `fail_on_image_error=True` to raise instead. The pipeline turns on
`sheet_path`, `chain_panels` and `check_art` (`book_comic.pipeline.default_options`). Pass
`options=RenderOptions()` for the plain renderer.

`RenderOptions(style_ref=...)` (optional, default `None`) attaches a palette reference to every panel of a
page, so the pages match a picture drawn earlier, normally the unlettered front cover
(`render_cover(art_path=...)`). Pass an image file path, an open PIL image or a `data:` URL (each is sent as
a JPEG of at most 1536 px) or an http(s) URL (sent as it is). It is the last reference of each panel draw,
after the photo, the sheet and the previous panel, with the role `palette`: colours, line work, lighting and
texture only, never its composition, figures, poses, setting or objects. The character sheet is drawn
without it and the art check never receives it (the checker is told the brief's last reference is not
attached), so likeness, design and scene are still judged against the photo, the sheet and the earlier
panels only. A file that cannot be read draws the page without it. The pipeline does not set it.

Script fields (all optional; older `cast.json` / `script_NN.json` files still work):

| Field | Where | Meaning |
|---|---|---|
| `props[{name, look}]` | `cast.json` | Recurring objects, drawn the same in every panel and on the cover |
| `language` | `cast.json` | `he`, `en`, ... overrides reading direction (default: detected from the text) |
| `cover{scene, title, starring, footer, title_font}` | `cast.json` | Cover art direction and lettering; `title_font` is a bundled font file name or a font path |
| `dialogue[].bubble` | `script_NN.json` | Bubble kind (default `speech`) |
| `note` | `script_NN.json` panel | Dedication caption in the bottom corner |
| `sfx` | `script_NN.json` panel | Sound effect lettered by the engine over the finished art (`"BOOM!"`, `"בום!"`); never sent to the image model |

Run the tests with `pytest -q` (no network calls; fake clients).

The bundled fonts (Assistant, Rubik) are licensed under the SIL Open Font License 1.1; the licence
texts are in `assets/fonts/`.

## 📖 Documentation

### Project Structure

```
ComicCrafter/
├── src/comiccrafter/
│   ├── agents/              # Multi-agent system
│   │   ├── story_agent.py   # Story decomposition
│   │   ├── prompt_agent.py  # Image prompt generation
│   │   └── layout_agent.py  # Layout planning
│   ├── rag/                 # Character consistency
│   │   ├── character_memory.py
│   │   └── vector_store.py
│   ├── generation/          # Image generation
│   │   ├── image_generator.py
│   │   └── api_clients.py
│   ├── layout/              # Page composition
│   │   ├── panel_layout.py
│   │   └── text_overlay.py
│   ├── utils/               # Utilities
│   │   ├── config.py
│   │   └── logger.py
│   └── core.py              # Main orchestrator
├── tests/                   # Unit tests
├── evaluation/              # Evaluation tools
├── examples/                # Example scripts
├── docs/                    # Documentation
└── requirements.txt
```

### Core Components

#### 1. **StoryAgent**
Analyzes and decomposes stories into comic scenes using LLMs.

```python
from comiccrafter.agents import StoryAgent

agent = StoryAgent()
scenes = agent.decompose_story(story_text, max_scenes=6)
```

#### 2. **PromptAgent**
Generates optimized image prompts from scenes.

```python
from comiccrafter.agents import PromptAgent

agent = PromptAgent()
prompts = agent.generate_prompts(scenes, style="comic book style")
```

#### 3. **LayoutAgent**
Plans optimal panel layouts for pages.

```python
from comiccrafter.agents import LayoutAgent

agent = LayoutAgent()
layouts = agent.plan_adaptive_layout(scenes)
```

#### 4. **CharacterMemory**
Maintains character consistency using RAG.

```python
from comiccrafter.rag import CharacterMemory, Character

memory = CharacterMemory()
character = Character(
    name="Hero",
    appearance="tall warrior with silver armor",
    personality="brave and kind"
)
memory.add_character(character)
```

#### 5. **ImageGenerator**
Orchestrates image generation with consistency.

```python
from comiccrafter.generation import ImageGenerator

generator = ImageGenerator()
panel = generator.generate_panel(
    prompt="knight fighting dragon",
    character_context="tall warrior with silver armor"
)
```

## 🎯 Advanced Usage

### Custom Scenes

```python
from comiccrafter.agents.story_agent import Scene

scenes = [
    Scene(
        description="Hero enters the dark forest",
        characters=["Hero"],
        dialogue=["I must find the ancient sword"],
        action="Walking through misty trees",
        setting="Dark enchanted forest at dusk"
    ),
    # Add more scenes...
]

pages = crafter.generate_from_scenes(scenes)
```

### Custom Layouts

```python
from comiccrafter.layout import LayoutType

# Force specific layout
crafter.layout_agent.create_custom_layout(
    scene_indices=[0, 1, 2, 3],
    layout_type=LayoutType.GRID_2X2
)
```

### API Provider Selection

```python
# Use Gemini instead of Groq
crafter = ComicCrafter(llm_provider="gemini")

# Use different image model
from comiccrafter.generation import HuggingFaceClient

image_client = HuggingFaceClient(model="stabilityai/stable-diffusion-xl-base-1.0")
crafter.image_generator = ImageGenerator(image_client)
```

## 🔧 Configuration

Edit `.env` for configuration:

```env
# Required API Keys
GROQ_API_KEY=your_key
GOOGLE_API_KEY=your_key
HUGGINGFACE_TOKEN=your_token

# Optional: Model Selection
DEFAULT_LLM_MODEL=llama-3.3-70b-versatile
DEFAULT_IMAGE_MODEL=black-forest-labs/FLUX.1-dev
GEMINI_MODEL=gemini-2.0-flash-exp

# Optional: Output Settings
OUTPUT_DIR=./output
MAX_PANELS_PER_PAGE=6
IMAGE_WIDTH=512
IMAGE_HEIGHT=512

# Optional: ChromaDB
CHROMADB_PATH=./data/chroma_db
CHROMADB_COLLECTION=comic_characters
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Groq** for fast Llama 3.3 inference
- **Google** for Gemini API
- **HuggingFace** for free inference API
- **ChromaDB** for vector storage
- **LangChain** for LLM orchestration

## 🐛 Known Issues & Limitations

- Image generation may be slow on free HuggingFace tier
- API rate limits apply to free tiers
- Character consistency depends on model quality
- Best results with clear, descriptive stories

## 📧 Contact

Project Link: [https://github.com/Absirkhan/ComicCrafter](https://github.com/Absirkhan/ComicCrafter)

## 🗺️ Roadmap

- [ ] Support for more image models
- [ ] Advanced panel composition
- [ ] PDF export with multiple pages
- [ ] Web interface
- [ ] Animation support
- [ ] Style transfer options
- [ ] Multi-language support

---

**Made with ❤️ by the ComicCrafter Team**
