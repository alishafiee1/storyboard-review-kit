# Changelog

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
