# -*- coding: utf-8 -*-
"""What is on disk next to the text: picture versions, references, videos, voice variants, and the archive folders (nothing here deletes a file)."""
import glob, os, re, time
from kitcore import IMG_EXT, LANGS, ROOT, VID_EXT, replace_file


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def scan_images():
    """{IMG###: {versions: [{name, src}] oldest first, rejected: [src]}}. Any file name that starts with the id counts (random suffixes included)."""
    cur, rej = {}, {}
    for f in glob.glob(os.path.join(ROOT, "images", "scenes", "**", "IMG*"), recursive=True):
        m = re.match(r"(IMG\d{3})", os.path.basename(f))
        if m and f.lower().endswith(IMG_EXT):
            (rej if "_rejected" in f.replace("\\", "/") else cur).setdefault(m.group(1), []).append(f)
    out = {}
    for id_ in set(cur) | set(rej):
        c = sorted(cur.get(id_, []), key=lambda f: (os.path.getmtime(f), f))
        out[id_] = dict(versions=[dict(name=os.path.basename(f), src=rel(f)) for f in c],
                        rejected=[rel(x) for x in sorted(rej.get(id_, []), key=os.path.getmtime, reverse=True)])
    return out


def image_state(im, scan):
    """What the page needs about a picture's files: shown file, all versions, the chosen one. A chosen picture counts as approved."""
    vs = scan.get("versions", [])
    names = [v["name"] for v in vs]
    picked = im["pick"] if im["pick"] in names else ""
    vi = names.index(picked) if picked else len(vs) - 1
    return dict(src=vs[vi]["src"] if vs else None, versions=vs, vi=vi, picked=picked, rejected=scan.get("rejected", []),
                status=im["status"] or ("ok" if picked else ""))


def scan_refs(prompts):
    used = {}
    for id_, rec in prompts.items():
        if id_.startswith("IMG"):
            for r in rec["refs"]:
                used.setdefault(r, []).append(id_)
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "images", "refs", "*", "*"))):
        if f.lower().endswith(IMG_EXT):
            name = re.sub(r"_[0-9a-f]{8}$", "", os.path.splitext(os.path.basename(f))[0])
            out.append(dict(name=name, kind=os.path.basename(os.path.dirname(f)), src=rel(f), used=used.get(name, []),
                            prompt=(prompts.get(name) or {}).get("prompt", "")))
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


def audio_variants(lang, id_):
    """[{name, path}]: 'default' is the old plain <id>.mp3, the others are <id>.<tag>.mp3 (oldest first)."""
    d = os.path.join(ROOT, "audio", lang)
    out = []
    if os.path.exists(os.path.join(d, id_ + ".mp3")):
        out.append(dict(name="default", path=os.path.join(d, id_ + ".mp3")))
    others = sorted(glob.glob(os.path.join(glob.escape(d), glob.escape(id_) + ".*.mp3")), key=lambda f: (os.path.getmtime(f), f))
    return out + [dict(name=os.path.basename(f)[len(id_) + 1:-4], path=f) for f in others]


def audio_choice(lang, id_, pick_map):
    """(chosen variant dict or None, all variants): the picked one, else the old default, else the newest."""
    vs = audio_variants(lang, id_)
    want = (pick_map or {}).get(f"{id_}.{lang}")
    ch = next((v for v in vs if v["name"] == want), None) or (vs[0] if vs else None)
    return ch, vs


def audio_path(lang, id_, pick_map=None):
    ch, _ = audio_choice(lang, id_, pick_map)
    return ch["path"] if ch else None


def audio_url(lang, id_, pick_map=None):
    ch, vs = audio_choice(lang, id_, pick_map)
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
    return [dict(name=os.path.basename(f), src=rel(f)) for f in sorted(glob.glob(os.path.join(glob.escape(archive_dir("image")), id_ + "*")), key=os.path.getmtime)
            if f.lower().endswith(IMG_EXT)]


def archived_voices(lang, id_):
    d = glob.escape(archive_dir("voice", lang))
    fs = glob.glob(os.path.join(d, glob.escape(id_) + ".mp3")) + glob.glob(os.path.join(d, glob.escape(id_) + ".*.mp3"))
    return [dict(name=os.path.basename(f)[len(id_) + 1:-4] or "default", src=rel(f)) for f in sorted(fs, key=os.path.getmtime)]


def archive_item(kind, id_, name, lang="", back=False):
    """Archive (or bring back) one picture version or one voice variant. Returns the new path."""
    if kind == "image":
        if not re.fullmatch(r"IMG\d{3}", id_):
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
        v = next((x for x in scan_images().get(id_, {}).get("versions", []) if x["name"] == name), None)
        if not v:
            raise ValueError("no such picture file")
        return archive_move(os.path.join(ROOT, v["src"]), archive_dir("image"))
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
