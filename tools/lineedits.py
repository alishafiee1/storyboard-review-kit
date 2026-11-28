# -*- coding: utf-8 -*-
"""Edits of single lines in story.txt: change, add, delete a dialogue / action / translation line, and format-issue notes."""
import glob, os, re
import kitcore
from kitcore import BOOK_RULES, Conflict, KEYLINE, LANGS, MARKER, ROOT, SAY_KEYS, SPEECH, STORY, read_lines, write_lines
from story import DEC, ENC, clean_label, clean_line, clean_name, clean_tone, ensure_speaker, fmt_say, parse_scene, scene_ranges, scene_span, split_act, split_say_head
from edits import IMG_KEYS, find_say, image_range, stale_lines


def locate(lines, d, key="index", book="story"):
    """(scene id, index counted from the scene header) of the line a request means. New form: {"image": "IMG001", key: n}, n counted from the
    image's own [IMG001] line (so the address survives moving the image to another scene). Old form: {"scene": "scene-01", key: n}."""
    rules = BOOK_RULES.get(book, BOOK_RULES["story"])
    if d.get("image"):
        img = str(d["image"])
        if not rules["item_re"].fullmatch(img):
            raise ValueError("bad image")
        sid, s, m, end = image_range(lines, img, book=book)
        a = m + int(d[key])
        if not m <= a < end:
            raise ValueError("bad line index")
        return sid, a - s
    sid = str(d.get("scene", ""))
    if not rules["section_re"].fullmatch(sid):
        raise ValueError("bad scene")
    return sid, int(d[key])


def owner_say(lines, scene_id, a, book="story"):
    """The id of the dialogue line that owns line `a` (the say line itself, or its en: line); None when it is not part of a dialogue line."""
    s, e = scene_span(lines, scene_id, book=book)
    for b in parse_scene(lines[s:e], book=book)["blocks"]:
        for it in b["items"]:
            if it["k"] == "say" and a - s in (it["ln"], it["en_ln"]):
                return it["id"]
    return None


def flag_line(lines, scene_id, line_id, langs, book="story"):
    """Its voice is out of date (only this line, in the languages given)."""
    if line_id:
        stale_lines(lines, scene_id, lambda it: it["id"] == line_id, langs, True, book=book)


def materialize_ids(lines, scene_id, book="story"):
    """Give every dialogue line of the scene that has no «id:» yet an explicit one: exactly the id it has now (IMG001_2), so no voice file
    changes name. Done before a line is added or deleted, because those shift the old position-based ids. Returns the new line positions
    (relative to the scene header), so callers can move the index they were given."""
    s, e = scene_span(lines, scene_id, book=book)
    sc = parse_scene(lines[s:e], book=book)
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


def owner_image(lines, a, s, book="story"):
    """The [IMG] a line at index `a` belongs to (the nearest marker above it inside the scene that starts at `s`), or None above the first picture."""
    mr = BOOK_RULES.get(book, BOOK_RULES["story"])["marker_re"]
    for i in range(a, s, -1):
        m = mr.match(lines[i].strip())
        if m:
            return m.group(1)
    return None


def next_say_id(lines, image):
    """IMG045-1, IMG045-2 ...: the next k of this picture that is not used by an id: line or by a voice file of any language (archived ones too),
    so a deleted line's number is never given to a new line (its voices could still be around)."""
    pat = re.escape(image) + r"-(\d+)"
    used = [int(m.group(1)) for l in lines for m in [re.match(r"\s*id:\s*" + pat + r"\s*$", l)] if m]
    used += [int(m.group(1)) for f in glob.glob(os.path.join(glob.escape(ROOT), "audio", "**", image + "-*"), recursive=True)
             for m in [re.match(pat + r"(?!\d)", os.path.basename(f))] if m]
    return "%s-%d" % (image, max(used or [0]) + 1)


def after_say(lines, a, e):
    """Index just after a say line and its id: line (where an en: line goes)."""
    return a + 2 if a + 1 < e and lines[a + 1].strip().startswith("id:") else a + 1


def edit_line(lines, scene_id, index, old, new, op="edit", book="story"):
    """Change only the text of one line (or the speaker of a say line, or add an en: line). The key never changes."""
    s, e = scene_span(lines, scene_id, book=book)
    a = s + int(index)
    if not (s < a < e):
        raise ValueError("bad line index")
    kv = KEYLINE.match(lines[a].strip())
    lid = owner_say(lines, scene_id, a, book=book)  # the line's id is read first: later steps may move line numbers (a new speaker line goes to the top)
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
            if book == "refs":
                story_file = getattr(kitcore, "STORY", kitcore.book_path("story"))
                sl = read_lines(story_file); ensure_speaker(sl, nn); write_lines(story_file, sl)
            else:
                ensure_speaker(lines, nn)
        flag_line(lines, scene_id, lid, LANGS if nn != name or nt != tone else ["fa"], book=book)  # another speaker or tone means another delivery
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
        flag_line(lines, scene_id, lid, ["en"], book=book)
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
            if book == "refs":
                story_file = getattr(kitcore, "STORY", kitcore.book_path("story"))
                sl = read_lines(story_file); ensure_speaker(sl, text); write_lines(story_file, sl)
            else:
                ensure_speaker(lines, text)
            flag_line(lines, scene_id, lid, LANGS, book=book)  # another speaker means another voice
            return
        if op == "tone":
            if tone != str(old).strip():
                raise Conflict("لحن این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
            if text != tone:
                lines[a] = fmt_say(name, text, body)
                flag_line(lines, scene_id, lid, LANGS, book=book)  # another tone means another delivery
            return
        if DEC(body) != str(old).strip():
            raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
        if text != DEC(body):
            lines[a] = fmt_say(name, tone, ENC(text))
            flag_line(lines, scene_id, lid, ["fa"], book=book)
        return
    if op == "speaker" or DEC(val) != str(old).strip():
        raise Conflict("این خط بیرون از مرورگر عوض شده؛ صفحه را دوباره بارگذاری کن.")
    if text == DEC(val):
        return
    lines[a] = f"{key}: {ENC(text)}"
    if key == "en":
        flag_line(lines, scene_id, lid, ["en"], book=book)


def add_line(lines, scene_id, after, kind, speaker, text, label="", tone="", book="story"):
    """Insert a new dialogue (say) or scene description (act) right after the given part (its en:/notes stay attached to it)."""
    s, e = scene_span(lines, scene_id, book=book)
    a = s + int(after)
    if not (s < a < e):
        raise ValueError("bad line index")
    if kind == "say":  # a new dialogue shifts the old position-based ids of the lines after it: pin them first
        a = s + shift(after, materialize_ids(lines, scene_id, book=book))
        s, e = scene_span(lines, scene_id, book=book)
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
    mr = BOOK_RULES.get(book, BOOK_RULES["story"])["marker_re"]
    l0 = lines[a].strip()
    kv = KEYLINE.match(l0)
    if mr.match(l0):
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
    new_id = None
    if kind == "say":  # a new line is named after the picture it belongs to; above the first picture the old L001 form is all there is
        img = owner_image(lines, a, s, book=book)
        new_id = next_say_id(lines, img) if img else next_line_id(lines)
    lines[pos:pos] = [new] + (["id: " + new_id, "voice-stale: fa"] if kind == "say" else [])  # a new line has no voice yet
    if name:
        if book == "refs":
            story_file = getattr(kitcore, "STORY", kitcore.book_path("story"))
            sl = read_lines(story_file); ensure_speaker(sl, name); write_lines(story_file, sl)
        else:
            ensure_speaker(lines, name)


def delete_line(lines, scene_id, index, old, book="story"):
    """Remove one act / say / en line. A say line takes its en: and format-issue lines with it; env cannot be deleted."""
    sa, e = scene_span(lines, scene_id, book=book)
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
        ins = materialize_ids(lines, scene_id, book=book)
        a = sa + shift(index, ins)
        sa, e = scene_span(lines, scene_id, book=book)
    skip = SAY_KEYS if key == "say" else ("format-issue",) if key == "act" else ()
    lid = owner_say(lines, scene_id, a, book=book) if key == "en" else None
    end, had_en = a + 1, False
    while end < e:
        k2 = KEYLINE.match(lines[end].strip())
        if not k2 or k2.group(1) not in skip:
            break
        had_en = had_en or k2.group(1) == "en"
        end += 1
    del lines[a:end]
    if key == "en":  # the line stays; its English voice no longer matches (a deleted dialogue line takes its voice keys with it)
        flag_line(lines, scene_id, lid, ["en"], book=book)


def add_issue(lines, scene_id, index, message, book="story"):
    """Put 'format-issue: ...' right after the given part so the AI finds it (grep format-issue)."""
    s, e = scene_span(lines, scene_id, book=book)
    a = s + int(index)
    if not (s <= a < e):
        raise ValueError("bad line index")
    mr = BOOK_RULES.get(book, BOOK_RULES["story"])["marker_re"]
    kv = KEYLINE.match(lines[a].strip())
    pos = a + 1
    if mr.match(lines[a].strip()):
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


def clear_issue(lines, scene_id, index, book="story"):
    s, e = scene_span(lines, scene_id, book=book)
    a = s + int(index)
    if not (s < a < e) or not lines[a].strip().startswith("format-issue:"):
        raise Conflict("این یادداشت دیگر نیست؛ صفحه را دوباره بارگذاری کن.")
    del lines[a]


def _resolve_line_index(lines, ref, book="story"):
    rules = BOOK_RULES.get(book, BOOK_RULES["story"])
    if isinstance(ref, dict):
        if ref.get("id"):
            _, a = find_say(lines, str(ref["id"]), book=book)
            return a
        if ref.get("image"):
            img = str(ref["image"])
            if not rules["item_re"].fullmatch(img):
                raise ValueError("bad image")
            _, _, m, end = image_range(lines, img, book=book)
            k = int(ref.get("index", ref.get("line", 0)))
            a = m + k
            if not (m <= a < end):
                raise ValueError("bad line index")
            return a
        if ref.get("scene"):
            sid = str(ref["scene"])
            if not rules["section_re"].fullmatch(sid):
                raise ValueError("bad scene")
            s, e = scene_span(lines, sid, book=book)
            k = int(ref.get("index", ref.get("line", 0)))
            a = s + k
            if not (s < a < e):
                raise ValueError("bad line index")
            return a
    if isinstance(ref, str):
        if rules["item_re"].fullmatch(ref):
            return ref
        _, a = find_say(lines, ref, book=book)
        return a
    if isinstance(ref, (int, float)):
        a = int(ref)
        if 0 <= a < len(lines):
            return a
    raise ValueError("bad line reference")


def move_line(lines, source=None, before=None, after=None, to_image=None, scene=None, index=None, line=None, image=None, book="story"):
    """Move an entire dialogue or action line chunk (say/act + id: + en: + voice: + voice-stale: + format-issue:)
    strictly preserving its id:, within the picture or to a neighboring picture (before/after target line, or onto another image)."""
    if source is None:
        if image and (index is not None or line is not None):
            source = {"image": image, "index": index if index is not None else line}
        elif scene and (index is not None or line is not None):
            source = {"scene": scene, "index": index if index is not None else line}
        elif line is not None:
            source = line
        else:
            raise ValueError("missing source")
    a = _resolve_line_index(lines, source, book=book)
    if not isinstance(a, int) or not (0 <= a < len(lines)):
        raise ValueError("bad source line")
    kv = KEYLINE.match(lines[a].strip())
    if not kv or kv.group(1) not in ("say", "act"):
        raise ValueError("source line must be say or act")

    src_sc = next(((sid, s, e) for sid, s, e in scene_ranges(lines, book=book) if s <= a < e), None)
    if not src_sc or (book == "story" and src_sc[0] == "scene-00"):
        raise ValueError("bad source scene")
    src_sid, src_s, src_e = src_sc
    src_img = owner_image(lines, a, src_s, book=book)
    if not src_img:
        raise ValueError("source line has no owner picture")

    mr = BOOK_RULES.get(book, BOOK_RULES["story"])["marker_re"]
    all_imgs = [m.group(1) for sid, s, e in scene_ranges(lines, book=book) if (book != "story" or sid != "scene-00")
                for l in lines[s + 1:e] for m in [mr.match(l.strip())] if m]
    if src_img not in all_imgs:
        raise ValueError("source picture not found")
    src_idx = all_imgs.index(src_img)
    allowed_imgs = {src_img}
    if src_idx > 0:
        allowed_imgs.add(all_imgs[src_idx - 1])
    if src_idx < len(all_imgs) - 1:
        allowed_imgs.add(all_imgs[src_idx + 1])

    targets = [x for x in (before, after, to_image) if x is not None]
    if len(targets) != 1:
        raise ValueError("exactly one target (before, after, or to_image) must be specified")

    rules = BOOK_RULES.get(book, BOOK_RULES["story"])
    if to_image is not None or (isinstance(before, str) and rules["item_re"].fullmatch(before)) or (isinstance(after, str) and rules["item_re"].fullmatch(after)):
        dst_img = str(to_image or before or after)
        if dst_img not in allowed_imgs:
            raise ValueError("target image not in picture or neighbor")
        dst_sid, dst_s, _, _ = image_range(lines, dst_img, book=book)

        ins_src = materialize_ids(lines, src_sid, book=book)
        s_src, _ = scene_span(lines, src_sid, book=book)
        a = a + sum(1 for p in ins_src if s_src + p <= a)
        if dst_sid != src_sid:
            ins_dst = materialize_ids(lines, dst_sid, book=book)
            s_dst, _ = scene_span(lines, dst_sid, book=book)
            if s_dst < s_src:
                a += len(ins_dst)

        _, _, m, img_end = image_range(lines, dst_img, book=book)

        chunk_end = a + 1
        while chunk_end < len(lines):
            k2 = KEYLINE.match(lines[chunk_end].strip())
            if not k2 or k2.group(1) not in SAY_KEYS:
                break
            chunk_end += 1
        chunk = lines[a:chunk_end]
        chunk_len = len(chunk)

        if before is not None and isinstance(before, str):
            pos = m + 1
            while pos < img_end:
                k2 = KEYLINE.match(lines[pos].strip())
                if not k2 or k2.group(1) not in IMG_KEYS:
                    break
                pos += 1
            target_pos = pos
        else:
            pos = img_end
            while pos > m + 1 and not lines[pos - 1].strip():
                pos -= 1
            target_pos = pos

        if target_pos > a:
            del lines[a:chunk_end]
            lines[target_pos - chunk_len:target_pos - chunk_len] = chunk
        elif target_pos < a:
            del lines[a:chunk_end]
            lines[target_pos:target_pos] = chunk
        return

    is_before = before is not None
    target_ref = before if is_before else after
    tgt_a = _resolve_line_index(lines, target_ref, book=book)
    if not isinstance(tgt_a, int) or not (0 <= tgt_a < len(lines)):
        raise ValueError("bad target line")
    if tgt_a == a:
        raise ValueError("cannot move line relative to itself")
    tgt_kv = KEYLINE.match(lines[tgt_a].strip())
    if not tgt_kv or tgt_kv.group(1) not in ("say", "act"):
        raise ValueError("target line must be say or act")

    tgt_sc = next(((sid, s, e) for sid, s, e in scene_ranges(lines, book=book) if s <= tgt_a < e), None)
    if not tgt_sc or (book == "story" and tgt_sc[0] == "scene-00"):
        raise ValueError("bad target scene")
    tgt_sid, tgt_s, tgt_e = tgt_sc
    tgt_img = owner_image(lines, tgt_a, tgt_s, book=book)
    if not tgt_img or tgt_img not in allowed_imgs:
        raise ValueError("target line not in picture or neighbor")

    ins_src = materialize_ids(lines, src_sid, book=book)
    s_src, _ = scene_span(lines, src_sid, book=book)
    a = a + sum(1 for p in ins_src if s_src + p <= a)
    if tgt_sid == src_sid:
        tgt_a = tgt_a + sum(1 for p in ins_src if s_src + p <= tgt_a)
    else:
        ins_tgt = materialize_ids(lines, tgt_sid, book=book)
        s_tgt, _ = scene_span(lines, tgt_sid, book=book)
        if s_tgt < s_src:
            a += len(ins_tgt)
            tgt_a = tgt_a + sum(1 for p in ins_tgt if s_tgt + p <= tgt_a)
        else:
            tgt_a = tgt_a + len(ins_src) + sum(1 for p in ins_tgt if s_tgt + p <= tgt_a)

    chunk_end = a + 1
    while chunk_end < len(lines):
        k2 = KEYLINE.match(lines[chunk_end].strip())
        if not k2 or k2.group(1) not in SAY_KEYS:
            break
        chunk_end += 1
    chunk = lines[a:chunk_end]
    chunk_len = len(chunk)

    if is_before:
        target_pos = tgt_a
    else:
        tgt_chunk_end = tgt_a + 1
        while tgt_chunk_end < len(lines):
            k2 = KEYLINE.match(lines[tgt_chunk_end].strip())
            if not k2 or k2.group(1) not in SAY_KEYS:
                break
            tgt_chunk_end += 1
        target_pos = tgt_chunk_end

    if target_pos > a:
        del lines[a:chunk_end]
        lines[target_pos - chunk_len:target_pos - chunk_len] = chunk
    elif target_pos < a:
        del lines[a:chunk_end]
        lines[target_pos:target_pos] = chunk
