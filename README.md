# Storyboard Review Kit

**A free, single-page storyboard and review tool for AI-made videos and animations.** Keep your scenario, picture prompts, generated images and narration in plain text files, review everything on one page, edit it in the browser, and generate voice-over per speaker and scene. No database, no build step, no account: just Python and a browser.

[فارسی](README.fa.md) · [Website](https://alishafiee1.github.io/storyboard-review-kit/) · License: MIT

## What it does
- **One review page** (`review.html`): every scene with its generated image, the dialogue, the scene description and the image-generation prompt. Approve, mark for redo, add notes.
- **Plain-text project**: `scenario/story.txt` and `prompts/prompts.txt` are the only sources of truth. Edit them in the page or in any editor; git-friendly.
- **Bilingual lines** (Persian + English, right-to-left friendly), speakers with colours and voices, tone per line.
- **In-browser editing**: click a text, edit, press Enter. Clicking elsewhere saves it.
- **Voice-over**: pick a text-to-speech model and voice per speaker and scene (ElevenLabs, Gemini, Qwen, ... through one [OpenRouter](https://openrouter.ai) key), listen to a sample, rebuild only the scenes whose text changed.
- **Video prompts and clips**: every picture also has an image-to-video prompt (`prompts/video-prompts.txt`); pictures and references that already have a video get a ▶ play button.
- **Auto-play button**: a round floating button plays on from the line you last clicked (FA or EN), in that language.
- **Per-line listening**: every dialogue line with a generated voice file gets small 🔊 FA / 🔊 EN buttons to hear just that line.
- **Edit suggestions** (`fx:`): short notes per scene and per picture (zoom, fade, shake, particles, light, sound) that the AI editor follows on top of its defaults.
- **Subtitles**: one click writes `subtitles/fa.srt` and `subtitles/en.srt` from the scenario, timed by the voice files (ready to upload to YouTube).
- **Stale flags**: when you change a text or a voice, the page marks that scene's audio or image as out of date.
- **Updates without losing your work**: `python tools/update.py` replaces only the tool files; your scenario, prompts, images and audio stay untouched.

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

## Update an existing project
```bash
cd my-video
python tools/update.py          # replaces only review.html, click-for-review.bat and tools/*.py
python tools/update.py --check  # only tells you if a newer version exists
```
Replaced files are copied to `.engine-backup/` first. To add the updater to a project that does not have it yet, copy `tools/update.py` from this repository into the project's `tools/` folder once.

## Voice-over setup (optional)
Create a `.env` file next to `review.html` with one line `OPENROUTER_API_KEY=...` (it is git-ignored), then press "Refresh voice list" in the **Voices & speakers** tab, or run `python tools/voices.py`. Pick a voice per speaker and a model per scene; press "Rebuild voice" on a scene to generate it. Nothing is generated (and nothing is charged) until you press a button.

## Folder layout
| Path | What |
|---|---|
| `review.html`, `click-for-review.bat`, `tools/` | the tool (updated by `update.py`) |
| `scenario/story.txt` | scenes, dialogue, speakers, notes, flags |
| `prompts/prompts.txt` | one complete image prompt per picture or reference |
| `images/refs/`, `images/scenes/` | reference images and generated pictures (`IMG001_....jpg`) |
| `prompts/video-prompts.txt` | one image-to-video prompt per picture (the picture is the first frame) |
| `videos/` | generated clips, named after the picture (`videos/clips/IMG008_race.mp4`) |
| `voices/catalog.txt` | voices and models your key can use |
| `audio/fa`, `audio/en` | generated narration |
| `subtitles/` | `fa.srt` and `en.srt` made from the scenario |
| `skills/` | writing rules for image prompts (used by AI coding assistants) |

## Keywords
storyboard tool, AI video production, text-to-speech voice-over, scenario editor, image prompt manager, animation pipeline, Persian / Farsi RTL, OpenRouter, ElevenLabs, Google Flow, review page, YouTube video planning.

## License
[MIT](LICENSE): free for personal and commercial use.
