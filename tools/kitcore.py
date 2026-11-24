# -*- coding: utf-8 -*-
"""Shared basics of the review server: project paths, constants, the line patterns of story.txt, and safe reading / writing of the plain-text files."""
import os, re, threading, time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


STORY = os.path.join(ROOT, "scenario", "story.txt")


PROMPTS = os.path.join(ROOT, "prompts", "prompts.txt")


VPROMPTS = os.path.join(ROOT, "prompts", "video-prompts.txt")  # one image-to-video prompt per picture (optional file)


PORT = int(os.environ.get("PORT", "8765"))


IDLE = float(os.environ.get("IDLE_SECONDS", "90"))


MARKS = {"", "ok", "redo", "anim"}


LANGS = ("fa", "en")


IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


VID_EXT = (".mp4", ".webm", ".mov", ".m4v")


LOCK = threading.Lock()


HEADER = re.compile(r"^=== (scene-\d{2,3}) \| (.*?) \| (.*?) ===$")


MARKER = re.compile(r"^\[(IMG\d{3})\]$")


KEYLINE = re.compile(r"^([a-z][a-z-]*):\s?(.*)$")


PHEADER = re.compile(r"^=== ([A-Za-z0-9_]+) ===$")


SPEECH = ("say",)


SPK = re.compile(r"^speaker:\s*(.*?)\s*\|\s*(#[0-9a-fA-F]{6})\s*(?:\|\s*([A-Za-z0-9_.:-]*)\s*)?(?:\|\s*(.*?)\s*)?$")


PALETTE = ["#1565c0", "#ef6c00", "#2e7d32", "#8e24aa", "#c62828", "#00838f", "#6d4c41", "#ad1457", "#558b2f", "#4527a0", "#f9a825", "#37474f"]


VOICE_LIST = ["george", "charlie", "sarah", "adam", "alice", "bella", "bill", "brian", "callum", "chris", "daniel", "eric", "harry", "jessica", "laura", "liam", "lily", "matilda", "river", "roger", "will"]


CONTENT = ("act",) + SPEECH


DEFAULT_MODEL = "elevenlabs/eleven-v4-turbo"


MODEL_RE = re.compile(r"[A-Za-z0-9_./:-]{1,80}")


VOICE_RE = re.compile(r"[A-Za-z0-9_.:-]{1,60}")


HIDDEN = re.compile(r"(^|/)\.|\.(py|tmp)$")


def read_lines(path):
    try:
        return open(path, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    except OSError:
        return []


def replace_file(tmp, path):
    """os.replace that waits a moment when Windows says the target is open (an editor, a backup tool or an antivirus reading it)."""
    for _ in range(40):
        try:
            return os.replace(tmp, path)
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, path)


def write_lines(path, lines):
    text = "\n".join(lines).rstrip("\n") + "\n"
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8", newline="\n").write(text)
    replace_file(tmp, path)


class Conflict(Exception):
    pass
