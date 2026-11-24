# -*- coding: utf-8 -*-
"""Pack the project for someone else (an editor, a friend): one zip with the kit, the scenario, pictures, voices and the Premiere package,
but without the heavy or private things: output videos / previews / renders, archived files, test audio, .env, git data.
  python tools/pack.py [--clips]         -> ../<project>-for-editor.zip   (--clips also puts videos/clips/ in)
If the project has a Premiere XML it is checked first: a file the XML needs that would not be in the zip is reported."""
import os, re, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import premiere_check  # noqa: E402

ROOT = premiere_check.ROOT
SKIP_DIRS = {".git", ".engine-backup", "__pycache__", "graphify-out", "archive", "_samples", "_tests", "_tmp"}
VID_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
STORED = (".mp3", ".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".webm", ".zip")  # already compressed: no point squeezing


def skip(rel, clips=False):
    """True when this file stays out of the zip (rel = path from the project folder, with /)."""
    parts = rel.split("/")
    name = parts[-1]
    if any(p in SKIP_DIRS or p.endswith("_renders") for p in parts[:-1]):
        return True
    if name == ".env" or name.endswith((".tmp", ".rar", ".zip", ".pyc")):
        return True
    if rel.startswith("videos/clips/") and not clips:
        return True
    if name.lower().endswith(VID_EXT) and re.search(r"(preview|demo)", name, re.I):
        return True
    return False


def files(clips=False):
    for d, ds, fs in os.walk(ROOT):
        ds[:] = [x for x in ds if x not in SKIP_DIRS and not x.endswith("_renders")]
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), ROOT).replace("\\", "/")
            if not skip(rel, clips):
                yield rel


def problems(clips=False):
    """Files a Premiere XML needs that the zip would not hold (or that do not exist)."""
    out = []
    for x in premiere_check.find_xmls():
        for p in premiere_check.check(x)["paths"]:
            rel = os.path.relpath(p, ROOT).replace("\\", "/") if os.path.abspath(p).startswith(ROOT) else None
            if not os.path.exists(p):
                out.append("%s: missing %s" % (os.path.basename(x), p))
            elif rel is None:
                out.append("%s: %s is outside the project folder" % (os.path.basename(x), p))
            elif skip(rel, clips):
                out.append("%s: %s would be left out of the zip" % (os.path.basename(x), rel))
    return out


def pack(clips=False, out=None):
    out = out or os.path.join(os.path.dirname(ROOT), os.path.basename(ROOT) + "-for-editor.zip")
    n = 0
    with zipfile.ZipFile(out + ".tmp", "w") as z:
        for rel in files(clips):
            z.write(os.path.join(ROOT, rel), os.path.basename(ROOT) + "/" + rel,
                    zipfile.ZIP_STORED if rel.lower().endswith(STORED) else zipfile.ZIP_DEFLATED)
            n += 1
    os.replace(out + ".tmp", out)
    return out, n


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    clips = "--clips" in sys.argv
    pr = problems(clips)
    for p in pr:
        print("⚠", p)
    path, n = pack(clips)
    print("%d files, %.1f MB -> %s" % (n, os.path.getsize(path) / 1e6, path))
    sys.exit(1 if pr else 0)
