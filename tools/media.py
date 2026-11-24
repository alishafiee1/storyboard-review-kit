# -*- coding: utf-8 -*-
"""What is on disk next to the text: picture versions, references, videos, voice variants, and the archive folders (nothing here deletes a file)."""
import glob, os, re, time
from kitcore import IMG_EXT, LANGS, ROOT, VID_EXT, replace_file
from flowname import LEGACY_IMG, audio_parse, batch_of, find_version, group, parse, settings, walk


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def _legacy(name):
    """A name that does not follow the pattern but starts with an image id (old projects): its own version, keyed by the whole name."""
    m = LEGACY_IMG.match(name)
    return dict(base=m.group(1), slug=os.path.splitext(name)[0], rid="", q="", dup=False, key=(m.group(1), os.path.splitext(name)[0]), name=name) if m else None


def _version(v):
    """The page's view of one version: the shown file (best quality) and the other quality files of the same version."""
    return dict(name=os.path.basename(v["best"]), src=rel(v["best"]), id=v["id"], q=v["q"], files=[rel(f) for f in v["files"]])


def scan_images():
    """{IMG###: {versions: [{name, src, id, q, files}] oldest first, rejected: [src]}}. One version = one random id; its 2K / 4K files are one version (name / src = the best one)."""
    cfg = settings()
    cur, rej = {}, {}
    for f in walk(os.path.join(ROOT, "images", "scenes"), skip=("archive", "inbox")):
        if not f.lower().endswith(IMG_EXT):
            continue
        name = os.path.basename(f)
        p = parse(name, cfg) or _legacy(name)
        if p and re.fullmatch(r"IMG\d{3,4}", p["base"]):
            (rej if "_rejected" in rel(f)[len("images/scenes/"):] else cur).setdefault(p["base"], []).append((f, p))
    out = {}
    for id_ in set(cur) | set(rej):
        out[id_] = dict(versions=[_version(v) for v in group(cur.get(id_, []), cfg)],
                        rejected=[rel(x) for x, _ in sorted(rej.get(id_, []), key=lambda t: os.path.getmtime(t[0]), reverse=True)])
    return out


def shown_version(versions, pick):
    """(index of the version to show, the picked version or None): the picked one (by rid, version id or an old file name), else the newest."""
    v = find_version(versions, pick)
    return (versions.index(v) if v else len(versions) - 1), v


def image_state(im, scan):
    """What the page needs about a picture's files: shown file, all versions, the chosen one. A chosen picture counts as approved."""
    vs = scan.get("versions", [])
    vi, v = shown_version(vs, im["pick"])
    picked = v["id"] if v else ""
    return dict(src=vs[vi]["src"] if vs else None, versions=vs, vi=vi, picked=picked, rejected=scan.get("rejected", []),
                status=im["status"] or ("ok" if picked else ""), batch=batch_of(im["id"]))


def resolve(kind, id_, pick="", lang="", scan=None, idx=None):
    """The one answer to «which file is this?», shared by the page, the subtitles, pack.py and the Premiere export.
    kind 'image': the picked version (pick: value from story.txt, rid or old file name; none = the newest) at its best quality.
    kind 'voice': the chosen voice file of a line in `lang` (pick = the variant name; none = the old default, else the oldest).
    `scan` (scan_images()) / `idx` (audio_index(lang)) save a second disk walk when you ask many times.
    Returns dict(path, src, name, ...) or None when there is no file."""
    if kind == "image":
        vs = (scan if scan is not None else scan_images()).get(id_, {}).get("versions", [])
        if not vs:
            return None
        vi, v = shown_version(vs, pick)
        return dict(path=os.path.join(ROOT, vs[vi]["src"]), src=vs[vi]["src"], name=vs[vi]["name"], id=vs[vi]["id"], q=vs[vi]["q"], vi=vi, picked=bool(v))
    if kind == "voice":
        ch, vs = audio_choice(lang, id_, {f"{id_}.{lang}": pick} if pick else None, idx)
        return dict(path=ch["path"], src=rel(ch["path"]), name=ch["name"], variants=[x["name"] for x in vs]) if ch else None
    raise ValueError("kind must be image or voice")


def scan_refs(prompts):
    """One entry per reference (CH_MIMO, LOC_FACTORY_YARD): the newest version at its best quality; `versions` counts the versions on disk."""
    used = {}
    for id_, rec in prompts.items():
        if id_.startswith("IMG"):
            for r in rec["refs"]:
                used.setdefault(r, []).append(id_)
    cfg, root = settings(), os.path.join(ROOT, "images", "refs")
    by = {}
    for f in walk(root):
        if f.lower().endswith(IMG_EXT):
            name = os.path.basename(f)
            p = parse(name, cfg) or dict(base=re.sub(r"_[0-9a-f]{8}$", "", re.sub(r"\s\(\d+\)$", "", os.path.splitext(name)[0])), slug="", rid="", q="", dup=False, name=name)
            p.setdefault("key", (p["base"], ""))
            top = os.path.relpath(f, root).replace("\\", "/").split("/")[0]
            by.setdefault(p["base"], dict(kind=top if top != name else p["base"].split("_")[0], files=[]))["files"].append((f, p))
    out = []
    for name, r in sorted(by.items(), key=lambda kv: (kv[1]["kind"], kv[0])):
        vs = group(r["files"], cfg)
        out.append(dict(name=name, kind=r["kind"], src=rel(vs[-1]["best"]), used=used.get(name, []), versions=len(vs), prompt=(prompts.get(name) or {}).get("prompt", "")))
    return out


def scan_videos():
    """[(file name without extension, path)] of every video under videos/ and images/, newest first (rejected ones left out)."""
    out = []
    for f in glob.glob(os.path.join(ROOT, "videos", "**", "*"), recursive=True) + glob.glob(os.path.join(ROOT, "images", "**", "*"), recursive=True):
        if f.lower().endswith(VID_EXT) and "_rejected" not in f.replace("\\", "/"):
            out.append((os.path.getmtime(f), os.path.splitext(os.path.basename(f))[0], rel(f)))
    return [(b, p) for _, b, p in sorted(out, reverse=True)]


def video_for(name, vids):
    """The newest video named after this picture or reference: «IMG008.mp4», «IMG008_race_ab12cd34.mp4», «CH_MIMO_walk.mp4»."""
    return next((p for b, p in vids if b == name or b.startswith(name + "_")), None)


def variant_tag(model):
    """File-name tag of a voice model: 'elevenlabs/eleven-v4-turbo' -> 'eleven-v4-turbo'."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", model.split("/")[-1]) or "model"


def audio_index(lang):
    """{line id: [{name, path}]} of every voice file under audio/<lang>/ (all levels; archive/, _rejected/ and inbox/ left out), read from the disk once.
    name = 'default' for the old <id>.mp3, the model tag for <id>.<tag>.mp3, the random id for <id>_<rid>.mp3. 'default' comes first, then the oldest first;
    a browser copy « (1)» is ignored when the original is there."""
    best = {}
    for f in walk(os.path.join(ROOT, "audio", lang)):
        p = audio_parse(os.path.basename(f))
        if p and ((p[0], p[1]) not in best or (best[(p[0], p[1])][1] and not p[2])):
            best[(p[0], p[1])] = (f, p[2])
    out = {}
    for (id_, name), (f, _) in best.items():
        out.setdefault(id_, []).append(dict(name=name, path=f))
    for vs in out.values():
        vs.sort(key=lambda v: (v["name"] != "default", os.path.getmtime(v["path"]), v["path"]))
    return out


def audio_variants(lang, id_, idx=None):
    """[{name, path}] of one line: 'default' first (the old plain <id>.mp3), then the others, oldest first."""
    return list((idx if idx is not None else audio_index(lang)).get(id_, []))


def audio_choice(lang, id_, pick_map, idx=None):
    """(chosen variant dict or None, all variants): the picked one (its name, or the old file name), else the old default, else the oldest."""
    vs = audio_variants(lang, id_, idx)
    want = (pick_map or {}).get(f"{id_}.{lang}")
    ch = next((v for v in vs if v["name"] == want), None) or next((v for v in vs if want and os.path.basename(v["path"]) == want), None) or (vs[0] if vs else None)
    return ch, vs


def audio_path(lang, id_, pick_map=None, idx=None):
    ch, _ = audio_choice(lang, id_, pick_map, idx)
    return ch["path"] if ch else None


def audio_url(lang, id_, pick_map=None, idx=None):
    ch, vs = audio_choice(lang, id_, pick_map, idx)
    if not ch:
        return None, dict(names=[], chosen="")
    return f"{rel(ch['path'])}?v={int(os.path.getmtime(ch['path']))}", dict(names=[v["name"] for v in vs], chosen=ch["name"])


def archive_dir(kind, lang=""):
    """Archived pictures live in images/archive/, archived voices in audio/<lang>/archive/ (nothing is ever deleted)."""
    return os.path.join(ROOT, "images", "archive") if kind == "image" else os.path.join(ROOT, "audio", lang, "archive")


def archive_move(src, dest_dir):
    """Move a file into an archive folder (a time stamp is added when that name is already taken). Returns the new path."""
    os.makedirs(dest_dir, exist_ok=True)
    dst = os.path.join(dest_dir, os.path.basename(src))
    if os.path.exists(dst):
        stem, ext = os.path.splitext(dst)
        dst = "%s.%d%s" % (stem, time.time_ns() // 1000000, ext)
    replace_file(src, dst)
    return dst


def archived_images(id_):
    cfg = settings()
    out = []
    for f in sorted(walk(archive_dir("image"), skip=()), key=os.path.getmtime):
        name = os.path.basename(f)
        p = parse(name, cfg) or _legacy(name)
        if f.lower().endswith(IMG_EXT) and p and p["base"] == id_:
            out.append(dict(name=name, src=rel(f)))
    return out


def archived_voices(lang, id_):
    out = []
    for f in sorted(walk(archive_dir("voice", lang), skip=()), key=os.path.getmtime):
        p = audio_parse(os.path.basename(f))
        if p and p[0] == id_:
            out.append(dict(name=p[1], src=rel(f)))
    return out


def archive_item(kind, id_, name, lang="", back=False):
    """Archive (or bring back) one picture version or one voice variant. Returns the new path."""
    if kind == "image":
        if not re.fullmatch(r"IMG\d{3,4}", id_):
            raise ValueError("bad id")
        if back:
            f = next((x for x in archived_images(id_) if x["name"] == name), None)
            if not f:
                raise ValueError("not in the archive")
            dst = os.path.join(ROOT, "images", "scenes", name)
            if os.path.exists(dst):
                raise ValueError("a file with this name already exists")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            replace_file(os.path.join(ROOT, f["src"]), dst)
            return dst
        v = find_version(scan_images().get(id_, {}).get("versions", []), name)
        if not v:
            raise ValueError("no such picture file")
        moved = [archive_move(os.path.join(ROOT, f), archive_dir("image")) for f in v["files"]]  # every quality of the version goes together
        return moved[0]
    if kind != "voice" or lang not in LANGS or not re.fullmatch(r"[A-Za-z0-9_-]+", id_):
        raise ValueError("bad kind, lang or id")
    if back:
        f = next((x for x in archived_voices(lang, id_) if x["name"] == name), None)
        if not f:
            raise ValueError("not in the archive")
        dst = os.path.join(ROOT, "audio", lang, os.path.basename(f["src"]))
        if os.path.exists(dst):
            raise ValueError("a file with this name already exists")
        replace_file(os.path.join(ROOT, f["src"]), dst)
        return dst
    v = next((x for x in audio_variants(lang, id_) if x["name"] == name), None)
    if not v:
        raise ValueError("no such voice file")
    return archive_move(v["path"], archive_dir("voice", lang))
