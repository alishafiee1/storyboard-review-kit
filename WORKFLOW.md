# Workflow: from a script to a finished video

[فارسی](WORKFLOW.fa.md) · [README](README.md)

This guide shows how to make an AI video step by step once the kit is installed. The AI coding assistant (such as Claude Code) does the heavy lifting; you decide and review.

## What you need
- Python 3.9 or newer
- An AI coding assistant that can work in a folder (such as Claude Code)
- An image tool (the guide is written for Google Flow)
- Optional: an OpenRouter key for voice-over

## The cycle at a glance
1. **Script:** find or write the idea or first draft and give it to the AI to tidy and enrich: scenes, dialogue, speakers, a visual description per scene.
2. **New folder:** make an empty project folder and open your AI assistant in it.
3. **Bring in the kit:** tell the assistant to create the kit and rewrite the script in the kit's format (a ready-made prompt is below).
4. **Review the text:** run `python tools/serve.py` (Windows: double-click `click-for-review.bat`) and open the review page. Scroll through the story and edit text in place.
5. **Make the images:** menu → "Copy batch prompts" (10 pictures at once), paste into Flow, attach the references, generate and download. Files file themselves into the right folders; put odd files in `inbox/` and ask the assistant to sort them.
6. **Review the images:** stop on the best version (that is the approval). Mark problems with the flag or a note and tell the assistant "read the notes and fix the prompts". Regenerate until it is right.
7. **Voice-over:** menu → **Settings**, paste your OpenRouter key. Open **Voices & speakers**, pick a voice per speaker, build a line or a scene and listen. Nothing is generated or charged until you press a button.
8. **Video and edit advice (optional):** write an image-to-video prompt and edit advice (`fx:`) per picture.
9. **Hand-over:** build subtitles, `python tools/premiere_export.py` for a Premiere timeline and `python tools/pack.py` for a zip for your editor.

When something goes wrong, **Ctrl+Z** undoes the last structural change (add, delete, move). To get a new kit version: `python tools/update.py` (your work is never touched).

## A ready-made prompt for the AI assistant
Copy it and give it to the assistant inside the empty project folder:

```text
This folder is empty. Create the Storyboard Review Kit in it with:
python -c "import urllib.request as u;exec(u.urlopen('https://raw.githubusercontent.com/alishafiee1/storyboard-review-kit/main/tools/update.py').read())" --new .
Then read CLAUDE.md and skills/how-to-write-prompts-for-flow.md. Rewrite the script below as scenario/story.txt (scenes, an [IMG###] marker per picture, speakers and dialogue), write the painting style into skills/image-style-skill.txt and put one complete prompt per picture into prompts/prompts.txt. Delete nothing and generate nothing; tell me at the end what is ready.

Script:
<paste your script here>
```

## Notes
- The scenario and prompts are plain text: edit them in any editor and keep them in git.
- The assistant learns how the project works from `CLAUDE.md` and the guide in `skills/`; put your project's own rules (narrator tone, characters, style) in `CLAUDE.md`.
- Old project? Run `python tools/migrate.py` (it only reports first).
