# -*- coding: utf-8 -*-
"""Snapshots of scenario/story.txt for «undo»: before every structural edit (add / delete a line, add a picture or scene, move or set aside a scene)
the whole file is copied, byte for byte, to .kit/history/ (the last 30 are kept). undo() puts the newest copy back and removes it from the history.
The file name tells what is needed to judge a restore: <time>_<what was done>_<first 8 hex of the sha1 of story.txt right after that edit>.txt.
The folder starts with a dot, so the server never serves it, and it carries its own .gitignore (projects updated from older versions need nothing)."""
import datetime, hashlib, os, re
from kitcore import Conflict, ROOT, STORY, replace_file

DIR = os.path.join(ROOT, ".kit", "history")
UNDONE = os.path.join(ROOT, ".kit", "undone")  # what the file looked like just before an undo (so an undo can itself be taken back by hand)
KEEP = 30
NAME = re.compile(r"^(\d{8}-\d{6}-\d{6})_([a-z]+)_([0-9a-f]{8})\.txt$")


def read_story():
    """The raw bytes of story.txt, or None when the project has none."""
    try:
        return open(STORY, "rb").read()
    except OSError:
        return None


def digest(data):
    return hashlib.sha1(data).hexdigest()[:8]


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    open(tmp, "wb").write(data)
    replace_file(tmp, path)


def keep_out_of_git(folder):
    mark = os.path.join(folder, ".gitignore")
    os.makedirs(folder, exist_ok=True)
    if not os.path.exists(mark):
        open(mark, "w", encoding="utf-8", newline="\n").write("# snapshots are a safety net on this computer, not part of the project\n*\n")


def entries():
    """[{id, label, time, after}] oldest first (id = file name without .txt)."""
    out = []
    for f in sorted(os.listdir(DIR)) if os.path.isdir(DIR) else []:
        m = NAME.match(f)
        if m:
            out.append(dict(id=f[:-4], label=m.group(2), time=m.group(1), after=m.group(3)))
    return out


def trim(folder):
    names = sorted(f for f in os.listdir(folder) if f.endswith(".txt"))
    for f in names[:-KEEP]:
        os.remove(os.path.join(folder, f))


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def record(label, before):
    """Call after an edit that started from the bytes `before`: when the file really changed, keep `before` as a snapshot."""
    after = read_story()
    if before is None or after is None or after == before:
        return None
    name = "%s_%s_%s.txt" % (stamp(), re.sub(r"[^a-z]", "", label.lower()) or "edit", digest(after))
    try:
        keep_out_of_git(DIR)
        write_bytes(os.path.join(DIR, name), before)
        trim(DIR)
    except OSError:  # the edit itself is already saved: a full disk or a locked folder must not turn it into an error
        return None
    return name[:-4]


def undo(expect=None, force=False):
    """Restore the newest snapshot byte for byte and remove it from the history. Returns what was undone.
    409 (Conflict) when the page's idea of «the newest» differs (`expect` = the snapshot id it knows), or when story.txt is no longer the file
    that edit produced (it was edited since, in the page or outside it) and `force` is not set; the file as it was is kept in .kit/undone/."""
    ents = entries()
    if not ents:
        raise ValueError("چیزی برای برگرداندن نیست")
    last = ents[-1]
    if expect and expect != last["id"]:
        raise Conflict("آخرین تغییر عوض شده؛ صفحه را دوباره بارگذاری کن.")
    now = read_story()
    if now is not None and digest(now) != last["after"] and not force:
        raise Conflict("فایل بعد از آن تغییر دوباره عوض شده (در صفحه یا بیرون از آن)؛ اگه می‌خوای باز هم برگردد، با force بفرست.")
    path = os.path.join(DIR, last["id"] + ".txt")
    data = open(path, "rb").read()
    if now is not None:
        keep_out_of_git(UNDONE)
        write_bytes(os.path.join(UNDONE, "%s_%s.txt" % (stamp(), digest(now))), now)
        trim(UNDONE)
    write_bytes(STORY, data)
    os.remove(path)
    return dict(id=last["id"], label=last["label"], time=last["time"])
