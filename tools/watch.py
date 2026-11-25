# -*- coding: utf-8 -*-
"""Moves the pictures Flow (or the browser) downloaded from the Downloads folder into this project.
  python tools/watch.py              watch the folder every few seconds (serve.py does this by itself, always, unless kit-config.json has "watch_downloads": false)
  python tools/watch.py --once       one pass, then stop
  python tools/watch.py --dry-run    only say what would be moved (nothing moves, nothing is logged)
  python tools/watch.py --downloads DIR   another folder (default: kit-config.json "downloads", else ~/Downloads)
A file is MOVED (cut, never copied and kept) only when ALL of this holds:
  - its name follows the Flow pattern (flowname.py) and it is not a partial download (.crdownload / .part / .tmp, or its size / time changed during the pass);
  - its base name (IMG045, CH_MIMO) is known in THIS project: a [IMG045] marker in story.txt, a «=== IMG045 ===» header in prompts.txt, or a reference already in images/refs/;
  - with "match_slug": true (the default) its slug fits the expected output name of that picture: «[OUTPUT NAME: IMG045_cave_wall]» in its prompt, else the slug of the
    versions already on disk (case, underscores and Flow's «…» cut-off are ignored). A file with no slug fits; a file with another slug (another episode) stays where it is.
Pictures go to images/scenes/bNN/ (IMG001-010 = b01, IMG000 = b00), references to images/refs/<KIND>/. Nothing is overwritten: a file whose bytes are already in the
project is only taken out of Downloads (it is the same file); a different file with a taken name gets a free « (n)» name. Every move is appended to .kit/imports.tsv
(time, from, to, size). Files that do not match are never touched."""
import argparse, hashlib, os, re, shutil, sys, time
from kitcore import MARKER, ROOT, IMG_EXT, read_lines
from flowname import REF_KINDS, batch_of, config, output_slug, parse, settings, slugs_match, walk

PARTIAL = (".crdownload", ".part", ".tmp", ".download", ".opdownload", ".partial")
LOG = os.path.join(".kit", "imports.tsv")


def downloads_dir(root=None):
    """kit-config.json "downloads" (~ allowed; a relative path is relative to the project), else the user's Downloads folder (Windows and Linux)."""
    root = root or ROOT
    d = config(root).get("downloads")
    if isinstance(d, str) and d.strip():
        d = os.path.expanduser(d.strip())
        return d if os.path.isabs(d) else os.path.join(root, d)
    return os.path.join(os.path.expanduser("~"), "Downloads")


def _read_prompts(root):
    """{base: prompt text} of prompts/prompts.txt (header «=== X ===», text up to the next header)."""
    out, cur = {}, None
    for l in read_lines(os.path.join(root, "prompts", "prompts.txt")):
        m = re.match(r"^=== ([A-Za-z0-9_]+) ===$", l.strip())
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur:
            out[cur].append(l)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def project_index(root, cfg):
    """What this project knows: {base: dict(kind 'scene' | 'ref', prompt, slugs)} + every image file of the project [(path, size)] (archive included)."""
    prompts = _read_prompts(root)
    known = {}
    for l in read_lines(os.path.join(root, "scenario", "story.txt")):
        m = MARKER.match(l.strip())
        if m:
            known.setdefault(m.group(1), dict(kind="scene"))
    for k in prompts:
        known.setdefault(k, dict(kind="scene" if re.fullmatch(r"IMG\d{3,4}", k) else "ref"))
    files = []
    for top in ("scenes", "refs"):
        for f in walk(os.path.join(root, "images", top), skip=("inbox",)):
            if f.lower().endswith(IMG_EXT):
                files.append(f)
    for f in walk(os.path.join(root, "images", "archive"), skip=()):
        if f.lower().endswith(IMG_EXT):
            files.append(f)
    slugs = {}
    for f in files:
        p = parse(os.path.basename(f), cfg)
        if not p:
            continue
        if os.path.relpath(f, root).replace("\\", "/").startswith("images/refs/"):
            known.setdefault(p["base"], dict(kind="ref"))
        if p["slug"]:
            slugs.setdefault(p["base"], []).append(p["slug"])
    for base, k in known.items():
        k["prompt"] = prompts.get(base, "")
        k["slugs"] = slugs.get(base, [])
    return known, files


def destination(base, kind):
    """images/scenes/bNN or images/refs/<KIND> (relative, with /) for a base name; None when the name has no place (an unknown reference prefix)."""
    if re.fullmatch(r"IMG\d{3,4}", base):
        return "images/scenes/" + batch_of(base)
    k = base.split("_")[0]
    return "images/refs/" + k if kind == "ref" and k in REF_KINDS else None


def expected_slugs(base, info):
    """The slugs a file of this base may carry: the prompt's OUTPUT NAME (the only one, when there is one), else the slugs of the versions already here; [] = nothing known."""
    s = output_slug(info["prompt"], base)
    return [s] if s is not None else list(info["slugs"])


def _free_name(folder, name, taken):
    """`name`, or «stem (n).ext» with the first n that is free in `folder` and not in `taken` (lower-case names of the project)."""
    if name.lower() not in taken and not os.path.exists(os.path.join(folder, name)):
        return name
    stem, ext = os.path.splitext(re.sub(r"\s\(\d+\)(?=\.[^.]*$)", "", name))
    n = 1
    while True:
        cand = "%s (%d)%s" % (stem, n, ext)
        if cand.lower() not in taken and not os.path.exists(os.path.join(folder, cand)):
            return cand
        n += 1


def _digest(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _identical(path, size, files):
    """The project file with exactly the bytes of `path`, or None (only files of the same size are read)."""
    dig = None
    for f in files:
        try:
            if os.path.getsize(f) != size:
                continue
            dig = dig or _digest(path)
            if _digest(f) == dig:
                return f
        except OSError:
            continue
    return None


def move_file(src, dst):
    """Cut `src` to `dst`. Same drive: os.replace; another drive (OSError): shutil.move to a .tmp next to the target, then os.replace into place, so a scan
    of the project never sees half a file."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.replace(src, dst)
    except OSError:
        tmp = dst + ".tmp"
        try:
            shutil.move(src, tmp)
            os.replace(tmp, dst)
        except OSError:
            if os.path.exists(tmp) and os.path.exists(src):
                os.remove(tmp)
            raise


def log_import(root, src, dst, size):
    os.makedirs(os.path.join(root, ".kit"), exist_ok=True)
    rel = os.path.relpath(dst, root).replace("\\", "/") if dst and os.path.isabs(dst) and not dst.startswith("(") else dst
    with open(os.path.join(root, LOG), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("%s\t%s\t%s\t%d\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), src.replace("\t", " "), rel.replace("\t", " "), size))


def recent_imports(root=None, n=30):
    """[{time, from, to, size}] newest first (the last `n` rows of .kit/imports.tsv)."""
    out = []
    for l in read_lines(os.path.join(root or ROOT, LOG)):
        c = l.split("\t")
        if len(c) >= 4:
            out.append(dict(time=c[0], source=c[1], to=c[2], size=int(c[3]) if c[3].isdigit() else 0))
    return out[::-1][:n]


def _stat(path):
    try:
        st = os.stat(path)
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def run_once(root=None, downloads=None, dry_run=False, settle=1.0):
    """One pass over the top level of the Downloads folder. Returns [{file, action, to, reason}] with action 'moved', 'duplicate' (same bytes already in the project:
    removed from Downloads), 'skip' (reason says why) - only files whose names look like project files are listed; every other file is invisible to the watcher.
    `settle` = seconds between the two size checks that tell a finished download from a growing one."""
    root, report = root or ROOT, []
    downloads = downloads or downloads_dir(root)
    if not os.path.isdir(downloads):
        return report
    cfg = settings(root)
    match_slug = config(root).get("match_slug", True) is not False
    cands = []
    for name in sorted(os.listdir(downloads)):
        path = os.path.join(downloads, name)
        if name.startswith(".") or name.lower().endswith(PARTIAL) or not os.path.isfile(path) or not name.lower().endswith(IMG_EXT):
            continue
        p = parse(name, cfg)
        if p:
            cands.append((path, name, p))
    if not cands:
        return report
    first = {c[0]: _stat(c[0]) for c in cands}
    if settle:
        time.sleep(settle)
    known, files = project_index(root, cfg)
    for path, name, p in cands:
        item = dict(file=name, action="skip", to="", reason="")
        report.append(item)
        st = _stat(path)
        info = known.get(p["base"])
        if st is None or st != first[path]:
            item["reason"] = "still being downloaded"
            continue
        if info is None:
            item["reason"] = "unknown base name in this project"
            continue
        dest = destination(p["base"], info["kind"])
        if dest is None:
            item["reason"] = "no folder for this kind of reference"
            continue
        if match_slug:
            exp = expected_slugs(p["base"], info)
            if p["slug"] and not exp:
                item["reason"] = "no expected output name to compare its slug with"
                continue
            if p["slug"] and not any(slugs_match(p["slug"], e) for e in exp):
                item["reason"] = "slug differs from the expected output name (%s)" % ", ".join(sorted(set(exp))[:3])
                continue
        same = _identical(path, st[0], files)
        if same:
            item.update(action="duplicate", to=os.path.relpath(same, root).replace("\\", "/"), reason="same bytes are already in the project")
            if not dry_run:
                try:
                    os.remove(path)
                    log_import(root, path, "(duplicate of %s)" % item["to"], st[0])
                except OSError as e:
                    item.update(action="skip", reason="could not remove: %s" % e)
            continue
        folder = os.path.join(root, *dest.split("/"))
        taken = {os.path.basename(f).lower() for f in files}
        target = os.path.join(folder, _free_name(folder, name, taken))
        item.update(action="moved", to=os.path.relpath(target, root).replace("\\", "/"))
        if dry_run:
            continue
        try:
            move_file(path, target)
        except OSError as e:
            item.update(action="skip", to="", reason="could not move: %s" % e)  # open in another program, no space, ...: the file stays in Downloads
            continue
        files.append(target)
        log_import(root, path, target, st[0])
    return report


def watch_loop(root=None, interval=3.0, stop=None):
    """Run run_once() every `interval` seconds until `stop` (a threading.Event) is set. Errors never end the loop."""
    while not (stop and stop.is_set()):
        try:
            run_once(root, settle=min(1.0, interval / 2))
        except Exception as e:  # a bad file or a busy disk must not stop the watcher
            print("watch:", e, file=sys.stderr, flush=True)
        if stop:
            stop.wait(interval)
        else:
            time.sleep(interval)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true", help="one pass, then stop")
    ap.add_argument("--dry-run", action="store_true", help="only report; nothing moves")
    ap.add_argument("--downloads", help="the folder to watch (default: kit-config.json downloads, else ~/Downloads)")
    ap.add_argument("--interval", type=float, default=3.0, help="seconds between passes")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    d = os.path.expanduser(a.downloads) if a.downloads else downloads_dir()
    print("watching %s%s" % (d, "  (dry run)" if a.dry_run else ""), flush=True)
    if not os.path.isdir(d):
        print("this folder does not exist (set \"downloads\" in kit-config.json)")
    while True:
        for r in run_once(downloads=d, dry_run=a.dry_run, settle=min(1.0, a.interval / 2)):
            print("%-9s %s%s%s" % (r["action"], r["file"], "  ->  " + r["to"] if r["to"] else "", "   (%s)" % r["reason"] if r["reason"] else ""), flush=True)
        if a.once or a.dry_run:
            return
        time.sleep(a.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
