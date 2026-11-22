# Changelog

## 1.3.0
- Two small voice buttons (🔊 FA / 🔊 EN) on every dialogue line whose audio file exists: click to hear just that line, click again to stop.

## 1.2.0
- Tone of a dialogue line now reaches the voice: for English lines on ElevenLabs v3/v4 models it becomes an audio tag (`[whispers]`, `[annoyed]`, `[sheepishly]`, `[chuckles]`, `[playfully]`...). The mapping is `TONE_TAGS` in `tools/tts.py`.

## 1.1.0
- Video prompt per picture: a «🎬 video prompt» button next to the image prompt (stored in `prompts/video-prompts.txt`, edit, save, copy).
- Play buttons: a picture or reference that has a video (in `videos/` or `images/`, file name starting with the picture id or reference name) gets a «▶ video» button; references show a small ▶ chip.

## 1.0.0
- First public version: one-page storyboard review (images, scenario, prompts, notes, flags), bilingual FA/EN lines with speakers, in-page editing, audio playback, voice and model picker per speaker/scene (OpenRouter), `update.py` for in-place updates.
