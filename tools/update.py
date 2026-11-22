# -*- coding: utf-8 -*-
"""Updates the review tool inside a project (or creates a new project) from the latest version on GitHub. No git needed.
  python tools/update.py                 update THIS project: only the tool files listed in ENGINE.txt are replaced
                                         (review.html, tools/*.py, click-for-review.bat). Your scenario, prompts, images,
                                         audio and voices are never touched. Replaced files are copied to .engine-backup/ first.
  python tools/update.py --new FOLDER    create a new project in FOLDER (tool files + a small starter project)
  python tools/update.py --check         only say whether a newer version exists
Set STORYBOARD_KIT_REPO=owner/name to use a fork."""
import io, os, re, shutil, sys, time, urllib.request, zipfile

REPO = os.environ.get("STORYBOARD_KIT_REPO", "alishafiee1/storyboard-review-kit")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(globals().get("__file__") or "tools/update.py")))  # (no __file__ when started with python -c)
IGNORE = [".env", ".engine-backup/", "audio/", "__pycache__/", "*.tmp"]


def fetch():
    """Download the latest main branch as a zip -> (zipfile, top folder prefix)."""
    req = urllib.request.Request(f"https://github.com/{REPO}/archive/refs/heads/main.zip", headers={"User-Agent": "storyboard-review-kit-updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    return z, z.namelist()[0].split("/")[0] + "/"


def read(z, pre, name):
    try:
        return z.read(pre + name).decode("utf-8")
    except KeyError:
        return ""


def safe(rel):
    """A path from the manifest must stay inside the project."""
    return rel and not os.path.isabs(rel) and ".." not in rel.replace("\\", "/").split("/")


def local_version():
    p = os.path.join(ROOT, "VERSION")
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else "none"


def write(z, pre, rel, dest_root):
    data = z.read(pre + rel)
    dest = os.path.join(dest_root, *rel.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "wb").write(data)


def ensure_ignore(root):
    p = os.path.join(root, ".gitignore")
    cur = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []
    add = [x for x in IGNORE if x not in cur]
    if add:
        open(p, "a", encoding="utf-8", newline="").write(("\n" if cur and cur[-1] else "") + "\n".join(add) + "\n")


def update():
    z, pre = fetch()
    new_v = read(z, pre, "VERSION").strip()
    files = [l.strip() for l in read(z, pre, "ENGINE.txt").splitlines() if l.strip() and not l.startswith("#")]
    if not files:
        sys.exit("ENGINE.txt not found in the download; nothing changed.")
    old_v = local_version()
    if "--check" in sys.argv:
        print(f"installed: {old_v} | latest: {new_v}" + ("  (up to date)" if old_v == new_v else "  (update available: python tools/update.py)"))
        return
    stamp = os.path.join(ROOT, ".engine-backup", time.strftime("%Y%m%d-%H%M%S") + "-v" + old_v)
    changed = []
    for rel in files:
        if not safe(rel):
            sys.exit("Unsafe path in ENGINE.txt: " + rel)
        cur = os.path.join(ROOT, *rel.split("/"))
        new = z.read(pre + rel)
        if os.path.exists(cur) and open(cur, "rb").read() == new:
            continue
        if os.path.exists(cur):
            os.makedirs(os.path.dirname(os.path.join(stamp, *rel.split("/"))), exist_ok=True)
            shutil.copy2(cur, os.path.join(stamp, *rel.split("/")))
        write(z, pre, rel, ROOT)
        changed.append(rel)
    ensure_ignore(ROOT)
    if not changed:
        print(f"Already up to date (version {new_v}).")
    else:
        print(f"Updated {old_v} -> {new_v}: " + ", ".join(changed))
        print("Old copies of replaced files are in", os.path.relpath(stamp, ROOT))
        print("Restart the review server (close its window, then click click-for-review.bat again).")


def new_project(folder):
    folder = os.path.abspath(folder)
    if os.path.exists(folder) and os.listdir(folder):
        sys.exit("The folder is not empty: " + folder)
    z, pre = fetch()
    files = [l.strip() for l in read(z, pre, "ENGINE.txt").splitlines() if l.strip() and not l.startswith("#")]
    for rel in files:
        if safe(rel):
            write(z, pre, rel, folder)
    for n in z.namelist():  # starter/... -> project root
        rel = n[len(pre) + len("starter/"):]
        if n.startswith(pre + "starter/") and rel and not n.endswith("/") and safe(rel):
            dest = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "wb").write(z.read(n))
    ensure_ignore(folder)
    print("New project created:", folder)
    print("Start it with click-for-review.bat (Windows) or: python tools/serve.py")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--new" in sys.argv:
        i = sys.argv.index("--new")
        if i + 1 >= len(sys.argv):
            sys.exit("Usage: python tools/update.py --new FOLDER")
        new_project(sys.argv[i + 1])
    else:
        update()
