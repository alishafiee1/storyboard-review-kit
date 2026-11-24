# Changelog

## 1.15.1
- `python tools/update.py` no longer puts `audio/` in a project's `.gitignore` (voices belong in git). It now adds the kit's ignore rules once, under a marker comment, and never touches the file again, so lines a project removed or added stay as they are. The rules: `.env`, `.engine-backup/`, `__pycache__/`, `*.tmp`, `graphify-out/`, `videos/`, `*_renders/`, video and archive file types (`*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.rar *.zip *.7z`), `archive/`, `audio/_samples/`, `audio/_tests/`. The new-project `.gitignore` is the same list. Projects updated by an older version keep an `audio/` line if they have one: delete it by hand.

## 1.15.0
- The page scripts are now ES modules (`main.js` is the only script; `state.js` holds the shared values; start-up code lives in `boot_*()` functions). Nothing changes on screen.
- `edits.py` split into `edits.py`, `lineedits.py` and `promptedits.py`.
- Unit tests now check that every import has a matching export, every file is reached from `main.js`, and no name is exported twice (22 unit tests).

## 1.14.0
- Internal tidy-up, no change in what the page does. `tools/serve.py` (1400 lines) is now small modules: `kitcore`, `story`, `media`, `edits`, `jobs`, `project`, `api` (one small function per endpoint) and a thin `serve.py`. The page scripts were pretty-printed (readable lines) and the style was split into `tools/ui/css/*.css`.
- New `ARCHITECTURE.md` (code map, `story.txt` format, API, how to add a feature), 18 fast unit tests, and a GitHub Actions workflow that runs the unit and browser tests on every push.

## 1.13.0
- `tools/pack.py`: one zip for an editor or a friend (kit, scenario, pictures, voices, Premiere package) without output videos, previews, renders, archives, test audio and `.env`; `--clips` adds `videos/clips/`. A Premiere XML is checked first.
- `tools/premiere_check.py`: every file a Premiere XML points to must exist; absolute paths are reported (relative paths are the rule).
- New projects get a `.gitignore` (videos, renders, archives, `.env`). The guide has a new section about the Premiere package: `premiere/` with the XML, notes and generated media only; pictures and voices are not copied, the XML points at them with relative paths.

## 1.12.0
- «📎 اتچ» next to a picture's references opens a gallery of the project's reference pictures; tick or untick and save. Only the `[REFS TO ATTACH: ...]` line at the top of that prompt is rewritten (created when the prompt does not exist yet) and the picture is marked stale. Only reference names that exist on disk or that another prompt already uses are accepted.
- 1 new test (34 in total).

## 1.11.0
- Voice manager per line: a small 🎙 button next to the flag opens a dialog where you listen to every voice of the line, choose the final one, archive a voice, bring an archived one back, and make a new voice with a model you pick (Persian, English or both). The new voice sits next to the old ones and becomes the chosen one. The per-scene model picker is not needed any more.
- Archive instead of delete: «🗄 آرشیو» under a picture moves that version to `images/archive/`; archived voices go to `audio/<lang>/archive/`; «📂 آرشیو» brings them back. An archived file that was the chosen one loses its `pick:` / `voice-pick:`. Making the same model's voice again moves the older file to the archive first.
- 3 new tests (33 in total).

## 1.10.0
- Cleaner page: a single «⋯» menu per scene (move up/down, set aside, new picture in this scene, new scene after this one) instead of a row of small buttons. The «new picture» item is new: it adds an empty `[IMG###]` slot at the end of an existing scene.
- Removed: the whole-scene edit box, the voice «updated»/count chips and the per-scene voice-model picker (a «make voices» button shows only when the scene's voice is out of date), and the ✅ approve / 🔁 redo buttons under pictures (choosing a version with ◀ ▶ is the approval).
- The note under a picture is now an always-visible input; «پرامپت» became «پرامپت تصویر»; «کنار بذار» sits next to the picture name.
- New test for the menu and the new-picture button (30 tests in total).

## 1.9.0
- Several pictures for one shot (any file name that starts with the id, random suffixes included): ◀ ▶ browse them; the one you stop on is saved as `pick:` and counts as approved (the ✅ button now chooses the shown picture). No `pick:` = the newest file.
- Several voices for one line: `tools/tts.py` writes `audio/<lang>/<id>.<model>.mp3` (never over another model's file; the old `<id>.mp3` is the `default`). A small ‹1/3› button next to 🔊 FA / EN switches voice and plays it; the last one you stop on is saved as `voice-pick:` under the scene header and is the final voice (also used by the auto-play and the subtitles). A freshly made voice becomes the chosen one.
- Scenes: ▲ ▼ move a scene (only the block moves; ids and file names stay), 🚫 sets a scene or a picture aside (`off: yes`, text and files stay; set-aside scenes are skipped by play, subtitles and new voices), «＋ صحنهٔ جدید» adds a scene with 0 to 12 empty picture slots. Scene numbers on the page follow the order; scene ids may now have 3 digits.
- 7 new browser tests (29 in total).

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
