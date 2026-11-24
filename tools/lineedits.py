# -*- coding: utf-8 -*-
"""Edits of single lines in story.txt: change, add, delete a dialogue / action / translation line, and format-issue notes."""
from kitcore import Conflict, KEYLINE, LANGS, MARKER, SPEECH
from story import DEC, ENC, clean_label, clean_line, clean_name, clean_tone, ensure_speaker, fmt_say, scene_span, split_act, split_say_head
from edits import set_flag


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
