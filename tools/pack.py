# -*- coding: utf-8 -*-
"""Pack the project for someone else (an editor, a friend): one zip with the kit, the scenario, pictures, voices and the Premiere package,
but without the heavy or private things: output videos / previews / renders, archived files, test audio, .env, git data.
  python tools/pack.py [--clips]         -> ../<project>-for-editor.zip   (--clips also puts videos/clips/ in)
  python tools/pack.py --all             every picture version and every voice take (default: only the ones the project uses)
  python tools/pack.py --list            only print what would go in (nothing is written)
  python tools/pack.py --package DIR     the Premiere package folder (default: the newest `premiere/` or `videos/final/*_premiere_package`)
  python tools/pack.py --help
Only the chosen package folder keeps its Premiere XML: every other *.xml of the project (old exports) and every other package folder stays out.
The XML of the package is checked first: a file it needs that would not be in the zip is reported."""
import argparse, glob, os, re, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import premiere_check  # noqa: E402
from media import resolve, scan_images  # noqa: E402
from story import story_scenes  # noqa: E402

ROOT = premiere_check.ROOT
SKIP_DIRS = {".git", ".kit", ".engine-backup", "__pycache__", "graphify-out", "archive", "_samples", "_tests", "_tmp"}
VID_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
STORED = (".mp3", ".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".webm", ".zip")  # already compressed: no point squeezing


def package_dirs():
    """Folders that look like a Premiere package (rel paths with /): `premiere/` and `videos/final/*_premiere_package`, newest first."""
    out = []
    for rel in ["premiere"] + [os.path.relpath(d, ROOT).replace("\\", "/") for d in glob.glob(os.path.join(ROOT, "videos", "final", "*_premiere_package"))]:
        if os.path.isdir(os.path.join(ROOT, rel)):
            out.append(rel)
    return sorted(out, key=lambda r: os.path.getmtime(os.path.join(ROOT, r)), reverse=True)


def pick_package(explicit=None):
    """The package folder to ship (rel path) or None: the one asked for, else the newest candidate."""
    if explicit:
        rel = explicit.strip().replace("\\", "/").strip("/")
        if not os.path.isdir(os.path.join(ROOT, rel)):
            raise SystemExit("package folder not found: " + explicit)
        return rel
    c = package_dirs()
    return c[0] if c else None


def skip(rel, clips=False, pkg=None):
    """True when this file stays out of the zip (rel = path from the project folder, with /). With `pkg` (the package folder) a Premiere XML outside
    it and every other package folder stay out too."""
    parts = rel.split("/")
    name = parts[-1]
    if pkg:
        inside = rel == pkg or rel.startswith(pkg + "/")
        if name.lower().endswith(".xml") and not inside:
            return True
        if not inside and any(rel.startswith(o + "/") for o in package_dirs() if o != pkg):
            return True
    if any(p in SKIP_DIRS or p.endswith("_renders") for p in parts[:-1]):
        return True
    if name == ".env" or name.endswith((".tmp", ".rar", ".zip", ".pyc")):
        return True
    if rel.startswith("videos/clips/") and not clips:
        return True
    if name.lower().endswith(VID_EXT) and re.search(r"(preview|demo)", name, re.I):
        return True
    return False


def selected_media():
    """The picture files and voice files the project really uses (rel paths with /): the picked version of every picture that is not set aside, and the
    chosen voice of every dialogue line in every language. Other versions and takes stay out."""
    from project import project
    out = set()
    for sc in project()["scenes"]:
        if sc.get("off"):
            continue
        for b in sc["blocks"]:
            for m in b["images"]:
                if m.get("src") and not m.get("off"):
                    out.add(m["src"])
            for it in b["items"]:
                for u in (it.get("audio") or {}).values():
                    if u:
                        out.add(u.split("?")[0])
    return out


def files(clips=False, pkg=None, selected=False):
    """Every file for the zip. With `selected` the pictures of images/scenes/ and the voices of audio/ are only those the project uses."""
    keep = selected_media() if selected else None
    for d, ds, fs in os.walk(ROOT):
        ds[:] = [x for x in ds if x not in SKIP_DIRS and not x.endswith("_renders")]
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), ROOT).replace("\\", "/")
            if skip(rel, clips, pkg):
                continue
            if keep is not None and (rel.startswith("images/scenes/") or (rel.startswith("audio/") and rel.lower().endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac")))) and rel not in keep:
                continue
            yield rel


def xmls_of(pkg=None):
    """The Premiere XMLs to check: those inside the package folder, or all of them when there is no package folder."""
    xs = premiere_check.find_xmls()
    if not pkg:
        return xs
    return [x for x in xs if os.path.relpath(x, ROOT).replace("\\", "/").startswith(pkg + "/")]


def problems(clips=False, pkg=None):
    """Files a Premiere XML needs that the zip would not hold (or that do not exist)."""
    out = []
    for x in xmls_of(pkg):
        for p in premiere_check.check(x)["paths"]:
            rel = os.path.relpath(p, ROOT).replace("\\", "/") if os.path.abspath(p).startswith(ROOT) else None
            if not os.path.exists(p):
                out.append("%s: missing %s" % (os.path.basename(x), p))
            elif rel is None:
                out.append("%s: %s is outside the project folder" % (os.path.basename(x), p))
            elif skip(rel, clips, pkg):
                out.append("%s: %s would be left out of the zip" % (os.path.basename(x), rel))
    return out


def outdated_pictures(pkg=None):
    """['<xml>: <path> -> <file the page shows now>']: a scene picture the Premiere XML points at that is not the picked version at its best quality
    (a 4K file arrived later, or another version was chosen). Only a hint: the zip is built the same."""
    picks = {im["id"]: im["pick"] for sc in story_scenes() for b in sc["blocks"] for im in b["images"]}
    scan, out = scan_images(), []
    for x in xmls_of(pkg):
        for p in premiere_check.check(x)["paths"]:
            m = re.match(r"(IMG\d{3,4})(?!\d)", os.path.basename(p))
            r = resolve("image", m.group(1), picks.get(m.group(1), ""), scan=scan) if m and "/images/scenes/" in p.replace("\\", "/") else None
            if r and os.path.normpath(r["path"]) != os.path.normpath(p):
                out.append("%s: %s -> %s" % (os.path.basename(x), os.path.relpath(p, ROOT).replace("\\", "/"), r["src"]))
    return out


EDITOR_README = """STORYBOARD REVIEW KIT - package for the editor
=================================================
This folder is a whole project: scenario, pictures, voices and the review page.

1. Install Python 3.9 or newer from https://www.python.org/downloads/ (tick "Add python.exe to PATH").
2. Windows: double-click click-for-review.bat. Other systems: python tools/serve.py
3. Open http://127.0.0.1:8765/review.html in your browser (it opens by itself on Windows).
   You can read the story picture by picture, listen to every line, see the notes and edit advice (fx:).
4. The pictures and voices in this package are the chosen versions only. The Premiere project (if any) is in the folder named
   premiere/ or videos/final/*_premiere_package/ and points to the same files with relative paths.

Nothing here needs an internet connection or an account. The server stops by itself about 90 seconds after the page is closed.

---

بسته برای ادیتور
1. Python نسخهٔ ۳٫۹ به بالا رو از python.org نصب کن (تیک Add to PATH رو بزن).
2. ویندوز: دابل‌کلیک روی click-for-review.bat. بقیه: python tools/serve.py
3. آدرس http://127.0.0.1:8765/review.html رو باز کن؛ داستان رو تصویر به تصویر می‌بینی، صدای هر خط رو می‌شنوی و یادداشت‌ها و توصیهٔ ادیت (fx:) رو می‌خونی.
4. عکس‌ها و صداهای این بسته فقط نسخه‌های انتخاب‌شده‌ان. پروژهٔ پریمیر (اگه باشه) توی premiere/ یا videos/final/*_premiere_package/ هست و با مسیر نسبی به همین فایل‌ها اشاره می‌کنه.
"""


def pack(clips=False, out=None, pkg=None, selected=True):
    out = out or os.path.join(os.path.dirname(ROOT), os.path.basename(ROOT) + "-for-editor.zip")
    n = 0
    with zipfile.ZipFile(out + ".tmp", "w") as z:
        z.writestr(os.path.basename(ROOT) + "/README-FOR-EDITOR.txt", EDITOR_README)
        for rel in files(clips, pkg, selected):
            z.write(os.path.join(ROOT, rel), os.path.basename(ROOT) + "/" + rel,
                    zipfile.ZIP_STORED if rel.lower().endswith(STORED) else zipfile.ZIP_DEFLATED)
            n += 1
    os.replace(out + ".tmp", out)
    return out, n


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Pack the project into one zip for an editor.", epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", action="store_true", help="also put videos/clips/ in")
    ap.add_argument("--all", action="store_true", help="every picture version and voice take, not only the ones the project uses")
    ap.add_argument("--list", action="store_true", help="only print the files that would go in; write nothing")
    ap.add_argument("--package", metavar="DIR", help="the Premiere package folder (default: the newest one found)")
    ap.add_argument("-o", "--output", metavar="ZIP", help="the zip to write (default: next to the project folder)")
    a = ap.parse_args()
    pkg = pick_package(a.package)
    print("Premiere package folder:", pkg or "(none found; every XML stays in)")
    if a.list:
        lst = sorted(files(a.clips, pkg, not a.all))
        print(chr(10).join(lst))
        print("%d files (nothing written)" % len(lst))
        sys.exit(0)
    pr = problems(a.clips, pkg)
    for p in pr:
        print("⚠", p)
    for p in outdated_pictures(pkg):
        print("ℹ", p)
    path, n = pack(a.clips, a.output, pkg, not a.all)
    print("%d files, %.1f MB -> %s" % (n, os.path.getsize(path) / 1e6, path))
    sys.exit(1 if pr else 0)
