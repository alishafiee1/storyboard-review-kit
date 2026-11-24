# Architecture

A small local web app: **plain-text files** are the database, a **tiny Python server** edits them line by line, and **one static page** shows them.
No build step, no framework, no database. Everything is meant to be read and changed with a text editor.

```
review.html            page shell (3 KB): loads the style and the scripts
tools/ui/              the page: review.css (+ css/*.css) and the scripts below
tools/*.py             the server and the tools around it
scenario/story.txt     the single source of truth for scenes, dialogue, notes, flags      (project data)
prompts/prompts.txt    one prompt per picture / reference                                  (project data)
images/ audio/ videos/ generated files; their names only carry the id (IMG001...)          (project data)
ENGINE.txt             the files `python tools/update.py` replaces in every project
```

## Python (`tools/`)

Layers, each importing only from the ones above it:

| File | Job |
|---|---|
| `kitcore.py` | paths, constants, the regexes of `story.txt`, safe read / write / replace of files, the file lock |
| `story.py` | parse `story.txt` / `prompts.txt` into plain dicts (scenes, lines, speakers, prompts); no writes |
| `flowname.py` | reads Flow file names (`IMG001_slug_<rid>_2K.jpg`), groups files into versions (rid, quality, browser copy), `kit-config.json` (`name_pattern`, `quality`), `batch_of` |
| `media.py` | what is on disk: picture versions, references, videos, voice variants, archive folders; `resolve()` is the one answer to «which file is this picture / voice line?» (page, subtitles, pack, Premiere export) |
| `edits.py` | scene / picture / per-line voice choice and out-of-date flag edits as small raw-line edits (nothing else in the file is touched) |
| `lineedits.py` | edits of single lines: change, add, delete a dialogue / action / translation line, format-issue notes |
| `promptedits.py` | edits of `prompts.txt`: save a prompt, attach references |
| `jobs.py` | slow network actions (voices, samples, subtitles) and the shared state of the running job |
| `moves.py` | moving pictures and scene markers: `move_images` (a picture = its `[IMG]` line and all it owns, also across scene headers), `scene_mark` (insert / remove / edit a header), `add_image_at`; `pin_scene` writes the old position-based line ids and scene-level voice keys under the lines first |
| `history.py` | snapshots of `story.txt` before structural edits (`.kit/history/`, last 30) and `undo` |
| `project.py` | builds the one JSON the page loads |
| `api.py` | one small function per write endpoint, registered with `@route("/api/...")` |
| `serve.py` | only the HTTP layer: GET files, GET `/api/project`, POST → `api.handle` under the file lock |
| `tts.py`, `voices.py`, `voice_test.py`, `subtitles.py` | voice making, the voice / model / tone config (`voices/voice-config.json`), samples, `.srt` files |
| `pack.py`, `premiere_check.py` | hand the project to an editor; check a Premiere XML (`--fix` repairs paths of renamed voices from `.kit/renames.tsv`; `rewrite_pathurls` is the one place that edits `<pathurl>` bytes) |
| `migrate.py` | one-time reversible migration to image-based voice names: `--dry-run` (default, Markdown report in `.kit/`), `--apply` (backup in `.engine-backup/migrate-<time>/`, renames logged in `.kit/renames.tsv`), `--undo <time>` |
| `premiere_export.py` | simple xmeml timeline from story order via `media.resolve()` (named differently from a project's own `export_premiere.py` so updates never replace it) |
| `update.py` | update a project from GitHub (only files listed in `ENGINE.txt`) |

Rules that keep it safe: the server listens on 127.0.0.1 only; dotfiles, `.py` and `.tmp` are never served; every edit re-reads the file, changes
the lines it owns and writes it back (a stale page gets a 409); before a structural edit the file is copied to `.kit/history/` (`POST /api/undo` restores it byte for byte); nothing is ever deleted (set aside = `off: yes`, archive = move to an archive folder).

## `story.txt` in one screen

```
speaker: راوی | #1565c0 | george | tone          speakers (colour, voice, default tone)
tts-model: elevenlabs/eleven-v4-turbo           default voice model
=== scene-01 | title | 0:00-0:15 ===            scene header (ids may have 2-3 digits; order = order in the file)
env: ...  fx: ...  model: ...  off: yes         scene-level keys right under the header (old files may also have voice-stale: / voice-pick: here; still read)
[IMG001]                                        a picture slot; every act / say below it, up to the next [IMG], belongs to it
status: redo | pick: <rid> (or an old file name) | off: yes | note: ... | fx: ... | image-stale: yes
act: ...   say: speaker (tone) | text   id: IMG045-1   en: translation   voice: fa=eleven-v3, en=default   voice-stale: fa   format-issue: ...
(voice: / voice-stale: = the chosen voice and the out-of-date flag of that dialogue line; the old scene-level forms are read and moved to the lines when the page writes.
id: = the stable name of the dialogue line above; its voice files are audio/<lang>/IMG045-1_<rid>.mp3 (new takes), IMG045-1.<model>.mp3 / IMG045-1.mp3 (older). New lines are named IMGnnn-k (nnn = the picture the line sits under, k = next free number, never reused); L007 and positional names are only read. Old files have no id: and
read as IMG001_2 (picture id + position in the block); the page writes that id explicitly before the first add / delete.)
```
The full writing rules for AI assistants are in `starter/skills/how-to-write-prompts-for-flow.md`.

## Write API (`api.py`; all `POST`, JSON in, JSON out)

`undo` (`.kit/history`), `image`, `voicepick`, `archive`, `restore`, `sceneoff`, `scenemove`, `addscene`, `addimage` (end of a scene, `{after}` / `{before}` a picture, or an existing `{id}`), `move` (`{ids, before | after | to_end_of_scene}`), `scenemark` (`op` = insert / remove / edit), `flag`, `line`, `add`, `speaker`, `ttsmodel`, `voicetest`,
`delete`, `issue`, `scenefx`, `vprompt`, `refs`, `prompt` (each under `/api/`). Slow ones (`jobs.SLOW`, no file lock): `subtitles`, `voices/refresh`,
`sample`, `regen`, `linevoice`. Reads: `GET /api/project`, `/api/job`, `/api/ping`. Line endpoints (`line`, `add`, `delete`, `issue`) address a line as `{image, index}` (counted from the `[IMG]` line) or the old `{scene, index}`; `voicepick`/`flag` use the line id; `regen` takes nothing (all stale lines), `image` or `scene`. Errors: 400 bad input, 409 the file changed outside the page (also: a picture or scene the request names is no longer in `story.txt`). Structural endpoints (add / delete line, addscene, addimage, move, scenemark, scenemove, sceneoff) keep a snapshot first. Picture ids have three or four digits (`IMG045`, `IMG1000`).

## The page (`tools/ui/`)

ES modules. `review.html` loads only `main.js`; every file lists what it needs with `import`. Code that used to run while the scripts loaded
(button wiring, listeners, start-up) is in each file's `boot_<name>()`, and `main.js` calls them in the old order once all modules exist.

| File | Job |
|---|---|
| `main.js` | entry: runs every `boot_*()` and gives the browser tests a handle (`window.__kit.S`) |
| `state.js` | `S`: the few values several files assign (project JSON `P`, blocks `BL`, `token`, `playing`, `START`, `RELOADS`, `cur`) |
| `core.js` | helpers (`$`, `api`, `fail`, `esc`), jobs polling, outside-click handling for open editors |
| `render.js` | draws scenes, lines, pictures and their buttons from `S.P` |
| `editors.js` | inline editors, composers, and `wire()` (attaches every button) |
| `versions.js` | picture versions, voice variants, scene menu / move / set aside / add |
| `dialogs.js` | the voice manager, picture archive and reference attach dialogs |
| `panels.js` | tabs: speakers, references, tones, lightbox, filter, stats, `reload()` |
| `player.js` | the auto-play, the floating button |
| `paper.js` | the paper-edge look |
| `css/*.css` | `base` → `scenes` → `dialogue` → `player` → `pictures` → `panels` → `polish`, imported by `review.css` |

Files import each other in both directions (e.g. `core` ↔ `panels`); that is fine because nothing is *run* at import time except self-contained
constants. Keep it that way: put new start-up code in a `boot_*()`, never at the top level of a module.
To change a shared value from several files, put it in `S` (`S.P = ...`), not in a `let` of one file.

## Tests

| Command | What |
|---|---|
| `python -m unittest discover -s tools/tests -p "test_*.py"` | 144 unit tests (text rules, migration, Premiere export, ownership / voice keys / undo, imports/exports of the page modules, old-import compatibility), in milliseconds |
| `python tools/tests/run.py` | 47 browser tests (needs `pip install playwright`) on a temporary copy of `tools/tests/fixture/`; nothing is charged |
| `python tools/tests/run.py --update-baseline` | refresh the recorded page after a deliberate change; read the diff in `tools/tests/baseline/` |

Both run on every push (`.github/workflows/tests.yml`).

## Adding a feature (checklist)

1. Data: which key in `story.txt` (or which file)? Add it to the parser in `story.py` and to the guide for AI assistants.
2. Change: an edit function in `edits.py` (raw lines only), then a route in `api.py`.
3. Page: draw it in `render.js`, wire it in `editors.js` / `versions.js` / `dialogs.js`; style in the matching `css/` file.
4. Tests: a unit test for the edit rule, a browser test for the click path; update the baseline only if the page changed on purpose.
5. Ship: new file → add to `ENGINE.txt` (a test checks this); bump `VERSION`; write `CHANGELOG.md`; commit.

## Known debts

- No formatter or linter is installed in the repo. The page scripts were pretty-printed once by a one-off tool; keep new code in the same style (2 spaces, one statement per line).
- Long HTML template strings in `render.js` / `dialogs.js` stay on single lines (about 50 lines are over 200 characters); splitting them would only add noise.
- `editors.js` is the largest page file (about 550 lines); a unit test fails at 700 lines, which is the signal to split it.

## Voice names and migration (v1.20)
- tts writes `audio/<lang>/<id>_<rid>.mp3` (8 random hex), one file per take; `audio/<lang>/voices.tsv` (`file, model, voice, tone, time`) records who made it. Without `force` a line that already has a voice of the model is skipped (old `<id>.<tag>.mp3` or a `voices.tsv` row).
- `python tools/migrate.py` (dry-run) → `--apply` → `--undo <time>`. Id of a line = `IMGnnn-k` (nnn = owner picture, k = position among its lines, bumped when taken); files keep their model tag / rid / ` (1)` suffix; the renames of every `audio/<lang>/` folder (archive included, `_samples`/`_tests` not) and the `<pathurl>` of every XML follow; a taken target name = the line keeps its old id and files (reported). Refuses with uncommitted git changes unless `--allow-dirty`; undo refuses when story/XML changed since unless `--force`.

## Versions and file names (v1.18)
- A picture version is `(base, rid)` (random 8-hex id from Flow), else `(base, slug)`, else `(base, "")`. `_1K/_2K/_4K` files of one version are one version; the best (4K, 2K, 1K, plain) is shown and exported; a browser copy ` (1)` is ignored while the original exists. `pick:` stores the rid, so a better file arriving later keeps the pick. No image file is ever renamed.
- Scans (`images/scenes`, `images/refs`, `audio/<lang>`) are recursive and skip `archive/`, `_rejected/`, `inbox/`. Voice files `<id>_<rid>.mp3`, `<id>.<model>.mp3` and `<id>.mp3` are variants of one line.
- Per project, `kit-config.json` may hold `name_pattern` (regex with the named groups `base`, `slug`, `rid`, `q`) and `quality` (best first).

