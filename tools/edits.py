# -*- coding: utf-8 -*-
"""Every change the page can make, as small raw-line edits of story.txt / prompts.txt. Nothing else in a file is ever touched."""
import re
from kitcore import Conflict, HEADER, KEYLINE, LANGS, LOCK, MARKER, SPEECH, STORY, read_lines, write_lines
from story import DEC, ENC, clean_label, clean_line, clean_name, clean_tone, ensure_speaker, fmt_say, parse_prompts, prompt_ranges, scene_ranges, scene_span, split_act, split_say_head, story_scenes
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


def set_flag(lines, scene_id, lang, value):
    s, e = next(((s, e) for i, s, e in scene_ranges(lines) if i == scene_id), (None, None))
    if s is None:
        raise ValueError("scene not found")
    flags, pos = set(), None
    for i in range(s + 1, e):
        if lines[i].strip().startswith("voice-stale:"):
            flags = {x.strip() for x in lines[i].split(":", 1)[1].split(",") if x.strip() in LANGS}
            pos = i
            break
    (flags.add if value else flags.discard)(lang)
    new = [f"voice-stale: {', '.join(x for x in LANGS if x in flags)}"] if flags else []
    if pos is not None:
        lines[pos:pos + 1] = new
    elif new:
        k = s + 1
        while k < e and lines[k].strip().startswith("env:"):
            k += 1
        lines[k:k] = new


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


def set_voice_picks(lines, scene_id, picks):
    """picks = {'IMG001_1.fa': 'eleven-v3'}; an empty value removes that choice. One «voice-pick:» line under the scene header."""
    s_, e = scene_span(lines, scene_id)
    pos = next((i for i in range(s_ + 1, e) if lines[i].strip().startswith("voice-pick:")), None)
    cur = {}
    if pos is not None:
        cur = {k.strip(): v.strip() for k, _, v in (x.partition("=") for x in lines[pos].split(":", 1)[1].split(",")) if k.strip() and v.strip()}
    for k, v in picks.items():
        if v:
            cur[k] = v
        else:
            cur.pop(k, None)
    new = ["voice-pick: " + ", ".join(f"{k}={v}" for k, v in sorted(cur.items()))] if cur else []
    if pos is not None:
        lines[pos:pos + 1] = new
    elif new:
        k = s_ + 1
        while k < e and lines[k].strip().split(":")[0] in TOP_KEYS:
            k += 1
        lines[k:k] = new


def pick_made(items, res, lang):
    """The voice that was just made becomes the chosen one of its line (the user can switch back on the page)."""
    picks = {f"{it['id']}.{lang}": variant_tag(it["model"]) for it in items if res.get(it["id"]) == "ok"}
    by_scene = {}
    for it in items:
        k = f"{it['id']}.{lang}"
        if k in picks:
            by_scene.setdefault(it["scene"], {})[k] = picks[k]
    if by_scene:
        with LOCK:
            lines = read_lines(STORY)
            for sid, pk in by_scene.items():
                set_voice_picks(lines, sid, pk)
            write_lines(STORY, lines)


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
    used = [int(m.group(1)) for l in lines for m in [MARKER.match(l.strip())] if m for m in [re.match(r"IMG(\d{3})", m.group(1))] if m]
    used += [int(k[3:]) for k in scan_images() if k.startswith("IMG")] + [int(k[3:]) for k in parse_prompts() if re.fullmatch(r"IMG\d{3}", k)]
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
    if first + images - 1 > 999:
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
    if n > 999:
        raise ValueError("too many pictures")
    while e > s_ + 1 and not lines[e - 1].strip():
        e -= 1
    lines[e:e] = [f"[IMG{n:03d}]"]
    return f"IMG{n:03d}"


def mark_stale(lines, scene_ids):
    for sid in scene_ids:
        for lg in LANGS:
            set_flag(lines, sid, lg, True)


def speech_scenes(lines, speaker=None, own_model=None):
    """Scene ids that have dialogue (of this speaker; only scenes with / without their own model when own_model is given)."""
    out = []
    for sc in story_scenes(lines):
        if own_model is not None and bool(sc["model"]) != own_model:
            continue
        if any(it["k"] == "say" and (speaker is None or it["sp"] == speaker) for b in sc["blocks"] for it in b["items"]):
            out.append(sc["id"])
    return out


def edit_line(lines, scene_id, index, old, new, op="edit"):
    """Change only the text of one line (or the speaker of a say line, or add an en: line). The key never changes."""
    s, e = scene_span(lines, scene_id)
    a = s + int(index)
    if not (s < a < e):
        raise ValueError("bad line index")
    kv = KEYLINE.match(lines[a].strip())
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
        if nn != name or nt != tone:  # another speaker or tone means another delivery
            for lg in LANGS:
                set_flag(lines, scene_id, lg, True)
        else:
            set_flag(lines, scene_id, "fa", True)
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
        if a + 1 < e and lines[a + 1].strip().startswith("en:"):
            raise Conflict("برای این خط ترجمه از قبل هست؛ صفحه را دوباره بارگذاری کن.")
        lines[a + 1:a + 1] = [f"en: {ENC(text)}"]
        set_flag(lines, scene_id, "en", True)
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
            for lg in LANGS:  # another speaker means another voice
                set_flag(lines, scene_id, lg, True)
            return
        if op == "tone":
            if tone != str(old).strip():
                raise Conflict("لحن این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
            if text != tone:
                lines[a] = fmt_say(name, text, body)
                for lg in LANGS:  # another tone means another delivery
                    set_flag(lines, scene_id, lg, True)
            return
        if DEC(body) != str(old).strip():
            raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
        if text != DEC(body):
            lines[a] = fmt_say(name, tone, ENC(text))
            set_flag(lines, scene_id, "fa", True)
        return
    if op == "speaker" or DEC(val) != str(old).strip():
        raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
    if text == DEC(val):
        return
    lines[a] = f"{key}: {ENC(text)}"
    if key == "en":
        set_flag(lines, scene_id, "en", True)


def add_line(lines, scene_id, after, kind, speaker, text, label="", tone=""):
    """Insert a new dialogue (say) or scene description (act) right after the given part (its en:/notes stay attached to it)."""
    s, e = scene_span(lines, scene_id)
    a = s + int(after)
    if not (s < a < e):
        raise ValueError("bad line index")
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
        skip = ("status", "note", "image-stale", "fx", "format-issue")
    elif kv and kv.group(1) in SPEECH:
        skip = ("en", "format-issue")
    else:
        skip = ("format-issue",)
    pos = a + 1
    while pos < e:
        k2 = KEYLINE.match(lines[pos].strip())
        if not k2 or k2.group(1) not in skip:
            break
        pos += 1
    lines[pos:pos] = [new]
    if name:
        ensure_speaker(lines, name)
        set_flag(lines, scene_id, "fa", True)


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
    skip = ("en", "format-issue") if key == "say" else ("format-issue",) if key == "act" else ()
    end, had_en = a + 1, False
    while end < e:
        k2 = KEYLINE.match(lines[end].strip())
        if not k2 or k2.group(1) not in skip:
            break
        had_en = had_en or k2.group(1) == "en"
        end += 1
    del lines[a:end]
    if key == "say":
        set_flag(lines, scene_id, "fa", True)
    if key == "en" or had_en:
        set_flag(lines, scene_id, "en", True)


def add_issue(lines, scene_id, index, message):
    """Put 'format-issue: ...' right after the given part so the AI finds it (grep format-issue)."""
    s, e = scene_span(lines, scene_id)
    a = s + int(index)
    if not (s <= a < e):
        raise ValueError("bad line index")
    kv = KEYLINE.match(lines[a].strip())
    pos = a + 1
    if MARKER.match(lines[a].strip()):
        skip = ("status", "note", "image-stale", "fx", "format-issue")
    elif kv and kv.group(1) in SPEECH:
        skip = ("en", "format-issue")
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


def upsert_prompt(lines, id_, old, new):
    """Like replace_prompt, but a picture that has no block yet gets a new one at the end (old must then be empty)."""
    if id_ in prompt_ranges(lines):
        return replace_prompt(lines, id_, old, new)
    if old.strip():
        raise Conflict("این پرامپت بیرون از مرورگر پاک شده؛ صفحه را دوباره بارگذاری کن.")
    body = new.replace("\r\n", "\n").strip()
    if not body:
        return False
    while lines and not lines[-1].strip():
        lines.pop()
    lines += ["", f"=== {id_} ===", *body.split("\n"), ""]
    return True


def replace_prompt(lines, id_, old, new):
    r = prompt_ranges(lines)
    if id_ not in r:
        raise ValueError("prompt not found")
    s, e = r[id_]
    if "\n".join(lines[s + 1:e]).strip() != old.replace("\r\n", "\n").strip():
        raise Conflict("این پرامپت بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
    body = new.replace("\r\n", "\n").strip().split("\n")
    lines[s + 1:e] = body + [""]
    return "\n".join(body).strip() != old.replace("\r\n", "\n").strip()


REFS_LINE = re.compile(r"\[REFS TO ATTACH:[^\]]*\]")


def set_prompt_refs(lines, id_, names):
    """Rewrite only the «[REFS TO ATTACH: A| B]» line at the top of one prompt (added when missing, removed when empty).
    A prompt that does not exist yet is created. Returns True when something changed."""
    line = "[REFS TO ATTACH: " + "| ".join(names) + "]" if names else ""
    r = prompt_ranges(lines)
    if id_ not in r:
        if line:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ([""] if lines else []) + [f"=== {id_} ===", line, ""]
        return bool(line)
    s, e = r[id_]
    i = next((k for k in range(s + 1, e) if lines[k].strip()), None)
    if i is not None and REFS_LINE.fullmatch(lines[i].strip()):
        if lines[i].strip() == line:
            return False
        lines[i:i + 1] = [line] if line else []
    elif line:
        lines[s + 1:s + 1] = [line]
    else:
        return False
    return True
