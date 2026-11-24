# -*- coding: utf-8 -*-
"""Edits of single lines in story.txt: change, add, delete a dialogue / action / translation line, and format-issue notes."""
import glob, os, re
from kitcore import Conflict, KEYLINE, LANGS, MARKER, ROOT, SAY_KEYS, SPEECH
from story import DEC, ENC, clean_label, clean_line, clean_name, clean_tone, ensure_speaker, fmt_say, parse_scene, scene_span, split_act, split_say_head
from edits import IMG_KEYS, image_range, stale_lines


def locate(lines, d, key="index"):
    """(scene id, index counted from the scene header) of the line a request means. New form: {"image": "IMG001", key: n}, n counted from the
    image's own [IMG001] line (so the address survives moving the image to another scene). Old form: {"scene": "scene-01", key: n}."""
    if d.get("image"):
        img = str(d["image"])
        if not re.fullmatch(r"IMG\d{3,4}", img):
            raise ValueError("bad image")
        sid, s, m, end = image_range(lines, img)
        a = m + int(d[key])
        if not m <= a < end:
            raise ValueError("bad line index")
        return sid, a - s
    sid = str(d.get("scene", ""))
    if not re.fullmatch(r"scene-\d{2,3}", sid):
        raise ValueError("bad scene")
    return sid, int(d[key])


def owner_say(lines, scene_id, a):
    """The id of the dialogue line that owns line `a` (the say line itself, or its en: line); None when it is not part of a dialogue line."""
    s, e = scene_span(lines, scene_id)
    for b in parse_scene(lines[s:e])["blocks"]:
        for it in b["items"]:
            if it["k"] == "say" and a - s in (it["ln"], it["en_ln"]):
                return it["id"]
    return None


def flag_line(lines, scene_id, line_id, langs):
    """Its voice is out of date (only this line, in the languages given)."""
    if line_id:
        stale_lines(lines, scene_id, lambda it: it["id"] == line_id, langs, True)


def materialize_ids(lines, scene_id):
    """Give every dialogue line of the scene that has no «id:» yet an explicit one: exactly the id it has now (IMG001_2), so no voice file
    changes name. Done before a line is added or deleted, because those shift the old position-based ids. Returns the new line positions
    (relative to the scene header), so callers can move the index they were given."""
    s, e = scene_span(lines, scene_id)
    sc = parse_scene(lines[s:e])
    todo = [(it["ln"] + 1, it["id"]) for b in sc["blocks"] for it in b["items"] if it["k"] in SPEECH and not it.get("eid")]
    for pos, id_ in sorted(todo, reverse=True):
        lines[s + pos:s + pos] = ["id: " + id_]
    return sorted(p for p, _ in todo)


def shift(index, inserted):
    """An old line index after `inserted` lines (positions) were put into the scene."""
    return int(index) + sum(1 for p in inserted if p <= int(index))


def next_line_id(lines):
    """L001, L002 ...: the next number not used by an id: line, an audio file (also archived ones) or a voice-pick."""
    used = [int(m.group(1)) for l in lines for m in [re.match(r"\s*id:\s*L(\d+)\s*$", l)] if m]
    used += [int(m.group(1)) for f in glob.glob(os.path.join(glob.escape(ROOT), "audio", "**", "L*.mp3"), recursive=True)
             for m in [re.match(r"L(\d+)\.", os.path.basename(f))] if m]
    used += [int(m) for l in lines if l.strip().startswith("voice-pick:") for m in re.findall(r"\bL(\d+)\.", l)]
    return "L%03d" % (max(used or [0]) + 1)


def after_say(lines, a, e):
    """Index just after a say line and its id: line (where an en: line goes)."""
    return a + 2 if a + 1 < e and lines[a + 1].strip().startswith("id:") else a + 1


def edit_line(lines, scene_id, index, old, new, op="edit"):
    """Change only the text of one line (or the speaker of a say line, or add an en: line). The key never changes."""
    s, e = scene_span(lines, scene_id)
    a = s + int(index)
    if not (s < a < e):
        raise ValueError("bad line index")
    kv = KEYLINE.match(lines[a].strip())
    lid = owner_say(lines, scene_id, a)  # the line's id is read first: later steps may move line numbers (a new speaker line goes to the top)
    if op == "say":
        if not kv or kv.group(1) != "say":
            raise Conflict("این خط دیگر دیالوگ نیست؛ صفحه را دوباره بارگذاری کن.")
        head, _, body = kv.group(2).partition("|")
        name, tone = split_say_head(head)
        o, n = old, new
        if (name, tone, DEC(body.strip())) != (str(o["name"]).strip(), str(o["tone"]).strip(), str(o["text"]).strip()):
            raise Conflict("این دیالوگ بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
        nn, nt, nx = clean_name(n["name"]), clean_tone(n["tone"]), clean_line(n["text"])
        if not nx:
            raise ValueError("متن خالی است")
        if (nn, nt, nx) == (name, tone, DEC(body.strip())):
            return
        lines[a] = fmt_say(nn, nt, ENC(nx))
        if nn != name:
            ensure_speaker(lines, nn)
        flag_line(lines, scene_id, lid, LANGS if nn != name or nt != tone else ["fa"])  # another speaker or tone means another delivery
        return
    if op == "speaker":
        text = clean_name(new)
    elif op == "label":
        text = clean_label(new)
    elif op == "tone":
        text = clean_tone(new)
    else:
        text = clean_line(new)
    if not text and op not in ("label", "tone"):
        raise ValueError("متن خالی است")
    if op == "add_en":
        if not kv or kv.group(1) not in SPEECH:
            raise Conflict("این خط دیگر دیالوگ نیست؛ صفحه را دوباره بارگذاری کن.")
        at = after_say(lines, a, e)
        if at < e and lines[at].strip().startswith("en:"):
            raise Conflict("برای این خط ترجمه از قبل هست؛ صفحه را دوباره بارگذاری کن.")
        lines[at:at] = [f"en: {ENC(text)}"]
        flag_line(lines, scene_id, lid, ["en"])
        return
    if not kv or kv.group(1) not in ("env", "act", "en") + SPEECH:
        raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
    key, val = kv.group(1), kv.group(2).strip()
    if key == "act":
        lab, body = split_act(val)
        if op == "label":
            if (lab or "") != str(old).strip():
                raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
            lines[a] = f"act: {text} | {body}" if text else f"act: {body}"
            return
        if DEC(body) != str(old).strip():
            raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
        if text != DEC(body):
            lines[a] = f"act: {lab} | {ENC(text)}" if lab else f"act: {ENC(text)}"
        return
    if key == "say":
        head, _, body = val.partition("|")
        name, tone = split_say_head(head)
        body = body.strip()
        if op == "speaker":
            if name != str(old).strip():
                raise Conflict("گوینده این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
            if text == name:
                return
            lines[a] = fmt_say(text, tone, body)
            ensure_speaker(lines, text)
            flag_line(lines, scene_id, lid, LANGS)  # another speaker means another voice
            return
        if op == "tone":
            if tone != str(old).strip():
                raise Conflict("لحن این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
            if text != tone:
                lines[a] = fmt_say(name, text, body)
                flag_line(lines, scene_id, lid, LANGS)  # another tone means another delivery
            return
        if DEC(body) != str(old).strip():
            raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
        if text != DEC(body):
            lines[a] = fmt_say(name, tone, ENC(text))
            flag_line(lines, scene_id, lid, ["fa"])
        return
    if op == "speaker" or DEC(val) != str(old).strip():
        raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
    if text == DEC(val):
        return
    lines[a] = f"{key}: {ENC(text)}"
    if key == "en":
        flag_line(lines, scene_id, lid, ["en"])


def add_line(lines, scene_id, after, kind, speaker, text, label="", tone=""):
    """Insert a new dialogue (say) or scene description (act) right after the given part (its en:/notes stay attached to it)."""
    s, e = scene_span(lines, scene_id)
    a = s + int(after)
    if not (s < a < e):
        raise ValueError("bad line index")
    if kind == "say":  # a new dialogue shifts the old position-based ids of the lines after it: pin them first
        a = s + shift(after, materialize_ids(lines, scene_id))
        s, e = scene_span(lines, scene_id)
    t = clean_line(text)
    if not t:
        raise ValueError("متن خالی است")
    if kind == "act":
        lab = clean_label(label)
        new, name = (f"act: {lab} | {ENC(t)}" if lab else f"act: {ENC(t)}"), None
    elif kind == "say":
        name = clean_name(speaker)
        new = fmt_say(name, clean_tone(tone), ENC(t))
    else:
        raise ValueError("bad kind")
    l0 = lines[a].strip()
    kv = KEYLINE.match(l0)
    if MARKER.match(l0):
        skip = IMG_KEYS + ("format-issue",)
    elif kv and kv.group(1) in SPEECH:
        skip = SAY_KEYS
    else:
        skip = ("format-issue",)
    pos = a + 1
    while pos < e:
        k2 = KEYLINE.match(lines[pos].strip())
        if not k2 or k2.group(1) not in skip:
            break
        pos += 1
    lines[pos:pos] = [new] + (["id: " + next_line_id(lines), "voice-stale: fa"] if kind == "say" else [])  # a new line has no voice yet
    if name:
        ensure_speaker(lines, name)


def delete_line(lines, scene_id, index, old):
    """Remove one act / say / en line. A say line takes its en: and format-issue lines with it; env cannot be deleted."""
    sa, e = scene_span(lines, scene_id)
    a = sa + int(index)
    if not (sa < a < e):
        raise ValueError("bad line index")
    kv = KEYLINE.match(lines[a].strip())
    if not kv or kv.group(1) not in ("act", "say", "en"):
        raise Conflict("این خط بیرون از مرورگر عوض شده یا حذف‌شدنی نیست؛ صفحه را دوباره بارگذاری کن.")
    key, val = kv.group(1), kv.group(2).strip()
    cmp = DEC(val.partition("|")[2].strip()) if key == "say" else DEC(split_act(val)[1]) if key == "act" else DEC(val)
    if cmp != str(old).strip():
        raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
    if key == "say":  # pin the position-based ids of the other lines first (deleting one shifts them)
        ins = materialize_ids(lines, scene_id)
        a = sa + shift(index, ins)
        sa, e = scene_span(lines, scene_id)
    skip = SAY_KEYS if key == "say" else ("format-issue",) if key == "act" else ()
    lid = owner_say(lines, scene_id, a) if key == "en" else None
    end, had_en = a + 1, False
    while end < e:
        k2 = KEYLINE.match(lines[end].strip())
        if not k2 or k2.group(1) not in skip:
            break
        had_en = had_en or k2.group(1) == "en"
        end += 1
    del lines[a:end]
    if key == "en":  # the line stays; its English voice no longer matches (a deleted dialogue line takes its voice keys with it)
        flag_line(lines, scene_id, lid, ["en"])


def add_issue(lines, scene_id, index, message):
    """Put 'format-issue: ...' right after the given part so the AI finds it (grep format-issue)."""
    s, e = scene_span(lines, scene_id)
    a = s + int(index)
    if not (s <= a < e):
        raise ValueError("bad line index")
    kv = KEYLINE.match(lines[a].strip())
    pos = a + 1
    if MARKER.match(lines[a].strip()):
        skip = IMG_KEYS + ("format-issue",)
    elif kv and kv.group(1) in SPEECH:
        skip = SAY_KEYS
    else:
        skip = ("format-issue",)
    while pos < e:
        k2 = KEYLINE.match(lines[pos].strip())
        if not k2 or k2.group(1) not in skip:
            break
        pos += 1
    lines[pos:pos] = ["format-issue: " + (clean_line(message) or "فرمت این قسمت درست نیست")]


def clear_issue(lines, scene_id, index):
    s, e = scene_span(lines, scene_id)
    a = s + int(index)
    if not (s < a < e) or not lines[a].strip().startswith("format-issue:"):
        raise Conflict("این یادداشت دیگر نیست؛ صفحه را دوباره بارگذاری کن.")
    del lines[a]
