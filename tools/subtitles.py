# -*- coding: utf-8 -*-
"""Subtitles from the scenario: subtitles/fa.srt and subtitles/en.srt (upload them to YouTube as caption files).
Usage:  python tools/subtitles.py        (or the «📝 زیرنویس» button on the review page)
Timing follows the review page's auto-play: each line lasts as long as its voice file, 0.26 s between lines, 0.38 s after a block,
3.2 s for a block with no dialogue. A line with no voice file yet gets a length estimated from its text (reported).
The timing is provisional until the final edit exists: run it again after the edit if shot lengths change."""
import os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serve import ROOT, audio_path, clean_spoken, story_scenes  # noqa: E402

LINE_GAP, BLOCK_GAP, SILENT = 0.26, 0.38, 3.2  # same as the page's auto-play
CPS = {"fa": 13.0, "en": 15.0}  # characters per second, only for lines without a voice file
MAX_CHARS = 42  # per subtitle line; two lines per cue at most
OUT = os.path.join(ROOT, "subtitles")


def duration(path):
    if not shutil.which("ffprobe"):
        return None
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        return None


def wrap(text):
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > MAX_CHARS:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def cues_of(text):
    """Cues of at most two lines of MAX_CHARS characters, never inside a word; a cue ends where a sentence ends
    (short sentences that fit together share one cue)."""
    out, cur = [], []
    for sent in re.split(r"(?<=[.!?؟…])\s+", text.strip()):
        lines = wrap(sent)
        if cur and len(wrap(" ".join(cur + [sent]))) <= 2:  # still fits in the open cue
            cur.append(sent)
            continue
        if cur:
            out.append("\n".join(wrap(" ".join(cur))))
            cur = []
        if len(lines) <= 2:
            cur = [sent]
        else:
            out += ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]
    if cur:
        out.append("\n".join(wrap(" ".join(cur))))
    return out


def stamp(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def build(lang):
    t, cues, estimated = 0.0, [], []
    for sc in story_scenes():
        if sc["off"]:
            continue
        for b in sc["blocks"]:
            lines = [(it, clean_spoken(it["fa"] if lang == "fa" else (it["en"] or ""))) for it in b["items"] if it["k"] == "say"]
            lines = [(it, x) for it, x in lines if x]
            if not lines:
                t += SILENT
                continue
            for it, text in lines:
                f = audio_path(lang, it["id"], sc["voice_pick"])  # the voice the user chose (else the old default or the newest)
                d = duration(f) if f else None
                if d is None:
                    d = len(text) / CPS[lang] + 0.3
                    estimated.append(it["id"])
                parts = cues_of(text.replace("\n", " "))
                total, s = sum(len(p) for p in parts) or 1, t
                for p in parts:  # long lines: time shared by length
                    dd = d * len(p) / total
                    cues.append((s, s + dd, p))
                    s += dd
                t += d + LINE_GAP
            t += BLOCK_GAP
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, lang + ".srt")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for n, (a, b, x) in enumerate(cues, 1):
            fh.write(f"{n}\n{stamp(a)} --> {stamp(b)}\n{x}\n\n")
    return dict(file=os.path.relpath(path, ROOT).replace("\\", "/"), cues=len(cues), length=round(t, 1), estimated=estimated)


def make_all():
    res = {lg: build(lg) for lg in ("fa", "en")}
    est = sum(len(r["estimated"]) for r in res.values())
    msg = " · ".join(f"{r['file']}: {r['cues']} تکه، {int(r['length'] // 60)}:{int(r['length'] % 60):02d}" for r in res.values())
    if est:
        msg += f" · زمان {est} خط بدون فایل صدا تخمینی است"
    return dict(ok=True, message=msg, result=res)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(make_all()["message"])
