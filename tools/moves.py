# -*- coding: utf-8 -*-
"""Moving pictures and scene markers in story.txt. A picture is its [IMG###] line and everything under it up to the next [IMG] or scene header;
a scene is only a header line (plus its env / fx / off lines) that says «from here on: this scene». Moving a picture moves that block of text,
also across scene headers (it then belongs to the destination scene); no file on disk is touched or renamed.
The file is cut into a small model (the lines before the first scene, then per scene: head lines + picture blocks), changed, and written back with
exactly one blank line between scenes. Lines are only ever moved, never copied or dropped (except the header / env / fx / off lines of a removed scene).
Before anything moves, the scenes involved get their old position-based line ids and scene-level voice choices written under the lines themselves
(pin_scene), so no voice changes name or file because a picture changed neighbours."""
import os, re
from kitcore import BOOK_RULES, Conflict, HEADER, LANGS, MARKER, book_path
from story import ENC, DEC, parse_scene, scene_ranges, scene_span
from edits import migrate_scene_key, next_image_id, set_say_attr, set_scene_fx, stale_lines
from lineedits import materialize_ids

IMG_ID = BOOK_RULES["story"]["item_re"]
SCENE_ID = BOOK_RULES["story"]["section_re"]
INFO_KEYS = ("env", "fx", "off", "model")  # lines under a scene header whose loss the user must confirm (force) when the header is removed


def pin_scene(lines, sid, book="story"):
    """Make a scene independent of its position: every dialogue line gets its explicit «id:», and the old scene-level «voice-pick:» /
    «voice-stale:» entries move under the lines they are about (a line's own choice wins over an old scene-level one). Entries that point at
    a line that no longer exists stay where they are."""
    materialize_ids(lines, sid, book=book)
    s, e = scene_span(lines, sid, book=book)
    sc = parse_scene(lines[s:e], book=book)
    if sc["legacy_pick"]:
        items = [it for b in sc["blocks"] for it in b["items"] if it["k"] == "say"]
        by_id, want, orphans = {it["id"]: it for it in items}, {}, {}
        for key, v in sc["legacy_pick"].items():
            lid, _, lg = key.rpartition(".")
            it = by_id.get(lid)
            if it is None or lg not in LANGS:
                orphans[key] = v
            elif lg not in it["voice"]:
                want.setdefault(lid, {})[lg] = v
        for it in sorted(items, key=lambda x: -x["ln"]):
            if it["id"] in want:
                cur = dict(it["voice"], **want[it["id"]])
                set_say_attr(lines, s + it["ln"], "voice", ", ".join(f"{lg}={cur[lg]}" for lg in LANGS if lg in cur))
        migrate_scene_key(lines, sid, "voice-pick", orphans, book=book)
    stale_lines(lines, sid, lambda it: False, LANGS, True, book=book)  # moves an old scene-level flag onto every line of the scene


def split(lines, book="story"):
    """-> (lines before the first scene, [scene]) where scene = {id, head: chunk, blocks: [chunk]} and chunk = {id, lines, gap} (gap = blank lines
    that followed it; the last chunk of a scene has none, the blank line between scenes is written by join)."""
    marker_re = BOOK_RULES[book]["marker_re"]
    rs = scene_ranges(lines, book=book)
    if not rs:
        return list(lines), []
    scenes = []
    for sid, s, e in rs:
        cuts = [i for i in range(s + 1, e) if marker_re.match(lines[i].strip())]
        edges = [s] + cuts + [e]
        chunks = []
        for k in range(len(edges) - 1):
            part = lines[edges[k]:edges[k + 1]]
            n = 0
            while part and not part[-1].strip():
                part.pop()
                n += 1
            chunks.append(dict(id=marker_re.match(part[0].strip()).group(1) if k else None, lines=part, gap=n))
        chunks[-1]["gap"] = 0
        scenes.append(dict(id=sid, head=chunks[0], blocks=chunks[1:]))
    return list(lines[:rs[0][1]]), scenes


def join(pre, scenes):
    out = list(pre)
    for si, sc in enumerate(scenes):
        chunks = [sc["head"]] + sc["blocks"]
        for ci, ch in enumerate(chunks):
            out += ch["lines"] + [""] * (ch["gap"] if ci < len(chunks) - 1 else 0)
        if si < len(scenes) - 1:
            out.append("")
    return out


def order(scenes):
    return [(sc["id"], [b["id"] for b in sc["blocks"]]) for sc in scenes]


def find_image(scenes, img, book="story"):
    """(scene index, block index) of the first [img] marker; Conflict when it is not there (the page is out of date)."""
    for si, sc in enumerate(scenes):
        for bi, b in enumerate(sc["blocks"]):
            if b["id"] == img:
                return si, bi
    fname = os.path.basename(book_path(book))
    raise Conflict(f"تصویر {img} در {fname} نیست؛ صفحه را دوباره بارگذاری کن.")


def find_scene(scenes, sid, book="story"):
    for si, sc in enumerate(scenes):
        if sc["id"] == sid:
            return si
    fname = os.path.basename(book_path(book))
    raise Conflict(f"صحنهٔ {sid} در {fname} نیست؛ صفحه را دوباره بارگذاری کن.")


def clean_title(title, default=True):
    title = re.sub(r"\s+", " ", str(title or "")).strip() or ("صحنهٔ جدید" if default else "")
    if "|" in title or len(title) > 60:
        raise ValueError("عنوان صحنه باید تا ۶۰ حرف باشد و | نداشته باشد")
    return title


def env_lines(env):
    """A text (or a list of texts) -> the «env: ...» lines it stands for (a line break inside one text is stored as \\n)."""
    parts = [env] if isinstance(env, str) else list(env or [])
    out = []
    for p in parts:
        t = "\n".join(l.rstrip() for l in str(p).replace("\r\n", "\n").split("\n")).strip()
        if len(t) > 2000:
            raise ValueError("متن محیط خیلی بلند است")
        if t:
            out.append("env: " + ENC(t))
    return out


def next_scene_id(scenes, book="story"):
    prefix = "ref-" if book == "refs" else "scene-"
    plen = len(prefix)
    nums = [int(sc["id"][plen:]) for sc in scenes if sc["id"].startswith(prefix) and sc["id"][plen:].isdigit()]
    num = max(nums or [0]) + 1
    if num > 999:
        raise ValueError("too many scenes")
    return f"{prefix}{num:02d}"


def _take(scenes, ids, book="story"):
    """Cut the blocks of `ids` out of the model; returns them in file order."""
    pos = sorted(find_image(scenes, i, book=book) for i in ids)
    taken = [scenes[si]["blocks"][bi] for si, bi in pos]
    for si, bi in reversed(pos):
        del scenes[si]["blocks"][bi]
    return taken


def _put(scenes, blocks, before=None, after=None, to_end=None, book="story"):
    if to_end:
        sc = scenes[find_scene(scenes, to_end, book=book)]
        sc["blocks"] += blocks
        return sc["id"]
    si, bi = find_image(scenes, before or after, book=book)
    scenes[si]["blocks"][bi + (0 if before else 1):bi + (0 if before else 1)] = blocks
    return scenes[si]["id"]


def _target(before, after, to_end, book="story"):
    rules = BOOK_RULES[book]
    given = [x for x in (before, after, to_end) if x]
    if len(given) != 1:
        raise ValueError("دقیقاً یکی از before و after و to_end_of_scene لازم است")
    if (before or after) and not rules["item_re"].fullmatch(str(before or after)):
        raise ValueError("bad image")
    if to_end and not rules["section_re"].fullmatch(str(to_end)):
        raise ValueError("bad scene")
    return (str(before) if before else None), (str(after) if after else None), (str(to_end) if to_end else None)


def move_images(lines, ids, before=None, after=None, to_end=None, book="story"):
    """Move the pictures `ids` (they keep their order in the file) to just before / after one picture, or to the end of a scene. Returns the scene
    they end up in, or None when nothing would change (then `lines` is not touched). Conflict when a picture or scene is not in the file."""
    rules = BOOK_RULES[book]
    ids = [str(i) for i in ids]
    if not ids or len(ids) > 200 or len(set(ids)) != len(ids) or not all(rules["item_re"].fullmatch(i) for i in ids):
        raise ValueError("bad ids")
    before, after, to_end = _target(before, after, to_end, book=book)
    anchor = before or after
    if anchor in ids:
        if len(ids) == 1:
            find_image(split(lines, book=book)[1], anchor, book=book)
            return None  # onto itself
        raise ValueError("جای مقصد خودش جزو تصویرهای جابه‌جاشونده است")
    pre, scenes = split(lines, book=book)
    for i in ids:
        si, _ = find_image(scenes, i, book=book)
        if book == "story" and scenes[si]["id"] == "scene-00":
            raise ValueError("تصویر تامبنیل (scene-00) جابه‌جا نمی‌شود")
    dest = scenes[find_image(scenes, anchor, book=book)[0]]["id"] if anchor else scenes[find_scene(scenes, to_end, book=book)]["id"]
    if book == "story" and dest == "scene-00":
        raise ValueError("تصویری به صحنهٔ تامبنیل (scene-00) نمی‌رود")
    src = {scenes[find_image(scenes, i, book=book)[0]]["id"] for i in ids}
    before_order = order(scenes)
    _put(scenes, _take(scenes, ids, book=book), before, after, to_end, book=book)
    if order(scenes) == before_order:
        return None
    for sid in sorted(src | {dest}):  # pin first (this changes lines), then cut again on the pinned text
        pin_scene(lines, sid, book=book)
    pre, scenes = split(lines, book=book)
    scene = _put(scenes, _take(scenes, ids, book=book), before, after, to_end, book=book)
    lines[:] = join(pre, scenes)
    return scene


def set_scene_env(lines, sid, env, book="story"):
    """Replace the env lines of a scene (the ones under the header, before its first picture)."""
    rules = BOOK_RULES[book]
    s, e = scene_span(lines, sid, book=book)
    first = next((i for i in range(s + 1, e) if rules["marker_re"].match(lines[i].strip())), e)
    keep = [l for l in lines[s + 1:first] if not l.strip().startswith("env:")]
    lines[s + 1:first] = env_lines(env) + keep


def scene_mark(lines, op, d, book="story"):
    """The three edits of the scene markers. insert: {before: IMG, title, env?} starts a new scene at that picture (it takes that picture and all
    the ones after it in the scene). remove: {scene, force?} deletes the header (and its env / fx / off / model lines, only with force when there
    are such lines) so the pictures join the previous scene. edit: {scene, title?, env?, fx?}. Returns {scene} (the new id for insert)."""
    rules = BOOK_RULES[book]
    if op == "insert":
        img = str(d.get("before", ""))
        if not rules["item_re"].fullmatch(img):
            raise ValueError("bad image")
        title = clean_title(d.get("title"))
        env = env_lines(d.get("env", ""))
        pre, scenes = split(lines, book=book)
        si, bi = find_image(scenes, img, book=book)
        if book == "story" and scenes[si]["id"] == "scene-00":
            raise ValueError("در صحنهٔ تامبنیل (scene-00) صحنه‌ای شروع نمی‌شود")
        old = scenes[si]["id"]
        pin_scene(lines, old, book=book)  # the pictures after the cut get a new scene: their position-based line ids and scene-level voice keys must not depend on it
        pre, scenes = split(lines, book=book)
        si, bi = find_image(scenes, img, book=book)
        sid = next_scene_id(scenes, book=book)
        new = dict(id=sid, head=dict(id=None, lines=[f"=== {sid} | {title} | - ==="] + env, gap=0), blocks=scenes[si]["blocks"][bi:])
        scenes[si]["blocks"] = scenes[si]["blocks"][:bi]
        scenes.insert(si + 1, new)
        lines[:] = join(pre, scenes)
        return {"scene": sid}
    sid = str(d.get("scene", ""))
    if not rules["section_re"].fullmatch(sid):
        raise ValueError("bad scene")
    if op == "remove":
        pre, scenes = split(lines, book=book)
        si = find_scene(scenes, sid, book=book)
        if book == "story" and sid == "scene-00":
            raise ValueError("صحنهٔ تامبنیل (scene-00) برداشته نمی‌شود")
        if si == 0 or (book == "story" and scenes[si - 1]["id"] == "scene-00"):
            raise ValueError("صحنه‌ای که قبلش صحنهٔ تامبنیل یا هیچ صحنه‌ای نیست را نمی‌شود با قبلی ادغام کرد")
        if "old_title" in d and str(d["old_title"]) != rules["header_re"].match(scenes[si]["head"]["lines"][0].strip()).group(2):
            raise Conflict("عنوان این صحنه بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
        pin_scene(lines, sid, book=book)
        pin_scene(lines, scenes[si - 1]["id"], book=book)  # the previous scene's own scene-level flags must not spread over the pictures that join it
        pre, scenes = split(lines, book=book)
        si = find_scene(scenes, sid, book=book)
        keys = []
        for l in scenes[si]["head"]["lines"][1:]:
            m = re.match(r"^([a-z][a-z-]*):", l.strip())
            if not m or m.group(1) not in INFO_KEYS + ("voice-pick", "voice-stale"):
                raise ValueError("زیر عنوان این صحنه متن یا خط دیگری هست؛ اول آن را زیر یک تصویر ببر یا پاک کن.")
            keys.append(m.group(1))
        if keys and not d.get("force"):
            raise ValueError("این صحنه خطّ %s دارد و با برداشتن عنوانش از دست می‌رود؛ با force دوباره بفرست." % "، ".join(sorted(set(keys))))
        prev = scenes[si - 1]
        for b in prev["blocks"][-1:]:
            b["gap"] = 0
        prev["blocks"] += scenes[si]["blocks"]
        del scenes[si]
        lines[:] = join(pre, scenes)
        return {"scene": prev["id"]}
    if op == "edit":
        s, e = scene_span(lines, sid, book=book) if any(r[0] == sid for r in scene_ranges(lines, book=book)) else (None, None)
        if s is None:
            fname = os.path.basename(book_path(book))
            raise Conflict(f"صحنهٔ {sid} در {fname} نیست؛ صفحه را دوباره بارگذاری کن.")
        sc = parse_scene(lines[s:e], book=book)
        old = d.get("old") or {}
        for key, cur in (("title", sc["title"]), ("env", "\n".join(x["text"] for x in sc["env"])), ("fx", sc["fx"])):
            if key in old and str(old[key]) != cur:
                raise Conflict("این صحنه بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
        if d.get("title") is not None:
            title = clean_title(d["title"], default=False)
            if not title:
                raise ValueError("عنوان صحنه خالی است")
            h = rules["header_re"].match(lines[s].strip())
            lines[s] = f"=== {sid} | {title} | {h.group(3)} ==="
        if d.get("env") is not None:
            set_scene_env(lines, sid, d["env"], book=book)
        if d.get("fx") is not None:
            set_scene_fx(lines, sid, str(d["fx"])[:2000], book=book)
        return {"scene": sid}
    raise ValueError("op must be insert, remove or edit")


def add_image_at(lines, before=None, after=None, scene=None, image_id=None, book="story"):
    """A new picture slot [IMG###] just before / after a picture, or at the end of a scene. `image_id` places a picture id that exists without a
    marker (files or a prompt) instead of a new number; Conflict when that id already has a marker. Returns the id."""
    rules = BOOK_RULES[book]
    before, after, to_end = _target(before, after, scene, book=book)
    if image_id is not None:
        image_id = str(image_id)
        if not rules["item_re"].fullmatch(image_id):
            raise ValueError("bad image id")
        if any(rules["marker_re"].match(l.strip()) and l.strip() == f"[{image_id}]" for l in lines):
            fname = os.path.basename(book_path(book))
            raise Conflict(f"{image_id} از قبل در {fname} جا دارد؛ صفحه را دوباره بارگذاری کن.")
    else:
        if book == "refs":
            raise ValueError("image_id is required in refs mode")
        n = next_image_id(lines)
        if n > 9999:
            raise ValueError("too many pictures")
        image_id = f"IMG{n:03d}"
    pre, scenes = split(lines, book=book)
    si = find_image(scenes, before or after, book=book)[0] if (before or after) else find_scene(scenes, to_end, book=book)
    if book == "story" and scenes[si]["id"] == "scene-00":
        raise ValueError("تصویری به صحنهٔ تامبنیل (scene-00) اضافه نمی‌شود")
    pin_scene(lines, scenes[si]["id"], book=book)  # a new marker may join or split an old shared block: pin the old line ids first
    pre, scenes = split(lines, book=book)
    _put(scenes, [dict(id=image_id, lines=[f"[{image_id}]"], gap=0)], before, after, to_end, book=book)
    lines[:] = join(pre, scenes)
    return image_id
