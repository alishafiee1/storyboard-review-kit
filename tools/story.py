# -*- coding: utf-8 -*-
"""Reading story.txt and prompts.txt: scenes, dialogue lines, speakers, prompts. Pure text in, plain dicts out (no network, no file writes except through kitcore)."""
import colorsys, random, re
from kitcore import VARIANT, LINE_ID, CONTENT, DEFAULT_MODEL, HEADER, KEYLINE, LANGS, MARKER, MARKS, PALETTE, PHEADER, PROMPTS, SPEECH, SPK, STORY, VOICE_LIST, read_lines


def clean_spoken(t):
    """Text to be read aloud: no fact/hypothesis tags, markdown or stage directions."""
    t = re.sub(r"〔[^〕]*〕", " ", t or "")
    t = re.sub(r"\*\([^)]*\)\*", " ", t)
    t = t.replace("`", "").replace("*", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t if re.search(r"[؀-ۿA-Za-z0-9]", t) else ""


def scene_ranges(lines):
    """[(id, start, end)] with end exclusive (next header or end of file)."""
    hs = [(i, HEADER.match(l.strip())) for i, l in enumerate(lines)]
    hs = [(i, m) for i, m in hs if m]
    return [(m.group(1), i, hs[k + 1][0] if k + 1 < len(hs) else len(lines)) for k, (i, m) in enumerate(hs)]


ENC = lambda t: t.replace("\n", "\\n")  # a real line break is stored as \n inside the one-line entry


DEC = lambda t: t.replace("\\n", "\n")


def split_say_head(head):
    """'علی (با تعجب)' -> ('علی', 'با تعجب'); a name without parentheses has no tone."""
    head = head.strip()
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", head)
    return (m.group(1).strip(), m.group(2).strip()) if m and m.group(1).strip() else (head, "")


def fmt_say(name, tone, text):
    return f"say: {name} ({tone}) | {text}" if tone else f"say: {name} | {text}"


def clean_tone(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(s) > 40 or any(c in s for c in "|()"):
        raise ValueError("لحن باید تا ۴۰ حرف باشد و | یا پرانتز نداشته باشد")
    return s


def split_act(val):
    """'گگ | text' -> ('گگ', 'text'); an act without a short label before | is ('None', whole text)."""
    lab, bar, text = val.partition("|")
    lab = lab.strip()
    if bar and lab and len(lab) <= 15 and text.strip():
        return lab, text.strip()
    return None, val.strip()


def clean_label(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if "|" in s or len(s) > 15:
        raise ValueError("برچسب باید تا ۱۵ حرف باشد و | نداشته باشد")
    return s


def parse_voice_map(val):
    """'fa=3a9c01de, en=default' -> {'fa': '3a9c01de', 'en': 'default'} (only known languages, only valid variant names)."""
    out = {}
    for part in val.split(","):
        k, _, v = part.partition("=")
        if k.strip() in LANGS and VARIANT.fullmatch(v.strip()):
            out[k.strip()] = v.strip()
    return out


def parse_langs(val):
    return {x.strip() for x in val.split(",") if x.strip() in LANGS}


def parse_scene(raw_lines):
    """raw_lines = the scene block (header first). ln = line index inside the block. Every part can carry format-issue notes.
    Ownership: every act / say line belongs to the nearest [IMG] marker above it (one block per picture: blocks[i]["images"] has exactly that
    picture). Lines before the first marker are scene-level (a block without a picture; they are reported in warnings). Voice choices and
    out-of-date flags belong to the dialogue line («voice:» / «voice-stale:» under it); the old scene-level «voice-pick:» / «voice-stale:»
    lines are still read and mapped onto the lines (sc["legacy_pick"], sc["legacy_stale"])."""
    m = HEADER.match(raw_lines[0].strip())
    sc = dict(id=m.group(1), title=m.group(2), time=m.group(3), env=[], model="", fx="", voice_stale=set(), blocks=[], warnings=[], issues=[],
              off=False, voice_pick={}, legacy_pick={}, legacy_stale=set(), legacy_ln={"voice-pick": [], "voice-stale": []})
    last_img = last_speech = last_obj = cur = grp = None
    # the old "block" (consecutive markers share the lines after them) is only kept to name lines that have no id: line, exactly as before
    grp_base, grp_n, grp_open = sc["id"], 0, False

    def warn(text, i):
        nonlocal last_obj
        last_obj = dict(text=text[:80], ln=i, issues=[])
        sc["warnings"].append(last_obj)

    for i in range(1, len(raw_lines)):
        s = raw_lines[i].strip()
        if not s or s.startswith("#"):
            continue
        mk = MARKER.match(s)
        if mk:
            last_img = last_obj = dict(id=mk.group(1), status="", note="", fx="", stale=False, pick="", off=False, ln=i, end=len(raw_lines), issues=[])
            if sc["blocks"] and sc["blocks"][-1]["images"]:
                sc["blocks"][-1]["images"][0]["end"] = i
            cur = dict(images=[last_img], items=[])
            sc["blocks"].append(cur)
            if grp is None or grp["items"]:  # a marker right after a marker keeps the old shared name base
                grp = dict(base=mk.group(1), n=0, items=0)
            last_speech = None
            continue
        kv = KEYLINE.match(s)
        if not kv:
            warn(s, i)
            continue
        key, val = kv.group(1), kv.group(2).strip()
        if key == "format-issue":
            (last_obj["issues"] if last_obj is not None else sc["issues"]).append(dict(ln=i, msg=val))
        elif key == "env":
            last_obj = dict(text=DEC(val), ln=i, issues=[])
            sc["env"].append(last_obj)
        elif key == "model":
            sc["model"] = val.strip()
        elif key == "fx" and last_img is None:  # before the first picture: edit suggestion for the whole scene
            sc["fx"] = val.replace("\\n", "\n")
        elif key == "off" and last_img is None:  # before the first picture: the whole scene is set aside (nothing is deleted)
            sc["off"] = val.lower() in ("yes", "true", "1")
        elif key == "voice-pick":  # old scene-level form «IMG001_1.fa=eleven-v3, IMG001_2.en=default»: still read, mapped onto the lines
            sc["legacy_pick"] = {k.strip(): v.strip() for k, _, v in (x.partition("=") for x in val.split(",")) if k.strip() and v.strip()}
            sc["legacy_ln"]["voice-pick"].append(i)
        elif key == "voice-stale" and last_speech is None:  # old scene-level flag (under the scene header); under a dialogue line it is that line's own
            sc["legacy_stale"] = parse_langs(val)
            sc["legacy_ln"]["voice-stale"].append(i)
        elif key in ("voice", "voice-stale"):  # per-line keys, right under the dialogue line they belong to
            if last_speech is None or last_speech.get(key):
                warn(s, i)
            else:
                last_speech[key], last_obj = (parse_voice_map(val) if key == "voice" else sorted(parse_langs(val))), last_speech
        elif key in ("status", "note", "image-stale", "fx", "pick", "off"):
            if last_img is None:
                warn(s, i)
            else:
                last_obj = last_img
                if key == "status":
                    last_img["status"] = val if val in MARKS else ""
                elif key == "note":
                    last_img["note"] = val.replace("\\n", "\n")
                elif key == "fx":
                    last_img["fx"] = val.replace("\\n", "\n")
                elif key == "pick":
                    last_img["pick"] = val
                elif key == "off":
                    last_img["off"] = val.lower() in ("yes", "true", "1")
                else:
                    last_img["stale"] = val.lower() in ("yes", "true", "1")
        elif key in CONTENT:
            if cur is None:  # lines above the first picture: scene-level items (kept so old files do not break; the page shows a warning)
                cur = dict(images=[], items=[])
                sc["blocks"].append(cur)
            if grp is None:
                grp = dict(base=sc["id"], n=0, items=0)
            sp, tone = None, ""
            if key == "say":
                head, bar, text = val.partition("|")
                name, tone = split_say_head(head)
                if not bar or not name or not text.strip():
                    warn(s, i)
                    continue
                sp, val = name, DEC(text.strip())
            label = None
            if key == "act":
                label, val = split_act(val)
                val = DEC(val)
            it = last_obj = dict(k=key, sp=sp, tone=tone if key == "say" else "", label=label, fa=val, en=None, ln=i, en_ln=None, issues=[],
                                 img=cur["images"][0]["id"] if cur["images"] else None)
            if last_img is None:
                sc["warnings"].append(dict(text=("%s before the first [IMG]: %s" % (key, s))[:80], ln=i, issues=[]))
            cur["items"].append(it)
            grp["items"] += 1
            if key == "say":
                grp["n"] += 1
                it["legacy_id"] = f"{grp['base']}_{grp['n']}"
            last_speech = it if key in SPEECH else None
        elif key == "en":
            if last_speech is None:
                warn(s, i)
            else:
                last_speech["en"], last_speech["en_ln"], last_obj = DEC(val), i, last_speech
        elif key == "id":  # the stable name of the dialogue line above (its voice files carry it); it stays with the line when the line moves
            if last_speech is None or not LINE_ID.fullmatch(val) or last_speech.get("eid"):
                warn(s, i)
            else:
                last_speech["eid"], last_speech["id_ln"], last_obj = val, i, last_speech
        else:
            warn(s, i)
    # speech ids: the line's own «id:», else the old position name {first picture of the old shared block or scene id}_{n}
    pick, stale = dict(sc["legacy_pick"]), set(sc["legacy_stale"])
    for b in sc["blocks"]:
        for it in b["items"]:
            if it["k"] in SPEECH:
                legacy = it.pop("legacy_id")
                it["id"] = it.get("eid") or legacy
                it["voice"] = it.get("voice") or {}
                it["stale_own"] = it.pop("voice-stale", None) or []
                it["vstale"] = sorted(set(it["stale_own"]) | sc["legacy_stale"])
                for lg, v in it["voice"].items():  # the line's own choice wins over an old scene-level one
                    pick[f"{it['id']}.{lg}"] = v
                stale |= set(it["vstale"])
    sc["voice_pick"], sc["voice_stale"] = pick, stale
    return sc


def story_scenes(lines=None):
    lines = read_lines(STORY) if lines is None else lines
    return [parse_scene(lines[s:e]) for _, s, e in scene_ranges(lines)]


def default_model(lines):
    """The «tts-model:» line at the top of story.txt (model used by scenes that have no «model:» line)."""
    for l in lines:
        if HEADER.match(l.strip()):
            break
        m = re.match(r"^tts-model:\s*(\S+)", l.strip())
        if m:
            return m.group(1)
    return DEFAULT_MODEL


def spoken_lines(lang="fa"):
    """[{id, scene, speaker, voice, model, spoken, tone}] for every dialogue line that has text in this language (used by tools/tts.py)."""
    lines = read_lines(STORY)
    spk = {s["name"]: s for s in parse_speakers(lines)}
    dm = default_model(lines)
    out = []
    for sc in story_scenes(lines):
        if sc["off"]:  # a scene that is set aside gets no new voice
            continue
        for b in sc["blocks"]:
            for it in b["items"]:
                if it["k"] in SPEECH:
                    sp = clean_spoken(it["fa"] if lang == "fa" else it["en"])
                    if sp:
                        out.append(dict(id=it["id"], scene=sc["id"], image=it["img"], stale=it["vstale"], speaker=it["sp"], voice=spk.get(it["sp"], {}).get("voice") or "george",
                                        model=sc["model"] or dm, spoken=sp, tone=it["tone"] or spk.get(it["sp"], {}).get("tone", "")))
    return out


def parse_speakers(lines):
    out = []
    for i, l in enumerate(lines):
        if HEADER.match(l.strip()):
            break
        m = SPK.match(l.strip())
        if m:
            out.append(dict(name=m.group(1), color=m.group(2), voice=m.group(3) or "", tone=m.group(4) or "", ln=i))
    return out


def clean_name(s):
    s = re.sub(r"\s+", " ", str(s)).strip()
    if not s or len(s) > 40 or any(c in s for c in "|()"):
        raise ValueError("نام گوینده خالی یا بیش از ۴۰ حرف است یا | یا پرانتز دارد")
    return s


def new_color(used):
    for c in PALETTE:
        if c.lower() not in used:
            return c
    best, gap = None, -1
    for _ in range(40):  # keep a hue far from the colours already in use
        h = random.random()
        g = min([min(abs(h - hh), 1 - abs(h - hh)) for hh in [colorsys.rgb_to_hls(*[int(c[k:k + 2], 16) / 255 for k in (1, 3, 5)])[0] for c in used]] or [1])
        if g > gap:
            best, gap = h, g
    r, g_, b = colorsys.hls_to_rgb(best, 0.4, 0.6)
    return "#%02x%02x%02x" % (int(r * 255), int(g_ * 255), int(b * 255))


def ensure_speaker(lines, name, color=None, voice=None, tone=None):
    """Make sure a 'speaker: name | #color | voice' line exists (new speakers get an unused colour and voice); optionally update it."""
    sp = parse_speakers(lines)
    cur = next((x for x in sp if x["name"] == name), None)
    if cur is None:
        used_c = [x["color"].lower() for x in sp]
        used_v = [x["voice"] for x in sp]
        c = color or new_color(used_c)
        v = voice or next((x for x in VOICE_LIST if x not in used_v), "george")
        new = f"speaker: {name} | {c} | {v}" + (f" | {tone}" if tone else "")
        if sp:
            lines.insert(sp[-1]["ln"] + 1, new)
        else:
            h = next((i for i, l in enumerate(lines) if HEADER.match(l.strip())), len(lines))
            lines[h:h] = ["# گوینده‌ها: «speaker: نام | رنگ | صدا»؛ رنگ و صدای هر گوینده همین‌جاست", new, ""]
    elif color or voice is not None or tone is not None:
        tn = cur["tone"] if tone is None else tone
        lines[cur["ln"]] = f"speaker: {name} | {color or cur['color']} | {voice if voice is not None else cur['voice']}" + (f" | {tn}" if tn else "")


def prompt_ranges(lines):
    hs = [(i, PHEADER.match(l.strip())) for i, l in enumerate(lines)]
    hs = [(i, m) for i, m in hs if m]
    return {m.group(1): (i, hs[k + 1][0] if k + 1 < len(hs) else len(lines)) for k, (i, m) in enumerate(hs)}


def parse_prompts(lines=None):
    lines = read_lines(PROMPTS) if lines is None else lines
    out = {}
    for id_, (s, e) in prompt_ranges(lines).items():
        body = "\n".join(lines[s + 1:e]).strip()
        r = re.match(r"\[REFS TO ATTACH:([^\]]*)\]", body)
        out[id_] = dict(prompt=body, refs=[x.strip() for x in r.group(1).split("|")] if r else [])
    return out


def clean_line(s):
    s = str(s).replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n")).strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    if len(s) > 4000:
        raise ValueError("متن خیلی بلند است")
    return s


def scene_span(lines, scene_id):
    s, e = next(((s, e) for i, s, e in scene_ranges(lines) if i == scene_id), (None, None))
    if s is None:
        raise ValueError("scene not found")
    return s, e
