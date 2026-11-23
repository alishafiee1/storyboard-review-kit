# Changelog

## 1.8.0
- `review.html` is now a small page shell; its style and code moved, unchanged, to `tools/ui/` (`review.css` and six scripts: paper, core, render, editors, panels, player). The page looks and behaves exactly as before (checked against a recorded copy of the old page).
- The local server no longer serves hidden files (`.env`, `.git`, `.engine-backup`), `*.py` sources or `*.tmp` files. Before, `.env` could be downloaded from 127.0.0.1.
- Fix: on Windows a save could fail when another program (an editor, an antivirus) had the file open at that moment; saves now wait for a moment and retry.
- New end-to-end tests in `tools/tests/` (22 browser tests on a throw-away project; not part of the engine): `python tools/tests/run.py` (needs `pip install playwright`).

## 1.7.0
- One config file for voices: `voices/voice-config.json` (models, voices per model, tones). Built automatically from an existing `voices/catalog.txt` the first time; «Refresh voice list» merges the API list into it and keeps your own fields (accent, gender, note, tested, tags). `catalog.txt` stays as the raw list.
- Tones come from that file (`fa` name, `match` aliases, English `tag`): `tools/tts.py` no longer has a built-in list, sends up to 2 tags per line, and warns (page alert + terminal) about a tone that is not in the file instead of silently sending nothing. A tone with an empty tag (e.g. «عادی») is known and sends nothing.
- Page: tone menu lists the config tones; unknown tones are red (line, speakers tab, banner); the scene model menu marks models that lack a speaker's voice.
- Fix: a voice name with `-` or `.` (Deepgram, AssemblyAI, MAI voices…) broke the `speaker:` line and could not be saved from the page.
- New `tools/voice_test.py`: makes the same sentence with chosen models, voices and tones (shows the cost first, nothing is made without `--yes`); `audio/_tests/index.html` lets you mark 👍 / 👎, saved into the config.

## 1.6.2
- Floating play button redrawn: crisp SVG play/pause icons exactly centered, soft gradient, press feedback and a pulse while playing.
- Page CSS reformatted (one declaration per line, shared colour tokens); visible keyboard focus rings; larger invisible hit areas for the small buttons; tiny 11px labels raised to 12px; reduced-motion support; aria-labels on icon-only buttons.
- Fix: auto-play left timers running after each pause or clip (small leak), now cleaned up.

## 1.6.1
- Subtitle cues end where a sentence ends (short sentences share a cue), instead of breaking mid-sentence.

## 1.6.0
- Subtitles: «📝 زیرنویس» button (or `python tools/subtitles.py`) writes `subtitles/fa.srt` and `subtitles/en.srt` from the scenario; each line lasts as long as its voice file (estimated from the text when there is none yet), with the same gaps as the auto-play.

## 1.5.0
- Edit suggestions: an `fx:` line for the whole scene (under the scene header) and for each picture (under its marker). Edited in the page with «🎬 ادیت صحنه» / «🎬 ادیت». The starter skill lists the shared words and the default edit style (illustrated documentary, intensity 3).

## 1.4.0
- A round floating play button replaces the per-block «play from here» buttons. It continues from the line whose 🔊 FA / 🔊 EN button you clicked last, in that language; with no click yet it starts from the beginning (English if the English box is ticked, else Persian). Pausing and pressing it again resumes from the same line.

## 1.3.0
- Two small voice buttons (🔊 FA / 🔊 EN) on every dialogue line whose audio file exists: click to hear just that line, click again to stop.

## 1.2.0
- Tone of a dialogue line now reaches the voice: for English lines on ElevenLabs v3/v4 models it becomes an audio tag (`[whispers]`, `[annoyed]`, `[sheepishly]`, `[chuckles]`, `[playfully]`...). The mapping is `TONE_TAGS` in `tools/tts.py`.

## 1.1.0
- Video prompt per picture: a «🎬 video prompt» button next to the image prompt (stored in `prompts/video-prompts.txt`, edit, save, copy).
- Play buttons: a picture or reference that has a video (in `videos/` or `images/`, file name starting with the picture id or reference name) gets a «▶ video» button; references show a small ▶ chip.

## 1.0.0
- First public version: one-page storyboard review (images, scenario, prompts, notes, flags), bilingual FA/EN lines with speakers, in-page editing, audio playback, voice and model picker per speaker/scene (OpenRouter), `update.py` for in-place updates.
