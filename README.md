# Storyboard Review Kit

**A free, single-page storyboard and review tool for AI-made videos and animations.** Keep your scenario, picture prompts, generated images and narration in plain text files, review everything on one page, edit it in the browser, and generate voice-over per speaker. No database, no build step, no account: just Python and a browser.

[فارسی](README.fa.md) · [Website](https://alishafiee1.github.io/storyboard-review-kit/) · [Workflow](WORKFLOW.md) · [Changelog](CHANGELOG.md) · License: MIT

## The workflow in one look
The kit tidies the whole path of an AI video, and your AI coding assistant (such as Claude Code) learns from the guide inside the project how to work with it:

**script → picture prompts → pictures in Flow → review → voices → subtitles and editor hand-over**

1. Give your script to the AI to tidy and enrich.
2. Make an empty folder, tell the AI to create the kit there and rewrite the script in the kit's format.
3. Read and edit the story on the review page; feed the prompts to Flow; the pictures file themselves.
4. Stop on the best version, flag problems, and build the voices.

The full guide, with a ready-made prompt for the AI, is in [WORKFLOW.md](WORKFLOW.md).

## What it does
- **One scrolling review page** (`review.html`): every picture is a "page" of a long list (picture on one side, its dialogue on the other). Scroll through the story, or use the ‹ › buttons and the ← → keys. A gallery of all pictures lets you drag to reorder. On phones it is one picture per screen with a bottom action bar.
- **Everything about a picture sits under it**: flag, note and edit advice, image prompt, video prompt.
- **Plain-text project**: `scenario/story.txt` and `prompts/prompts.txt` are the only sources of truth. Edit them in the page or in any editor; git-friendly.
- **Picture-based model**: a scene is only a marker line; every picture (`[IMG045]`) owns its dialogue lines (`IMG045-1`, `IMG045-2`, ...). Move pictures or scene markers and no file is renamed.
- **Bilingual lines** (Persian + English, right-to-left friendly), coloured speakers, a tone per line.
- **Voice-over**: choose a text-to-speech model and voice per speaker and per line (ElevenLabs, Gemini, Qwen, ... through one [OpenRouter](https://openrouter.ai) key); several takes per line, you keep the one you stop on; only changed lines are rebuilt.
- **Versions**: several pictures for one shot sit side by side (Flow's random ids, 2K/4K). The version you stop on is the approved one.
- **Automatic downloads**: when the review server runs it watches your `Downloads` folder and moves Flow files that belong to this project into `images/scenes/bNN/` or `images/refs/` by itself (turn off with `"watch_downloads": false` in `kit-config.json`). Odd files go to `inbox/`.
- **Archive**: the archive icon under a picture sends the shown version to `images/archive/` (nothing is deleted); the archive icon next to it opens a popup of the archived versions to browse and bring back.
- **Undo**: structural changes (add, delete, move) are snapshotted in `.kit/history`; press **Ctrl+Z** or the undo icon in the top bar.
- **Video prompts and clips**, **edit advice** (`fx:`), **subtitles** (`fa.srt` / `en.srt`, timed by the voice files), **batch prompts** for Flow (`python tools/batch.py b05`).
- **Premiere hand-over**: `python tools/premiere_export.py` writes a timeline; `python tools/pack.py` zips the project for your editor.
- **Safe updates**: `python tools/update.py` replaces only the tool files (and the AI guide); your scenario, prompts, images and audio are never touched.

## Quick start (Windows, macOS, Linux)
Needs Python 3.9+ (no packages to install). `ffmpeg` is needed only for a few voice models that answer raw audio.

```bash
# 1) create a project folder from the latest version
python -c "import urllib.request as u;exec(u.urlopen('https://raw.githubusercontent.com/alishafiee1/storyboard-review-kit/main/tools/update.py').read())" --new my-video

# 2) open the review page
cd my-video
python tools/serve.py        # Windows: double-click click-for-review.bat
```
Then open http://127.0.0.1:8765/review.html. The server stops by itself about 90 seconds after you close the page.

## Add it to an existing project
Copy `tools/update.py` from this repository into the project's `tools/` folder once, then run it there:
```bash
cd my-video
python tools/update.py          # replaces review.html, click-for-review.bat, tools/ and the AI guide in skills/
python tools/update.py --check  # only tells you if a newer version exists
```
Replaced files are copied to `.engine-backup/` first. If the project is in the old format, the updater says so: run `python tools/migrate.py` (a dry run, nothing changes), then `python tools/migrate.py --apply` if the report looks right (it makes a backup and can be undone with `--undo`).

## Working with an AI assistant
Every project carries a short guide for AI coding assistants: `skills/how-to-write-prompts-for-flow.md` (the rules, the `story.txt` format, file naming, the review loop) plus a `CLAUDE.md` that points to it and holds your project's own rules (style, narrator tone, characters). The guide is an engine file, so `update.py` keeps it current. Tell your assistant to read `CLAUDE.md` first.

## Settings and voice-over (optional)
Open the menu (top right) → **Settings** and paste your OpenRouter key (it is saved to `.env` next to the project, git-ignored and never shown again; a "test key" button checks it). The same panel switches the Downloads watcher on or off and changes its folder. Then open **Voices & speakers**, pick a voice per speaker, and build the voices of a line or scene. The last menu row, **Help**, shows short cards of how the kit works with a "more" button each. Nothing is generated (and nothing is charged) until you press a button. Tones (the Persian word after a speaker's name, e.g. `علی (مرموز)`) map to English audio tags in `voices/voice-config.json`; `python tools/voice_test.py` shows which models, voices and tones work (it shows the cost first; add `--yes` to generate).

## Folder layout
| Path | What |
|---|---|
| `review.html`, `click-for-review.bat`, `tools/`, `skills/how-to-write-prompts-for-flow.md` | the tool (updated by `update.py`) |
| `scenario/story.txt` | scenes, dialogue, speakers, notes, flags |
| `prompts/prompts.txt`, `prompts/video-prompts.txt` | one complete image / image-to-video prompt per picture |
| `images/scenes/bNN/`, `images/refs/<KIND>/` | pictures (10 per batch folder) and references |
| `inbox/` | loose files for the AI to sort |
| `audio/fa`, `audio/en`, `voices/` | narration, voice models and tones |
| `videos/clips/`, `subtitles/`, `premiere/` | clips, subtitles, editor hand-over |
| `.kit/` | undo history and import logs (do not edit) |

## Development
The code map, the file format, the API and a checklist for new features are in [ARCHITECTURE.md](ARCHITECTURE.md). The page is `review.html` (shell) + `tools/ui/` (style and scripts) + `tools/*.py` (server, voices, subtitles). Unit tests: `python -m unittest discover -s tools/tests -p "test_*.py"`. Browser tests: `pip install playwright`, then `python tools/tests/run.py` (they run on a temporary copy of a small project; nothing is generated or charged). After changing the page on purpose, refresh the recorded page with `python tools/tests/run.py --update-baseline` and read the diff in `tools/tests/baseline/`.

## Keywords
storyboard tool, AI video production, text-to-speech voice-over, scenario editor, image prompt manager, animation pipeline, Persian / Farsi RTL, OpenRouter, ElevenLabs, Google Flow, review page, YouTube video planning.

## License
[MIT](LICENSE): free for personal and commercial use.
