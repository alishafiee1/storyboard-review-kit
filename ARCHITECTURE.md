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
| `media.py` | what is on disk: picture versions, references, videos, voice variants, archive folders |
| `edits.py` | every change as a small raw-line edit (nothing else in the file is touched) |
| `jobs.py` | slow network actions (voices, samples, subtitles) and the shared state of the running job |
| `project.py` | builds the one JSON the page loads |
| `api.py` | one small function per write endpoint, registered with `@route("/api/...")` |
| `serve.py` | only the HTTP layer: GET files, GET `/api/project`, POST → `api.handle` under the file lock |
| `tts.py`, `voices.py`, `voice_test.py`, `subtitles.py` | voice making, the voice / model / tone config (`voices/voice-config.json`), samples, `.srt` files |
| `pack.py`, `premiere_check.py` | hand the project to an editor; check a Premiere XML |
| `update.py` | update a project from GitHub (only files listed in `ENGINE.txt`) |

Rules that keep it safe: the server listens on 127.0.0.1 only; dotfiles, `.py` and `.tmp` are never served; every edit re-reads the file, changes
the lines it owns and writes it back (a stale page gets a 409); nothing is ever deleted (set aside = `off: yes`, archive = move to an archive folder).

## `story.txt` in one screen

```
speaker: راوی | #1565c0 | george | tone          speakers (colour, voice, default tone)
tts-model: elevenlabs/eleven-v4-turbo           default voice model
=== scene-01 | title | 0:00-0:15 ===            scene header (ids may have 2-3 digits; order = order in the file)
env: ...  fx: ...  model: ...  off: yes         scene-level keys right under the header
voice-stale: fa   voice-pick: IMG001_1.fa=eleven-v3      flags and the chosen voice per line
[IMG001]                                        a picture slot; its dialogue follows it
status: redo | pick: file.png | off: yes | note: ... | fx: ... | image-stale: yes
act: ...   say: speaker (tone) | text   en: translation   format-issue: ...
```
The full writing rules for AI assistants are in `starter/skills/how-to-write-prompts-for-flow.md`.

## Write API (`api.py`; all `POST`, JSON in, JSON out)

`image`, `voicepick`, `archive`, `restore`, `sceneoff`, `scenemove`, `addscene`, `addimage`, `flag`, `line`, `add`, `speaker`, `ttsmodel`, `voicetest`,
`delete`, `issue`, `scenefx`, `vprompt`, `refs`, `prompt` (each under `/api/`). Slow ones (`jobs.SLOW`, no file lock): `subtitles`, `voices/refresh`,
`sample`, `regen`, `linevoice`. Reads: `GET /api/project`, `/api/job`, `/api/ping`. Errors: 400 bad input, 409 the file changed outside the page.

## The page (`tools/ui/`)

Plain scripts that share one global scope. `review.html` loads them in this order: `paper` → `core` → `render` → `editors` → `versions` → `dialogs` → `panels` → `player`.

| File | Job |
|---|---|
| `core.js` | helpers (`$`, `api`, `fail`), shared state, jobs polling, outside-click handling for open editors |
| `render.js` | draws scenes, lines, pictures and their buttons from `P` (the project JSON) |
| `editors.js` | inline editors, composers, and `wire()` (attaches every button) |
| `versions.js` | picture versions, voice variants, scene menu / move / set aside / add |
| `dialogs.js` | the voice manager, picture archive and reference attach dialogs |
| `panels.js` | tabs: speakers, references, tones, lightbox, filter, stats, `reload()` |
| `player.js` | the auto-play, the floating button, start-up |
| `paper.js` | the paper-edge look |
| `css/*.css` | `base` → `scenes` → `dialogue` → `player` → `pictures` → `panels` → `polish`, imported by `review.css` |

Shared mutable state (assigned from more than one file): `P` (project), `BL` (blocks), `token`, `playing`, `START`, `RELOADS`, `cur`.
A unit test (`tools/tests/test_units.py`) fails if two files declare the same top-level name.

## Tests

| Command | What |
|---|---|
| `python -m unittest discover -s tools/tests -p "test_*.py"` | 18 unit tests of the text rules, in milliseconds |
| `python tools/tests/run.py` | 35 browser tests (needs `pip install playwright`) on a temporary copy of `tools/tests/fixture/`; nothing is charged |
| `python tools/tests/run.py --update-baseline` | refresh the recorded page after a deliberate change; read the diff in `tools/tests/baseline/` |

Both run on every push (`.github/workflows/tests.yml`).

## Adding a feature (checklist)

1. Data: which key in `story.txt` (or which file)? Add it to the parser in `story.py` and to the guide for AI assistants.
2. Change: an edit function in `edits.py` (raw lines only), then a route in `api.py`.
3. Page: draw it in `render.js`, wire it in `editors.js` / `versions.js` / `dialogs.js`; style in the matching `css/` file.
4. Tests: a unit test for the edit rule, a browser test for the click path; update the baseline only if the page changed on purpose.
5. Ship: new file → add to `ENGINE.txt` (a test checks this); bump `VERSION`; write `CHANGELOG.md`; commit.

## Known debts

- The page scripts are plain scripts, not ES modules. Converting needs the 7 shared variables above turned into one `state` object and every cross-file call made an explicit import; the files also depend on each other in both directions (e.g. `core` ↔ `panels`), so it is a rewrite, not a move.
- The JS files were pretty-printed once by a tool; there is no formatter or linter in the repo yet.
- `edits.py` is the largest file (about 500 lines); scene operations and line operations could be split.
