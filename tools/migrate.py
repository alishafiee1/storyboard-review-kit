# -*- coding: utf-8 -*-
"""One-time, reversible migration of an old project to image-based voice names (run it from the project's folder).
  python tools/migrate.py                 --dry-run (the default): changes nothing, prints a full Markdown report and saves it to .kit/migrate-report-<time>.md
  python tools/migrate.py --apply         do it (refused when the project is a git repo with uncommitted changes; --allow-dirty overrides)
  python tools/migrate.py --undo <time>   take a migration back: files renamed back, story.txt and the Premiere XMLs restored byte for byte
What --apply does, in this order:
  1. copies scenario/story.txt and every *.xml of the project (not .git / .engine-backup) to .engine-backup/migrate-<time>/
  2. gives every dialogue line a stable image-based id (IMG045-1: the picture the line belongs to + its position among that picture's lines; lines that
     already have such an id keep it) and renames its voice files in every audio/<lang>/ folder (also archive/; _samples/ and _tests/ are not touched):
     IMG001_1.mp3 -> IMG001-1.mp3, IMG001_2.eleven-v3.mp3 -> IMG001-2.eleven-v3.mp3, L007.mp3 -> IMG045-1.mp3 (the model tag or random id stays)
  3. writes the line's choice («voice:» / «voice-stale:») under the line itself; old scene-level voice-pick / voice-stale entries move there
  4. rewrites the <pathurl> of every Premiere XML that points at a renamed voice file (relative, absolute, file://localhost/D%3a/... alike); all other bytes stay
  5. appends every rename to .kit/renames.tsv (time, old, new): `python tools/premiere_check.py --fix` repairs XMLs from that log later
A file is never overwritten: when the new name is already taken the line keeps its old id and name, and the report says so."""
import argparse, collections, datetime, hashlib, json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import premiere_check  # noqa: E402
from edits import migrate_scene_key, set_say_attr  # noqa: E402
from flowname import audio_parse  # noqa: E402
from kitcore import LANGS, ROOT, STORY, MARKER, read_lines, write_lines  # noqa: E402
from moves import pin_scene  # noqa: E402
from story import parse_scene, parse_voice_map, scene_ranges  # noqa: E402

NEW_ID = re.compile(r"(IMG\d{3,4})-(\d+)")
SKIP_AUDIO = ("_samples", "_tests")
LOG = os.path.join(ROOT, ".kit", "renames.tsv")
BACKUPS = os.path.join(ROOT, ".engine-backup")


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def sha(path):
    return hashlib.sha1(open(path, "rb").read()).hexdigest()


def audio_files():
    """[(lang, path)] of every mp3 under audio/<lang>/ at any depth (archive/ included, _samples/ and _tests/ left out)."""
    out = []
    for lg in LANGS:
        for d, ds, fs in os.walk(os.path.join(ROOT, "audio", lg)):
            ds[:] = sorted(x for x in ds if x not in SKIP_AUDIO)
            out += [(lg, os.path.join(d, f)) for f in sorted(fs) if f.lower().endswith(".mp3")]
    return out


def project_xmls():
    out = []
    for d, ds, fs in os.walk(ROOT):
        ds[:] = sorted(x for x in ds if x not in (".git", ".engine-backup", "node_modules"))
        out += [os.path.join(d, f) for f in sorted(fs) if f.lower().endswith(".xml")]
    return out


def scenes_of(lines):
    return [(sid, parse_scene(lines[s:e]), s) for sid, s, e in scene_ranges(lines)]


def plan():
    """Work out everything --apply would do, without touching the disk. Returns a dict (see report())."""
    orig = read_lines(STORY)
    if not orig:
        sys.exit("no scenario/story.txt in this project")
    notes = []
    lines = list(orig)
    for sid, sc, _ in scenes_of(orig):  # what the old file says: shared blocks (lines named after another picture) and lines above the first picture
        for b in sc["blocks"]:
            for it in b["items"]:
                if it["k"] != "say":
                    continue
                if not it["img"]:
                    notes.append("%s: the line «%s» is above the first picture: it keeps its name (`%s`)." % (sid, it["fa"][:40], it["id"]))
                elif not it.get("eid") and re.fullmatch(r"IMG\d{3,4}", it["id"].rsplit("_", 1)[0]) and it["id"].rsplit("_", 1)[0] != it["img"]:
                    notes.append("%s: shared block: `%s` was named after %s, the line sits under %s, so it becomes %s-… (it stays under the last [IMG] of the block)." % (
                        sid, it["id"], it["id"].rsplit("_", 1)[0], it["img"], it["img"]))
    for sid, _, _ in scenes_of(orig):
        pin_scene(lines, sid)  # explicit id: lines, scene-level choices under the lines
    scenes = scenes_of(lines)
    says = [(sid, s, it) for sid, sc, s in scenes for b in sc["blocks"] for it in b["items"] if it["k"] == "say"]
    count = collections.Counter(it["id"] for _, _, it in says)
    taken = {it["id"] for _, _, it in says if NEW_ID.fullmatch(it["id"])}
    idmap, skipped, rows, pos = {}, [], [], collections.Counter()
    for sid, s, it in says:
        img = it["img"]
        if not img:
            continue
        pos[img] += 1
        old = it["id"]
        if NEW_ID.fullmatch(old):
            continue
        if count[old] > 1:
            skipped.append((old, "the same id is on %d lines: which one owns the voice files is unknown" % count[old]))
            continue
        k = pos[img]
        while "%s-%d" % (img, k) in taken:
            k += 1
        new = "%s-%d" % (img, k)
        taken.add(new)
        idmap[old] = new
        rows.append(dict(scene=sid, image=img, old=old, new=new))
    renames = collections.OrderedDict()  # old rel path -> new rel path
    owner = {}  # old rel -> old id
    for lg, path in audio_files():
        name = os.path.basename(path)
        p = audio_parse(name)
        if p and p[0] in idmap and name.startswith(p[0]):
            new = os.path.join(os.path.dirname(path), idmap[p[0]] + name[len(p[0]):])
            renames[rel(path)], owner[rel(path)] = rel(new), p[0]
    exist = {rel(p).lower() for _, p in audio_files()}
    want = collections.Counter(v.lower() for v in renames.values())
    blocked = {owner[o] for o, n in renames.items() if n.lower() in exist or want[n.lower()] > 1}  # a name that is already there (or wanted twice): never overwrite
    for old in sorted(blocked):
        skipped.append((old, "a voice file of this line would get a name that is already taken (nothing overwritten): the line keeps `%s` and its files" % old))
        idmap.pop(old)
    renames = collections.OrderedDict((o, n) for o, n in renames.items() if owner[o] not in blocked)
    rows = [r for r in rows if r["old"] in idmap]
    base = {lg: {os.path.basename(o): os.path.basename(n) for o, n in renames.items() if o.split("/")[1] == lg} for lg in LANGS}
    changed = dict(ids=0, voice=0)
    for sid, sc, s in scenes:  # write the new ids and the renamed files into the choices
        for b in sc["blocks"]:
            for it in b["items"]:
                if it["k"] != "say":
                    continue
                if it["id"] in idmap and "id_ln" in it:
                    lines[s + it["id_ln"]] = "id: " + idmap[it["id"]]
                    changed["ids"] += 1
                new = {lg: base[lg].get(v, v) for lg, v in it["voice"].items()}
                if new != it["voice"]:
                    set_say_attr(lines, s + it["ln"], "voice", ", ".join("%s=%s" % (lg, new[lg]) for lg in LANGS if lg in new))
                    changed["voice"] += 1
    for sid, sc, _ in scenes_of(lines):  # scene-level choices that point at no line of the scene stay there, but follow the renames
        if sc["legacy_pick"]:
            new = {}
            for k, v in sc["legacy_pick"].items():
                lid, _, lg = k.rpartition(".")
                new["%s.%s" % (idmap.get(lid, lid), lg)] = base.get(lg, {}).get(v, v)
            if new != sc["legacy_pick"]:
                migrate_scene_key(lines, sid, "voice-pick", new)
            notes.append("%s: scene-level voice-pick entries that name no line of this scene stay as they are: %s" % (sid, ", ".join(sorted(new))))
    known = {p[0] for p in (audio_parse(os.path.basename(f)) for _, f in audio_files()) if p}
    story_ids = {it["id"] for _, _, it in says}
    for lid in sorted(known - story_ids - set(idmap.values())):
        notes.append("voice files named `%s…` belong to no dialogue line of story.txt: left as they are." % lid)
    xmls = []
    for x in project_xmls():
        data = open(x, "rb").read()
        if b"<pathurl>" in data:
            new, ch = premiere_check.rewrite_pathurls(data, os.path.dirname(x), renames, ROOT)
            xmls.append(dict(path=x, rel=rel(x), data=new, changes=ch))
    return dict(orig=orig, lines=lines, rows=rows, renames=renames, skipped=skipped, notes=notes, xmls=xmls, changed=changed, idmap=idmap,
                all_xml=[rel(x) for x in project_xmls()])


def report(p, mode, stamp, extra=()):
    L = ["# Migration report (%s)" % mode, "", "- project: `%s`" % ROOT, "- time: `%s`" % stamp, ""]
    L += ["## Summary", "",
          "- dialogue lines that get a new id: **%d**" % len(p["rows"]),
          "- voice files renamed: **%d**" % len(p["renames"]),
          "- lines left as they are (see below): **%d**" % len(p["skipped"]),
          "- Premiere XML files with paths to rewrite: **%d** of %d (%d paths)" % (sum(1 for x in p["xmls"] if x["changes"]), len(p["all_xml"]), sum(len(x["changes"]) for x in p["xmls"])),
          "- `story.txt`: %d `id:` lines written, %d `voice:` lines updated" % (p["changed"]["ids"], p["changed"]["voice"]), ""]
    L += ["## Dialogue lines", ""] + (["| scene | picture | old id | new id |", "|---|---|---|---|"] + ["| %s | %s | `%s` | `%s` |" % (r["scene"], r["image"], r["old"], r["new"]) for r in p["rows"]] if p["rows"] else ["Nothing to rename."]) + [""]
    L += ["## Voice files", ""] + (["| old | new |", "|---|---|"] + ["| `%s` | `%s` |" % (o, n) for o, n in p["renames"].items()] if p["renames"] else ["No voice file has to be renamed."]) + [""]
    if p["skipped"]:
        L += ["## Skipped (nothing was changed for these)", ""] + ["- `%s`: %s" % s for s in p["skipped"]] + [""]
    if p["notes"]:
        L += ["## Notes", ""] + ["- " + n for n in p["notes"]] + [""]
    L += ["## Premiere XML", ""]
    if p["xmls"]:
        for x in p["xmls"]:
            L += ["- `%s`: %d path(s) rewritten" % (x["rel"], len(x["changes"]))] + ["  - `%s` → `%s`" % c for c in x["changes"][:5]] + (["  - … and %d more" % (len(x["changes"]) - 5)] if len(x["changes"]) > 5 else [])
    else:
        L += ["No Premiere XML with media paths found."]
    L += [""] + list(extra)
    if mode == "dry-run":
        L += ["## Next", "", "Nothing was changed. To do it: commit your work, then `python tools/migrate.py --apply`; to take it back: `python tools/migrate.py --undo %s`." % stamp, ""]
    return "\n".join(L)


def save_report(text, stamp):
    path = os.path.join(ROOT, ".kit", "migrate-report-%s.md" % stamp)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8", newline="\n").write(text)
    return path


def now():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def git_dirty():
    """List of changed paths of this project when it is a git work tree (the migration's own reports do not count); None when it is not one."""
    try:
        if subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True, text=True).stdout.strip() != "true":
            return None
        r = subprocess.run(["git", "status", "--porcelain", "--", ".", ":(exclude).kit/migrate-report-*", ":(exclude).engine-backup"], cwd=ROOT, capture_output=True, text=True)
        return [l for l in r.stdout.split("\n") if l.strip()]
    except OSError:
        return None


def log_rows(rows):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8", newline="") as fh:
        for t, o, n in rows:
            fh.write("%s\t%s\t%s\n" % (t, o, n))
        fh.flush()


def apply(allow_dirty=False):
    dirty = git_dirty()
    if dirty and not allow_dirty:
        sys.exit("Refused: this project is a git repo with uncommitted changes (commit or stash them first, or use --allow-dirty):\n  " + "\n  ".join(dirty[:10]))
    p = plan()
    stamp = now()
    while os.path.exists(os.path.join(BACKUPS, "migrate-" + stamp)):  # two runs in one second
        stamp = (datetime.datetime.strptime(stamp, "%Y%m%d-%H%M%S") + datetime.timedelta(seconds=1)).strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(BACKUPS, "migrate-" + stamp)
    targets = [STORY] + [x["path"] for x in p["xmls"] if x["changes"]]
    for x in p["all_xml"]:  # every XML is backed up, also those that need no change
        if os.path.join(ROOT, *x.split("/")) not in targets:
            targets.append(os.path.join(ROOT, *x.split("/")))
    for t in targets:
        os.makedirs(os.path.dirname(os.path.join(bdir, *rel(t).split("/"))), exist_ok=True)
        shutil.copy2(t, os.path.join(bdir, *rel(t).split("/")))
    manifest = os.path.join(bdir, "manifest.json")
    json.dump(dict(time=stamp, files=[rel(t) for t in targets], after={}), open(manifest, "w", encoding="utf-8"), indent=1)
    done = []
    try:
        for o, n in p["renames"].items():
            src, dst = os.path.join(ROOT, *o.split("/")), os.path.join(ROOT, *n.split("/"))
            if os.path.exists(dst):
                raise OSError("target appeared meanwhile: " + n)
            os.rename(src, dst)
            done.append((stamp, o, n))
            log_rows([done[-1]])
        after = {}
        if p["lines"] != p["orig"]:
            write_lines(STORY, p["lines"])
        after[rel(STORY)] = sha(STORY)
        for x in p["xmls"]:
            if x["changes"]:
                open(x["path"], "wb").write(x["data"])
                after[x["rel"]] = sha(x["path"])
        json.dump(dict(time=stamp, files=[rel(t) for t in targets], after=after), open(manifest, "w", encoding="utf-8"), indent=1)
    except Exception as e:
        print("FAILED (%s): putting everything back" % e, file=sys.stderr)
        undo(stamp, force=True)
        raise
    extra = ["## Check", ""]
    for x in p["xmls"]:
        if x["changes"]:
            r = premiere_check.check(x["path"])
            left = premiere_check.rewrite_pathurls(open(x["path"], "rb").read(), os.path.dirname(x["path"]), p["renames"], ROOT)[1]
            extra.append("- `%s`: %d files used, %d not found on this computer, %d with an absolute path (those of another computer cannot be checked here); paths still on an old name: %d" % (x["rel"], r["total"], len(r["missing"]), len(r["absolute"]), len(left)))
    extra += ["- backup: `%s`" % rel(bdir), "- rename log: `.kit/renames.tsv` (%d rows)" % len(done), "- to take it back: `python tools/migrate.py --undo %s`" % stamp, ""]
    text = report(p, "applied", stamp, extra)
    print(text)
    print("report saved to", rel(save_report(text, stamp)))
    return stamp


def undo(stamp, force=False):
    bdir = os.path.join(BACKUPS, "migrate-" + stamp)
    try:
        man = json.load(open(os.path.join(bdir, "manifest.json"), encoding="utf-8"))
    except (OSError, ValueError):
        sys.exit("No backup of a migration at %s" % rel(bdir))
    rows = [r.split("\t") for r in (open(LOG, encoding="utf-8").read().split("\n") if os.path.exists(LOG) else []) if r.startswith(stamp + "\t")]
    changed = [f for f, h in man.get("after", {}).items() if not os.path.exists(os.path.join(ROOT, *f.split("/"))) or sha(os.path.join(ROOT, *f.split("/"))) != h]
    if changed and not force:
        sys.exit("Refused: changed since the migration (undoing would lose those edits; --force to do it anyway): " + ", ".join(changed))
    problems = [("%s is missing" % n) if not os.path.exists(os.path.join(ROOT, *n.split("/"))) else "%s exists already" % o
                for _, o, n in rows if not os.path.exists(os.path.join(ROOT, *n.split("/"))) or os.path.exists(os.path.join(ROOT, *o.split("/")))]
    if problems and not force:
        sys.exit("Refused: cannot put every file back (--force skips those): " + "; ".join(problems[:10]))
    for _, o, n in reversed(rows):
        src, dst = os.path.join(ROOT, *n.split("/")), os.path.join(ROOT, *o.split("/"))
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
    for f in man["files"]:
        src = os.path.join(bdir, *f.split("/"))
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(ROOT, *f.split("/")))
    if os.path.exists(LOG):
        keep = [l for l in open(LOG, encoding="utf-8").read().split("\n") if l and not l.startswith(stamp + "\t")]
        if keep:
            open(LOG, "w", encoding="utf-8", newline="").write("".join(l + "\n" for l in keep))
        else:
            os.remove(LOG)
    print("Undone: %d file(s) renamed back, %d text file(s) restored from %s" % (len(rows), len(man["files"]), rel(bdir)))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="report only (the default)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", metavar="TIME")
    ap.add_argument("--allow-dirty", action="store_true", help="run --apply although git has uncommitted changes")
    ap.add_argument("--force", action="store_true", help="with --undo: also when files changed since the migration")
    a = ap.parse_args()
    if a.undo:
        undo(a.undo, a.force)
    elif a.apply:
        apply(a.allow_dirty)
    else:
        t = now()
        text = report(plan(), "dry-run", t)
        print(text)
        print("report saved to", rel(save_report(text, t)))
