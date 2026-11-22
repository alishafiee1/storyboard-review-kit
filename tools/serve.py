# -*- coding: utf-8 -*-
"""Review server for review.html. Reads and edits two plain-text files:
  scenario/story.txt     (scenes, dialogue FA + optional en: lines, notes, flags, format-issue notes)
  prompts/prompts.txt    (one complete Flow prompt per image / reference)
Run:  python tools/serve.py   (or double-click click-for-review.bat)  ->  http://127.0.0.1:8765/review.html
Listens on 127.0.0.1 only and stops by itself ~90 s after the page is closed. tools/tts.py imports spoken_lines()."""
import colorsys, datetime, functools, glob, http.server, json, os, random, re, sys, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORY = os.path.join(ROOT, "scenario", "story.txt")
PROMPTS = os.path.join(ROOT, "prompts", "prompts.txt")
VPROMPTS = os.path.join(ROOT, "prompts", "video-prompts.txt")  # one image-to-video prompt per picture (optional file)
PORT = int(os.environ.get("PORT", "8765"))
IDLE = float(os.environ.get("IDLE_SECONDS", "90"))
MARKS = {"", "ok", "redo", "anim"}
LANGS = ("fa", "en")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
VID_EXT = (".mp4", ".webm", ".mov", ".m4v")
last_ping, seen_ping = [time.time()], [False]
LOCK = threading.Lock()

HEADER = re.compile(r"^=== (scene-\d{2}) \| (.*?) \| (.*?) ===$")
MARKER = re.compile(r"^\[(IMG\d{3})\]$")
KEYLINE = re.compile(r"^([a-z][a-z-]*):\s?(.*)$")
PHEADER = re.compile(r"^=== ([A-Za-z0-9_]+) ===$")
SPEECH = ("say",)
SPK = re.compile(r"^speaker:\s*(.*?)\s*\|\s*(#[0-9a-fA-F]{6})\s*(?:\|\s*([A-Za-z0-9_]*)\s*)?(?:\|\s*(.*?)\s*)?$")
PALETTE = ["#1565c0", "#ef6c00", "#2e7d32", "#8e24aa", "#c62828", "#00838f", "#6d4c41", "#ad1457", "#558b2f", "#4527a0", "#f9a825", "#37474f"]
VOICE_LIST = ["george", "charlie", "sarah", "adam", "alice", "bella", "bill", "brian", "callum", "chris", "daniel", "eric", "harry", "jessica", "laura", "liam", "lily", "matilda", "river", "roger", "will"]
CONTENT = ("act",) + SPEECH
DEFAULT_MODEL = "elevenlabs/eleven-v4-turbo"
MODEL_RE = re.compile(r"[A-Za-z0-9_./:-]{1,80}")
VOICE_RE = re.compile(r"[A-Za-z0-9_.:-]{1,60}")


# ---------------------------------------------------------------- files
def read_lines(path):
    try:
        return open(path, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    except OSError:
        return []


def write_lines(path, lines):
    text = "\n".join(lines).rstrip("\n") + "\n"
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8", newline="\n").write(text)
    os.replace(tmp, path)


def clean_spoken(t):
    """Text to be read aloud: no fact/hypothesis tags, markdown or stage directions."""
    t = re.sub(r"〔[^〕]*〕", " ", t or "")
    t = re.sub(r"\*\([^)]*\)\*", " ", t)
    t = t.replace("`", "").replace("*", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t if re.search(r"[؀-ۿA-Za-z0-9]", t) else ""


# ---------------------------------------------------------------- story parsing
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


def parse_scene(raw_lines):
    """raw_lines = the scene block (header first). ln = line index inside the block. Every part can carry format-issue notes."""
    m = HEADER.match(raw_lines[0].strip())
    sc = dict(id=m.group(1), title=m.group(2), time=m.group(3), env=[], model="", fx="", voice_stale=set(), blocks=[], warnings=[], issues=[])
    cur = last_img = last_speech = last_obj = None

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
            if cur is None or cur["items"]:
                cur = dict(images=[], items=[])
                sc["blocks"].append(cur)
            last_img = last_obj = dict(id=mk.group(1), status="", note="", fx="", stale=False, ln=i, issues=[])
            cur["images"].append(last_img)
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
        elif key == "voice-stale":
            sc["voice_stale"] = {x.strip() for x in val.split(",") if x.strip() in LANGS}
        elif key in ("status", "note", "image-stale", "fx"):
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
                else:
                    last_img["stale"] = val.lower() in ("yes", "true", "1")
        elif key in CONTENT:
            if cur is None:
                cur = dict(images=[], items=[])
                sc["blocks"].append(cur)
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
            it = last_obj = dict(k=key, sp=sp, tone=tone if key == "say" else "", label=label, fa=val, en=None, ln=i, en_ln=None, issues=[])
            cur["items"].append(it)
            last_speech = it if key in SPEECH else None
        elif key == "en":
            if last_speech is None:
                warn(s, i)
            else:
                last_speech["en"], last_speech["en_ln"], last_obj = DEC(val), i, last_speech
        else:
            warn(s, i)
    # speech ids: {first image id or scene id}_{n}, n counted inside the block
    for b in sc["blocks"]:
        base, n = (b["images"][0]["id"] if b["images"] else sc["id"]), 0
        for it in b["items"]:
            if it["k"] in SPEECH:
                n += 1
                it["id"] = f"{base}_{n}"
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
        for b in sc["blocks"]:
            for it in b["items"]:
                if it["k"] in SPEECH:
                    sp = clean_spoken(it["fa"] if lang == "fa" else it["en"])
                    if sp:
                        out.append(dict(id=it["id"], scene=sc["id"], speaker=it["sp"], voice=spk.get(it["sp"], {}).get("voice") or "george",
                                        model=sc["model"] or dm, spoken=sp, tone=it["tone"] or spk.get(it["sp"], {}).get("tone", "")))
    return out


# ---------------------------------------------------------------- speakers (colour + voice live in the top of story.txt)
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


# ---------------------------------------------------------------- prompts
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


# ---------------------------------------------------------------- images / refs
def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def scan_images():
    cur, rej = {}, {}
    for f in glob.glob(os.path.join(ROOT, "images", "scenes", "**", "IMG*"), recursive=True):
        m = re.match(r"(IMG\d{3})", os.path.basename(f))
        if m and f.lower().endswith(IMG_EXT):
            (rej if "_rejected" in f.replace("\\", "/") else cur).setdefault(m.group(1), []).append(f)
    out = {}
    for id_ in set(cur) | set(rej):
        c = sorted(cur.get(id_, []), key=os.path.getmtime, reverse=True)
        out[id_] = dict(src=rel(c[0]) if c else None,
                        rejected=[rel(x) for x in sorted(rej.get(id_, []), key=os.path.getmtime, reverse=True)])
    return out


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


def audio_url(lang, id_):
    p = os.path.join(ROOT, "audio", lang, id_ + ".mp3")
    return f"audio/{lang}/{id_}.mp3?v={int(os.path.getmtime(p))}" if os.path.exists(p) else None


def project():
    import voices
    lines = read_lines(STORY)
    cat = voices.read_catalog()
    dm = default_model(lines)
    images, prompts = scan_images(), parse_prompts()
    vprompts = parse_prompts(read_lines(VPROMPTS)) if os.path.exists(VPROMPTS) else {}
    vids = scan_videos()
    refs = scan_refs(prompts)
    for r in refs:
        r["video"] = video_for(r["name"], vids)
    ref_src = {r["name"]: r["src"] for r in refs}
    ref_vid = {r["name"]: r["video"] for r in refs}
    scenes = []
    for sc in story_scenes(lines):
        for b in sc["blocks"]:
            b["images"] = [dict(im, **images.get(im["id"], dict(src=None, rejected=[])),
                                prompt=prompts.get(im["id"], {}).get("prompt", ""),
                                vprompt=vprompts.get(im["id"], {}).get("prompt", ""), video=video_for(im["id"], vids),
                                refs=[dict(name=n, src=ref_src.get(n), video=ref_vid.get(n)) for n in prompts.get(im["id"], {}).get("refs", [])])
                           for im in b["images"]]
            for it in b["items"]:
                if "id" in it:
                    it["audio"] = {lg: audio_url(lg, it["id"]) for lg in LANGS}
        scenes.append(dict(id=sc["id"], title=sc["title"], time=sc["time"], env=sc["env"], issues=sc["issues"],
                           warnings=sc["warnings"], model=sc["model"], fx=sc["fx"], voice_stale=sorted(sc["voice_stale"]), blocks=sc["blocks"]))
    return dict(name=os.path.basename(ROOT), scenes=scenes, refs=refs, speakers=parse_speakers(lines), voices=VOICE_LIST,
                tts=dict(default=dm, catalog=cat, job=JOB, **voices.status()), time=datetime.datetime.now().isoformat(timespec="seconds"))


# ---------------------------------------------------------------- edits (all raw-line based, nothing else in the file is touched)
class Conflict(Exception):
    pass


def patch_image(lines, img_id, status=None, note=None, stale=None, fx=None):
    idx = next((i for i, l in enumerate(lines) if l.strip() == f"[{img_id}]"), None)
    if idx is None:
        raise ValueError("image not in story")
    j, cur = idx + 1, dict(status="", note="", stale=False, fx="")
    while j < len(lines):
        kv = KEYLINE.match(lines[j].strip())
        if not kv or kv.group(1) not in ("status", "note", "image-stale", "fx"):
            break
        v = kv.group(2).strip()
        if kv.group(1) == "status":
            cur["status"] = v
        elif kv.group(1) == "note":
            cur["note"] = v
        elif kv.group(1) == "fx":
            cur["fx"] = v
        else:
            cur["stale"] = v.lower() in ("yes", "true", "1")
        j += 1
    if status is not None:
        cur["status"] = status
    if note is not None:
        cur["note"] = note.strip().replace("\r\n", "\n").replace("\n", "\\n")
    if stale is not None:
        cur["stale"] = bool(stale)
    if fx is not None:
        cur["fx"] = fx.strip().replace("\r\n", "\n").replace("\n", "\\n")
    new = ([f"status: {cur['status']}"] if cur["status"] else []) + (["image-stale: yes"] if cur["stale"] else []) \
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
        while k < e and lines[k].strip().split(":")[0] in ("env", "voice-stale", "model"):
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
        while k < e and lines[k].strip().split(":")[0] in ("env", "voice-stale"):
            k += 1
        lines[k:k] = new


def set_default_model(lines, model):
    pos = next((i for i, l in enumerate(lines) if l.startswith("tts-model:")), None)
    if pos is not None:
        lines[pos] = f"tts-model: {model}"
        return
    h = next((i for i, l in enumerate(lines) if HEADER.match(l.strip())), len(lines))
    lines[h:h] = ["# مدل پیش‌فرض تولید صدا؛ هر صحنه با یک خط «model:» می‌تواند مدل خودش را داشته باشد", f"tts-model: {model}", ""]


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


# ---------------------------------------------------------------- server
# ---------------------------------------------------------------- voice jobs (network; they do not hold the file lock while they wait)
JOB = dict(state="idle", scene="", done=0, total=0, errors=[])


def api_refresh(d):
    import voices
    return voices.refresh()


def api_sample(d):
    """One fixed Persian sentence in this model + voice (cached in audio/_samples) so a voice can be judged before it is chosen."""
    import tts, voices
    model, voice = str(d.get("model", "")), str(d.get("voice", ""))
    if not MODEL_RE.fullmatch(model) or not VOICE_RE.fullmatch(voice):
        raise ValueError("bad model or voice")
    bad = tts.voice_problem(model, voice)
    if bad:
        raise ValueError(bad)
    key = voices.load_key()
    if not key:
        raise ValueError("کلید API پیدا نشد")
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", model) + "__" + re.sub(r"[^A-Za-z0-9_.-]", "_", voice) + ".mp3"
    p = os.path.join(ROOT, "audio", "_samples", name)
    if not os.path.exists(p):
        try:
            data = tts.synth(model, voice, SAMPLE_TEXT, key)
        except RuntimeError as e:
            raise ValueError(str(e))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)
    return {"ok": True, "url": "audio/_samples/" + name}


def regen_job(scene):
    import tts
    try:
        with LOCK:
            sc = next(s for s in story_scenes() if s["id"] == scene)
        todo = [(lg, [i for i in spoken_lines(lg) if i["scene"] == scene]) for lg in sorted(sc["voice_stale"])]
        JOB["total"] = sum(len(x) for _, x in todo)

        def tick(id_, st):
            JOB["done"] += 1
            if st.startswith("FAILED"):
                JOB["errors"].append(f"{id_}: {st[7:]}")
        for lg, items in todo:
            before = len(JOB["errors"])
            tts.make(items, lg, force=True, on_done=tick)
            if len(JOB["errors"]) == before:
                with LOCK:
                    lines = read_lines(STORY)
                    set_flag(lines, scene, lg, False)
                    write_lines(STORY, lines)
        JOB["state"] = "failed" if JOB["errors"] else "done"
    except Exception as e:  # the page must always get an end state
        JOB["errors"].append(str(e)[:150])
        JOB["state"] = "failed"


def api_regen(d):
    scene = str(d.get("scene", ""))
    if not re.fullmatch(r"scene-\d{2}", scene):
        raise ValueError("bad scene")
    if JOB["state"] == "running":
        raise ValueError("یک بازسازی دیگر در حال انجام است")
    JOB.update(state="running", scene=scene, done=0, total=0, errors=[])
    threading.Thread(target=regen_job, args=(scene,), daemon=True).start()
    return {"ok": True}


def api_subtitles(d):
    import subtitles
    return subtitles.make_all()


SLOW = {"/api/subtitles": api_subtitles, "/api/voices/refresh": api_refresh, "/api/sample": api_sample, "/api/regen": api_regen}
SAMPLE_TEXT = "سلام، این یه نمونهٔ صداست. امروز می‌خوام یه چیز جالب بهت نشون بدم."


class H(http.server.SimpleHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/project":
            return self._json(200, project())
        if p == "/api/job":
            return self._json(200, JOB)
        if p == "/api/ping":
            last_ping[0], seen_ping[0] = time.time(), True
            return self._json(200, {"ok": True})
        if p == "/":
            self.send_response(302)
            self.send_header("Location", "/review.html")
            self.end_headers()
            return
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 200000:
            return self._json(400, {"error": "bad size"})
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            if self.path in SLOW:
                return self._json(200, SLOW[self.path](d))
            with LOCK:
                return self._json(200, self.edit(self.path, d))
        except Conflict as e:
            return self._json(409, {"error": str(e)})
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": str(e)})

    def edit(self, path, d):
        if path == "/api/image":
            id_ = str(d["id"])
            if not re.fullmatch(r"IMG\d{3}", id_) or str(d.get("status", "")) not in MARKS:
                raise ValueError("bad id or status")
            lines = read_lines(STORY)
            patch_image(lines, id_, d.get("status"), None if d.get("note") is None else str(d["note"])[:4000], d.get("stale"),
                        None if d.get("fx") is None else str(d["fx"])[:2000])
            write_lines(STORY, lines)
        elif path == "/api/flag":
            if d["lang"] not in LANGS or not re.fullmatch(r"scene-\d{2}", str(d["scene"])):
                raise ValueError("bad scene or lang")
            lines = read_lines(STORY)
            set_flag(lines, d["scene"], d["lang"], bool(d["value"]))
            write_lines(STORY, lines)
        elif path == "/api/line":
            if not re.fullmatch(r"scene-\d{2}", str(d["scene"])):
                raise ValueError("bad scene")
            lines = read_lines(STORY)
            edit_line(lines, d["scene"], d["index"], d.get("old", ""), d["new"], d.get("op", "edit"))
            write_lines(STORY, lines)
        elif path == "/api/add":
            if not re.fullmatch(r"scene-\d{2}", str(d["scene"])):
                raise ValueError("bad scene")
            lines = read_lines(STORY)
            add_line(lines, d["scene"], d["after"], d["kind"], d.get("speaker", ""), d["text"], d.get("label", ""), d.get("tone", ""))
            write_lines(STORY, lines)
        elif path == "/api/speaker":
            name = clean_name(d["name"])
            color, voice = d.get("color"), d.get("voice")
            if color is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(color)):
                raise ValueError("bad color")
            if voice is not None and not re.fullmatch(r"[A-Za-z0-9_]{0,30}", str(voice)):
                raise ValueError("bad voice")
            tone = d.get("tone")
            tone = None if tone is None else clean_tone(tone)
            lines = read_lines(STORY)
            before = next((x["voice"] for x in parse_speakers(lines) if x["name"] == name), None)
            ensure_speaker(lines, name, color, voice, tone)
            if voice and before is not None and voice != before:  # another voice = every line of this speaker must be made again
                mark_stale(lines, speech_scenes(lines, name))
            write_lines(STORY, lines)
        elif path == "/api/ttsmodel":
            model, scene = str(d.get("model", "")).strip(), d.get("scene")
            if model and not MODEL_RE.fullmatch(model):
                raise ValueError("bad model")
            lines = read_lines(STORY)
            if scene:
                if not re.fullmatch(r"scene-\d{2}", str(scene)):
                    raise ValueError("bad scene")
                set_scene_model(lines, scene, model)
                mark_stale(lines, [scene] if scene in speech_scenes(lines) else [])
            else:
                if not model:
                    raise ValueError("model is empty")
                set_default_model(lines, model)
                mark_stale(lines, speech_scenes(lines, own_model=False))
            write_lines(STORY, lines)
        elif path == "/api/delete":
            if not re.fullmatch(r"scene-\d{2}", str(d["scene"])):
                raise ValueError("bad scene")
            lines = read_lines(STORY)
            delete_line(lines, d["scene"], d["index"], d.get("old", ""))
            write_lines(STORY, lines)
        elif path == "/api/issue":
            if not re.fullmatch(r"scene-\d{2}", str(d["scene"])):
                raise ValueError("bad scene")
            lines = read_lines(STORY)
            if d.get("clear"):
                clear_issue(lines, d["scene"], d["index"])
            else:
                add_issue(lines, d["scene"], d["index"], d.get("message", ""))
            write_lines(STORY, lines)
        elif path == "/api/scenefx":
            if not re.fullmatch(r"scene-\d{2}", str(d["scene"])):
                raise ValueError("bad scene")
            lines = read_lines(STORY)
            set_scene_fx(lines, d["scene"], str(d.get("fx", ""))[:2000])
            write_lines(STORY, lines)
        elif path == "/api/vprompt":
            id_ = str(d["id"])
            if not re.fullmatch(r"IMG\d{3}", id_):
                raise ValueError("bad id")
            lines = read_lines(VPROMPTS) if os.path.exists(VPROMPTS) else [
                "# پرامپت‌های ویدیو (تصویر به ویدیو). هر بلوک با «=== IMG### ===» شروع می‌شه و کامل و مستقل است؛ تصویر همان شناسه، فریم اول ویدیوست.", ""]
            upsert_prompt(lines, id_, str(d.get("old", "")), str(d["new"]))
            write_lines(VPROMPTS, lines)
        elif path == "/api/prompt":
            id_ = str(d["id"])
            if not re.fullmatch(r"[A-Za-z0-9_]+", id_):
                raise ValueError("bad id")
            lines = read_lines(PROMPTS)
            changed = replace_prompt(lines, id_, str(d["old"]), str(d["new"]))
            write_lines(PROMPTS, lines)
            if changed and re.fullmatch(r"IMG\d{3}", id_):  # the picture was made from the old prompt
                sl = read_lines(STORY)
                try:
                    patch_image(sl, id_, stale=True)
                    write_lines(STORY, sl)
                except ValueError:
                    pass
        else:
            raise ValueError("unknown endpoint")
        return {"ok": True}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=ROOT))
    print(f"http://127.0.0.1:{PORT}/review.html", flush=True)

    def watchdog():  # page pings every 5 s; background tabs are slowed down, so wait IDLE s (3x before the first ping)
        while True:
            time.sleep(2)
            if time.time() - last_ping[0] > (IDLE if seen_ping[0] else IDLE * 3):
                srv.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    srv.serve_forever()
    print("stopped (page closed)", flush=True)
