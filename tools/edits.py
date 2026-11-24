# -*- coding: utf-8 -*-
"""Every change the page can make, as small raw-line edits of story.txt / prompts.txt. Nothing else in a file is ever touched."""
import re
from kitcore import HEADER, KEYLINE, LANGS, LOCK, MARKER, SAY_KEYS, STORY, read_lines, write_lines
from story import parse_prompts, parse_scene, scene_ranges, scene_span, story_scenes
from media import scan_images, variant_tag


TOP_KEYS = ("env", "voice-stale", "model", "voice-pick", "off")  # scene-level lines right under the header


IMG_KEYS = ("status", "note", "image-stale", "fx", "pick", "off")


def patch_image(lines, img_id, status=None, note=None, stale=None, fx=None, pick=None, off=None):
    idx = next((i for i, l in enumerate(lines) if l.strip() == f"[{img_id}]"), None)
    if idx is None:
        raise ValueError("image not in story")
    j, cur = idx + 1, dict(status="", note="", stale=False, fx="", pick="", off=False)
    while j < len(lines):
        kv = KEYLINE.match(lines[j].strip())
        if not kv or kv.group(1) not in IMG_KEYS:
            break
        v = kv.group(2).strip()
        k = kv.group(1)
        if k == "image-stale":
            cur["stale"] = v.lower() in ("yes", "true", "1")
        elif k == "off":
            cur["off"] = v.lower() in ("yes", "true", "1")
        else:
            cur[k] = v
        j += 1
    if status is not None:
        cur["status"] = status
    if note is not None:
        cur["note"] = note.strip().replace("\r\n", "\n").replace("\n", "\\n")
    if stale is not None:
        cur["stale"] = bool(stale)
    if fx is not None:
        cur["fx"] = fx.strip().replace("\r\n", "\n").replace("\n", "\\n")
    if pick is not None:
        cur["pick"] = pick
    if off is not None:
        cur["off"] = bool(off)
    new = ([f"status: {cur['status']}"] if cur["status"] else []) + ([f"pick: {cur['pick']}"] if cur["pick"] else []) \
        + (["off: yes"] if cur["off"] else []) + (["image-stale: yes"] if cur["stale"] else []) \
        + ([f"note: {cur['note']}"] if cur["note"] else []) + ([f"fx: {cur['fx']}"] if cur["fx"] else [])
    lines[idx + 1:j] = new


def image_range(lines, img_id):
    """(scene id, scene start, marker line, end) of a picture: the lines marker+1 .. end-1 belong to it (up to the next marker or the scene's end)."""
    for sid, s, e in scene_ranges(lines):
        for i in range(s + 1, e):
            if lines[i].strip() == f"[{img_id}]":
                return sid, s, i, next((j for j in range(i + 1, e) if MARKER.match(lines[j].strip())), e)
    raise ValueError("image not in story")


def say_attr_span(lines, a):
    """End (exclusive) of the keys that hang under the dialogue line at `a`: id:, en:, voice:, voice-stale:, format-issue:."""
    e = a + 1
    while e < len(lines):
        kv = KEYLINE.match(lines[e].strip())
        if not kv or kv.group(1) not in SAY_KEYS:
            break
        e += 1
    return e


def set_say_attr(lines, a, key, text):
    """Write (or, when text is empty, remove) one key under the dialogue line at `a`, in the usual order id, en, voice, voice-stale, issues."""
    end = say_attr_span(lines, a)
    keys = [KEYLINE.match(lines[j].strip()).group(1) for j in range(a + 1, end)]
    new = [f"{key}: {text}"] if text else []
    if key in keys:
        j = a + 1 + keys.index(key)
        lines[j:j + 1] = new
    elif new:
        at = next((a + 1 + k for k, x in enumerate(keys) if SAY_KEYS.index(x) > SAY_KEYS.index(key)), end)
        lines[at:at] = new


def find_say(lines, line_id):
    """(scene id, absolute line index) of the dialogue line with this id (its own id: or the old position name)."""
    for sid, s, e in scene_ranges(lines):
        for b in parse_scene(lines[s:e])["blocks"]:
            for it in b["items"]:
                if it["k"] == "say" and it.get("id") == line_id:
                    return sid, s + it["ln"]
    raise ValueError("no such dialogue line")


def langs_text(langs):
    return ", ".join(x for x in LANGS if x in langs)


def migrate_scene_key(lines, scene_id, key, keep):
    """Rewrite the old scene-level «voice-pick:» / «voice-stale:» line(s) of a scene so that only `keep` stays (a dict / set; empty = the line goes)."""
    s, e = scene_span(lines, scene_id)
    pos = parse_scene(lines[s:e])["legacy_ln"][key]
    if not pos:
        return
    text = ""
    if keep:
        text = f"{key}: " + (", ".join(f"{k}={v}" for k, v in sorted(keep.items())) if isinstance(keep, dict) else langs_text(keep))
    for k, j in enumerate(reversed(pos)):
        lines[s + j:s + j + 1] = [text] if (k == len(pos) - 1 and text) else []


def stale_lines(lines, scene_id, want, langs, value):
    """Mark (value True) or clear the out-of-date flag of `langs` on the dialogue lines of a scene that `want(item)` accepts. The flag lives under
    each line («voice-stale: fa»). An old scene-level flag for a language is first moved onto every dialogue line of the scene, so only the
    asked lines change and nothing else loses its flag."""
    langs = {x for x in langs if x in LANGS}
    for lg in sorted(langs):
        s, e = scene_span(lines, scene_id)
        sc = parse_scene(lines[s:e])
        if lg not in sc["legacy_stale"]:
            continue
        migrate_scene_key(lines, scene_id, "voice-stale", sc["legacy_stale"] - {lg})
        s, e = scene_span(lines, scene_id)
        for it in sorted([it for b in parse_scene(lines[s:e])["blocks"] for it in b["items"] if it["k"] == "say"], key=lambda x: -x["ln"]):
            set_say_attr(lines, s + it["ln"], "voice-stale", langs_text(set(it["stale_own"]) | {lg}))
    s, e = scene_span(lines, scene_id)
    items = [it for b in parse_scene(lines[s:e])["blocks"] for it in b["items"] if it["k"] == "say" and want(it)]
    for it in sorted(items, key=lambda x: -x["ln"]):
        cur = set(it["stale_own"])
        new = cur | langs if value else cur - langs
        if new != cur:
            set_say_attr(lines, s + it["ln"], "voice-stale", langs_text(new))


def set_stale(lines, line_id, langs, value=True):
    """The out-of-date flag of one dialogue line (by its id)."""
    sid, _ = find_say(lines, line_id)
    stale_lines(lines, sid, lambda it: it["id"] == line_id, langs, value)


def set_flag(lines, scene_id, lang, value):
    """Old name: flag every dialogue line of a scene (kept for old callers; new code flags single lines)."""
    stale_lines(lines, scene_id, lambda it: True, [lang], value)


def set_line_pick(lines, line_id, lang, variant):
    """The voice variant the user chose for one line: «voice: fa=<variant>, en=<variant>» under the line (empty variant = no choice).
    An old scene-level «voice-pick:» entry for the same line and language is removed (it is the one that was just replaced). False when
    there is no such line."""
    try:
        sid, _ = find_say(lines, line_id)
    except ValueError:
        return False
    s, e = scene_span(lines, sid)
    legacy = dict(parse_scene(lines[s:e])["legacy_pick"])
    if legacy.pop(f"{line_id}.{lang}", None) is not None:
        migrate_scene_key(lines, sid, "voice-pick", legacy)
    sid, a = find_say(lines, line_id)
    s, e = scene_span(lines, sid)
    it = next(it for b in parse_scene(lines[s:e])["blocks"] for it in b["items"] if it["k"] == "say" and it["id"] == line_id)
    cur = dict(it["voice"])
    if variant:
        cur[lang] = variant
    else:
        cur.pop(lang, None)
    set_say_attr(lines, a, "voice", ", ".join(f"{lg}={cur[lg]}" for lg in LANGS if lg in cur))
    return True


def set_voice_picks(lines, scene_id, picks):
    """Old name: picks = {'IMG001_1.fa': 'eleven-v3'}; an empty value removes that choice. Each one is written under its own line."""
    for k, v in picks.items():
        id_, _, lang = k.rpartition(".")
        if lang in LANGS:
            set_line_pick(lines, id_, lang, v)


def pick_made(items, res, lang):
    """The voice that was just made becomes the chosen one of its line (the user can switch back on the page)."""
    made = [it for it in items if res.get(it["id"]) == "ok"]
    if made:
        with LOCK:
            lines = read_lines(STORY)
            for it in made:
                set_line_pick(lines, it["id"], lang, variant_tag(it["model"]))
            write_lines(STORY, lines)


def set_scene_fx(lines, scene_id, text):
    """Write (or remove, when empty) the scene's own «fx:» line, right under the scene header lines (before the first picture)."""
    s, e = scene_span(lines, scene_id)
    first_img = next((i for i in range(s + 1, e) if MARKER.match(lines[i].strip())), e)
    pos = next((i for i in range(s + 1, first_img) if lines[i].strip().startswith("fx:")), None)
    text = text.strip().replace("\r\n", "\n").replace("\n", "\\n")
    new = [f"fx: {text}"] if text else []
    if pos is not None:
        lines[pos:pos + 1] = new
    elif new:
        k = s + 1
        while k < e and lines[k].strip().split(":")[0] in TOP_KEYS:
            k += 1
        lines[k:k] = new


def set_scene_model(lines, scene_id, model):
    """Write (or remove, when model is empty) the scene's «model:» line."""
    s, e = scene_span(lines, scene_id)
    pos = next((i for i in range(s + 1, e) if lines[i].strip().startswith("model:")), None)
    new = [f"model: {model}"] if model else []
    if pos is not None:
        lines[pos:pos + 1] = new
    elif new:
        k = s + 1
        while k < e and lines[k].strip().split(":")[0] in TOP_KEYS:
            k += 1
        lines[k:k] = new


def set_default_model(lines, model):
    pos = next((i for i, l in enumerate(lines) if l.startswith("tts-model:")), None)
    if pos is not None:
        lines[pos] = f"tts-model: {model}"
        return
    h = next((i for i, l in enumerate(lines) if HEADER.match(l.strip())), len(lines))
    lines[h:h] = ["# مدل پیش‌فرض تولید صدا؛ هر صحنه با یک خط «model:» می‌تواند مدل خودش را داشته باشد", f"tts-model: {model}", ""]


def set_scene_off(lines, scene_id, off):
    """Set a scene aside (or bring it back): one «off: yes» line under the header. Text, pictures and audio stay where they are."""
    s_, e = scene_span(lines, scene_id)
    first_img = next((i for i in range(s_ + 1, e) if MARKER.match(lines[i].strip())), e)
    pos = next((i for i in range(s_ + 1, first_img) if lines[i].strip().startswith("off:")), None)
    new = ["off: yes"] if off else []
    if pos is not None:
        lines[pos:pos + 1] = new
    elif new:
        k = s_ + 1
        while k < e and lines[k].strip().split(":")[0] in TOP_KEYS:
            k += 1
        lines[k:k] = new


def move_scene(lines, scene_id, step):
    """Swap a scene with its neighbour (step -1 = up, +1 = down). Only the order of the blocks changes; ids and file names stay.
    The thumbnail scene-00 stays first."""
    rs = scene_ranges(lines)
    i = next((k for k, r in enumerate(rs) if r[0] == scene_id), None)
    j = None if i is None else i + (-1 if step < 0 else 1)
    if i is None or j < 0 or j >= len(rs):
        raise ValueError("can't move there")
    if "scene-00" in (rs[i][0], rs[j][0]):
        raise ValueError("scene-00 (thumbnail) stays first")
    a, b = sorted((i, j))
    first, last = rs[a][1], rs[b][2]
    blocks = [list(lines[rs[k][1]:rs[k][2]]) for k in range(a, b + 1)]
    blocks[0], blocks[-1] = blocks[-1], blocks[0]
    out = []
    for k, bl in enumerate(blocks):
        while bl and not bl[-1].strip():
            bl.pop()
        out += bl + ([""] if k < len(blocks) - 1 or last < len(lines) else [])
    lines[first:last] = out


def next_image_id(lines):
    used = [int(m.group(1)[3:]) for l in lines for m in [MARKER.match(l.strip())] if m]
    used += [int(k[3:]) for k in scan_images() if re.fullmatch(r"IMG\d{3,4}", k)] + [int(k[3:]) for k in parse_prompts() if re.fullmatch(r"IMG\d{3,4}", k)]
    return max(used or [0]) + 1


def add_scene(lines, after, title, images):
    """A new scene with `images` empty picture slots, put after the scene `after` (or at the end). Returns the new scene id."""
    title = re.sub(r"\s+", " ", str(title or "")).strip() or "صحنهٔ جدید"
    if "|" in title or len(title) > 60:
        raise ValueError("عنوان صحنه باید تا ۶۰ حرف باشد و | نداشته باشد")
    images = int(images)
    if not 0 <= images <= 12:
        raise ValueError("تعداد تصویر بین ۰ تا ۱۲")
    rs = scene_ranges(lines)
    nums = [int(r[0][6:]) for r in rs]
    num = max(nums or [0]) + 1
    if num > 999:
        raise ValueError("too many scenes")
    sid = "scene-%02d" % num
    first = next_image_id(lines)
    if first + images - 1 > 9999:
        raise ValueError("too many pictures")
    block = [f"=== {sid} | {title} | - ==="] + [f"[IMG{first + k:03d}]" for k in range(images)]
    if after:
        at = next((r[2] for r in rs if r[0] == after), None)
        if at is None:
            raise ValueError("scene not found")
    else:
        at = len(lines)
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    tail = [] if at >= len(lines) or not lines[at].strip() else [""]  # keep exactly one blank line between scenes
    lines[at:at] = ([""] if at else []) + block + tail
    return sid


def add_image(lines, scene_id):
    """One more empty picture slot at the end of an existing scene. Returns the new id (e.g. IMG007)."""
    s_, e = scene_span(lines, scene_id)
    n = next_image_id(lines)
    if n > 9999:
        raise ValueError("too many pictures")
    while e > s_ + 1 and not lines[e - 1].strip():
        e -= 1
    lines[e:e] = [f"[IMG{n:03d}]"]
    return f"IMG{n:03d}"


def mark_stale(lines, scene_ids=None, speaker=None):
    """Both voices out of date, on the dialogue lines of these scenes (all scenes when none are given), only the speaker's when one is given."""
    for sc in story_scenes(lines):
        if scene_ids is None or sc["id"] in scene_ids:
            stale_lines(lines, sc["id"], lambda it: speaker is None or it["sp"] == speaker, LANGS, True)


def speech_scenes(lines, speaker=None, own_model=None):
    """Scene ids that have dialogue (of this speaker; only scenes with / without their own model when own_model is given)."""
    out = []
    for sc in story_scenes(lines):
        if own_model is not None and bool(sc["model"]) != own_model:
            continue
        if any(it["k"] == "say" and (speaker is None or it["sp"] == speaker) for b in sc["blocks"] for it in b["items"]):
            out.append(sc["id"])
    return out
