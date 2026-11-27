# Architecture & Technical Truth

A lightweight, local-first web application for reviewing and assembling animation storyboards: **plain-text files** act as the database, a **minimal Python server** edits them line by line under file locking, and **one static web page** provides an interactive sketchbook interface without build steps or external frameworks.

```
review.html                   page shell (loads ES modules and CSS)
tools/ui/                     frontend ES modules and paper theme styles
tools/*.py                    local server, endpoints, and helpers
scenario/story.txt            single source of truth for scenes, dialogue, notes (story book)
scenario/reference.txt        single source of truth for reference items (refs book)
prompts/prompts.txt           prompts for images and references
images/ audio/ videos/        generated media assets identified by item IDs (IMG001..., CH_MIMO...)
ENGINE.txt                    strict allow-list of runtime engine files copied by tools/update.py
```

---

## 1. Multi-Book Architecture (`story` vs `refs`)

The system operates across two book modes:
- `book = "story"`: Storyboard scenes, sequential shots (`[IMG001]`), dialogue lines, notes, and episode structure.
- `book = "refs"`: Character, location, prop, and style references (`[CH_MIMO]`, `[LOC_CAVE]`).

### `BOOK_RULES` in `tools/kitcore.py`
Centralized dictionary governing naming, matching, paths, and snapshot history for each book:

```python
BOOK_RULES = {
    "story": {
        "section_re": re.compile(r"^scene-\d{2,3}$"),
        "section_prefix": "scene",
        "header_re": re.compile(r"^=== (scene-\d{2,3}) \| (.*?) \| (.*?) ===$"),
        "item_re": re.compile(r"^IMG\d{3,4}$"),
        "marker_re": re.compile(r"^\[(IMG\d{3,4})\]$"),
        "images_rel": "images/scenes",
        "images_dir": os.path.join(ROOT, "images", "scenes"),
        "history_dir": os.path.join(ROOT, ".kit", "history"),
    },
    "refs": {
        "section_re": re.compile(r"^ref-\d{2,3}$"),
        "section_prefix": "ref",
        "header_re": re.compile(r"^=== (ref-\d{2,3}) \| (.*?) \| (.*?) ===$"),
        "item_re": re.compile(r"^(?!IMG\d{3,4}$)[A-Z][A-Z0-9_]{1,40}$"),
        "marker_re": re.compile(r"^\[((?!IMG\d{3,4}\b)[A-Z][A-Z0-9_]{1,40})\]$"),
        "images_rel": "images/refs",
        "images_dir": os.path.join(ROOT, "images", "refs"),
        "history_dir": os.path.join(ROOT, ".kit", "history-refs"),
    },
}
```

Key invariants:
- `scan_images(book="story")` in `tools/media.py` defaults to `"story"` for full backward compatibility.
- **Speakers:** Global speaker definitions (`speaker: Name | #color | voice | tone`) remain in `scenario/story.txt` and are shared across both story and refs modes.
- **Thumbnail scene:** `scene-00` guards (for cover images) are strictly scoped to `book == "story"` (ref sections never trigger `scene-00` restrictions).

---

## 2. Server & Backend Layers (`tools/*.py`)

All HTTP operations run on `127.0.0.1`. Writes are performed line-by-line under a file lock (`kitcore.LOCK`).

| Module | Responsibility |
|---|---|
| `kitcore.py` | Paths, regex patterns (`BOOK_RULES`, `KEYLINE`, `LINE_ID`), file locking, safe atomic read/write (`replace_file_atomically`). |
| `story.py` | Parses `story.txt` or `reference.txt` into plain dictionaries; extracts scenes, items, dialogue, notes, speakers. Read-only. |
| `flowname.py` | Parses Flow filename patterns (`IMG001_slug_<rid>_2K.jpg`), extracts version ID (`rid`), quality (`2K`, `4K`), and slug. |
| `media.py` | Scans disk recursively for picture versions, references, audio takes; `resolve()` determines the best asset for playback/export. |
| `edits.py` | Edits item status, version picks (`pick:`), flags, scene attributes as minimal raw-line edits. Returns 409 on stale file hash. |
| `lineedits.py` | Edits dialogue and action lines (`line`, `add`, `delete`, `issue`). |
| `moves.py` | Structural moves: moving pictures across scenes, inserting/removing scene headers (`scenemark`), `add_image_at`, and moving line blocks. |
| `history.py` | Pre-edit snapshots (`.kit/history/` for story, `.kit/history-refs/` for refs, keeping last 30 snapshots) and byte-for-byte undo. |
| `project.py` | Assembles the complete JSON state for the client (`GET /api/project?book=...`). |
| `api.py` | Dispatches POST write endpoints registered with `@route("/api/...")`. |
| `serve.py` | HTTP server (`127.0.0.1`), static file serving, routes requests through `api.handle`. |
| `tts.py`, `voices.py` | OpenRouter audio synthesis, tone configurations, multi-take variants (`audio/<lang>/<lineid>_<rid>.mp3`). |
| `watch.py` | Downloads watcher: moves matching Flow files into `images/scenes/bNN/` or `images/refs/` without overwriting. |
| `settings.py` | Configuration panel, OpenRouter API key management (stored in `.env`, never exposed to client). |
| `update.py` | Safe engine updater copying only paths listed in `ENGINE.txt`. |

### Critical Endpoints
- `/api/moveline`: Moves a dialogue or action line within or across pictures while preserving its stable `id:` (e.g. `IMG045-1`) and attached voice files.
- `/api/imagebulk`: Executes atomic batch updates across multiple selected images (e.g., mark ok, redo, or set aside) with a single undo snapshot.
- `/api/undo`: Reverts the active book to the immediate preceding snapshot in `.kit/history/` or `.kit/history-refs/`.

---

## 3. Frontend Architecture (`tools/ui/`)

ES modules loaded directly by `review.html` via `main.js`. No build step or bundler.

- **Sketchbook UI Shell:** Two-page spread layout with paper textures, washi tape marks, and Persian-friendly typography (bundled Vazirmatn woff2).
- **Per-picture toolbar:** Actions on each shot (`figure.shot > .pic-bar`) allow setting redo, editing prompt, opening note popover, or setting aside directly.
- **Per-scene menu:** Scene-level actions (edit title/env/fx, add picture, move scene, set scene off) live in a dedicated `⋯` menu next to `.slabel`.
- **Unified playback speed control:** Replaced legacy speed panels with a shared `[−] 1× [+]` stepper beside the transport bar (0.5×–2.0× in 0.25 steps), persisted in `localStorage` and controlling `playbackRate` across audio elements.
- **Scene-grouped gallery:** The gallery divides cards by scene headers with end-of-scene drop zones, thumbnail-grid move pickers, and `Alt+Arrow` keyboard reordering.
- **Paper dialogs:** Native browser `alert()` and `confirm()` dialogs are completely replaced by paper modal overlays (`tools/ui/dialogs.js`).

---

## 4. `ENGINE.txt` Boundary

`ENGINE.txt` defines the exact allow-list of runtime files that `tools/update.py` distributes to storyboard projects.
- **Strict Invariant:** Development files, testing scripts, `AGENTS.md`, and the `rodo/` directory must **never** be added to `ENGINE.txt`.
- Every runtime frontend or backend script needed by projects must be registered in `ENGINE.txt`.
