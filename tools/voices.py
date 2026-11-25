# -*- coding: utf-8 -*-
"""Voice configuration: models, voices and tones in ONE json file, voices/voice-config.json (safe to commit, edit by hand if you like).
  models : id -> {name, price, tags: yes|no|unknown, tested, note}      tags = does the model obey audio tags like [whispers]
  voices : model id -> voice name -> {accent, gender?, note?, tested?}  accent / gender / note / tested are yours: a refresh never erases them
  tones  : [{id, fa, match[], tag, tests{model: good|bad}}]            fa = the Persian name shown in the page and written in story.txt,
                                                                       match = other Persian words that mean the same, tag = English audio tag ("" = no tag)
Usage:  python tools/voices.py     (check the key, refresh the model and voice lists; voices/catalog.txt is rewritten as the raw list)
Key:    OPENROUTER_API_KEY in the environment, or in a .env file next to review.html (.env is git-ignored; never put the key in story.txt).
The first time the file is needed it is built from an existing voices/catalog.txt (if any) plus the default tones below."""
import datetime, json, os, re, sys, threading, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "voices", "catalog.txt")
CONFIG = os.path.join(ROOT, "voices", "voice-config.json")
API = "https://openrouter.ai/api/v1"
UNKNOWN = "؟"
LOCK = threading.RLock()
TAG_PREFIX = "elevenlabs/eleven-v"  # models of this family obey audio tags unless the config says "no"
MAX_TAGS = 2

# Starting tones (only used to create voice-config.json; after that the json is yours). tag "" = a known tone that sends nothing.
DEFAULT_TONES = [
    dict(id="whisper", fa="آهسته", match=["یواشکی", "نجوا"], tag="[whispers]"),
    dict(id="annoyed", fa="طلبکار", match=[], tag="[annoyed]"),
    dict(id="sheepish", fa="شرمنده", match=[], tag="[sheepishly]"),
    dict(id="laugh", fa="خنده", match=["خندان"], tag="[chuckles]"),
    dict(id="worried", fa="نگران", match=[], tag="[worried]"),
    dict(id="mischievous", fa="شیطون", match=[], tag="[mischievously]"),
    dict(id="playful", fa="شوخ", match=["بازیگوش"], tag="[playfully]"),
    dict(id="mysterious", fa="مرموز", match=["رازآلود"], tag="[mysteriously]"),
    dict(id="scared", fa="ترسیده", match=["ترس"], tag="[scared]"),
    dict(id="surprised", fa="با تعجب", match=["متعجب", "تعجب"], tag="[surprised]"),
    dict(id="curious", fa="کنجکاو", match=["پرسشی"], tag="[curious]"),
    dict(id="thoughtful", fa="متفکر", match=["فکور"], tag="[thoughtful]"),
    dict(id="neutral", fa="عادی", match=["توصیفی", "طبیعی", "صمیمی", "گرم"], tag=""),
]


def load_key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    p = os.path.join(ROOT, ".env")
    if not k and os.path.exists(p):
        for l in open(p, encoding="utf-8"):
            m = re.match(r"\s*OPENROUTER_API_KEY\s*=\s*(.+?)\s*$", l)
            if m:
                k = m.group(1).strip("\"'")
    return k


def _get(path, key):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def accent(voice):
    """Best guess from the voice name only (the API gives no accent): locale codes inside the name, Kokoro's a/b prefix."""
    if re.match(r"^a[fm]_", voice):
        return "en-US"
    if re.match(r"^b[fm]_", voice):
        return "en-GB"
    m = re.match(r"^([a-z]{2}-[A-Z]{2})-", voice) or re.search(r"-([a-z]{2})(?:$|-)", voice) or re.match(r"^([a-z]{2})_", voice)
    return m.group(1) if m else UNKNOWN


# ---------------------------------------------------------------- the json file
def _model(name, price="", old=None):
    m = dict(name=name, price=price, tags="unknown", tested="", note="")
    m.update({k: v for k, v in (old or {}).items() if k in ("tags", "tested", "note")})
    return m


def _from_catalog_txt():
    """Old plain-text catalogue -> (models, voices); {} when there is none."""
    models, voices, cur = {}, {}, None
    if os.path.exists(CATALOG):
        for l in open(CATALOG, encoding="utf-8"):
            l = l.rstrip("\n")
            if l.startswith("model:"):
                p = [x.strip() for x in l[6:].split("|")]
                cur = p[0]
                models[cur] = _model(p[2] if len(p) > 2 else cur, p[1] if len(p) > 1 else "")
                voices[cur] = {}
            elif l.startswith("voice:") and cur:
                p = [x.strip() for x in l[6:].split("|")]
                voices[cur][p[0]] = dict(accent=p[1] if len(p) > 1 and p[1] else UNKNOWN)
    return models, voices


def _dump(cfg):
    """Readable json: one line per model, voice and tone (a plain json.dumps would need ~5 lines per voice)."""
    j = lambda v: json.dumps(v, ensure_ascii=False)
    out = ['{', '  "version": 1,', '  "models": {']
    out.append(",\n".join("    %s: %s" % (j(k), j(v)) for k, v in sorted(cfg["models"].items())))
    out += ['  },', '  "voices": {']
    blocks = []
    for mid, vs in sorted(cfg["voices"].items()):
        body = ",\n".join("      %s: %s" % (j(n), j(v)) for n, v in vs.items())
        blocks.append("    %s: {%s}" % (j(mid), ("\n" + body + "\n    ") if body else ""))
    out.append(",\n".join(blocks))
    out += ['  },', '  "tones": [']
    out.append(",\n".join("    " + j(t) for t in cfg["tones"]))
    out += ['  ]', '}', '']
    return "\n".join(out)


def save_config(cfg):
    with LOCK:
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        tmp = CONFIG + ".tmp"
        open(tmp, "w", encoding="utf-8", newline="\n").write(_dump(cfg))
        for _ in range(40):  # Windows refuses while another program has the file open
            try:
                os.replace(tmp, CONFIG)
                return
            except PermissionError:
                time.sleep(0.05)
        os.replace(tmp, CONFIG)


def load_config():
    """The config dict. Built (and saved) from voices/catalog.txt + the default tones the first time."""
    with LOCK:
        if os.path.exists(CONFIG):
            try:
                cfg = json.load(open(CONFIG, encoding="utf-8"))
                for k, empty in (("models", {}), ("voices", {}), ("tones", [])):
                    cfg.setdefault(k, empty)
                return cfg
            except ValueError as e:
                raise ValueError("voices/voice-config.json خراب است (%s)؛ درستش کن یا پاکش کن تا دوباره ساخته شود" % e)
        models, voices = _from_catalog_txt()
        cfg = dict(version=1, models=models, voices=voices, tones=[dict(t, tests={}) for t in DEFAULT_TONES])
        save_config(cfg)
        return cfg


# ---------------------------------------------------------------- reading it
def read_catalog():
    """[{id, price, name, tags, tested, voices:[{name, accent, gender, note, tested}]}] sorted by id."""
    cfg, out = load_config(), []
    for mid, m in sorted(cfg["models"].items()):
        vs = [dict(name=n, accent=v.get("accent") or UNKNOWN, gender=v.get("gender", ""), note=v.get("note", ""), tested=v.get("tested", ""))
              for n, v in cfg["voices"].get(mid, {}).items()]
        out.append(dict(id=mid, price=m.get("price", ""), name=m.get("name", mid), tags=m.get("tags", "unknown"),
                        tested=m.get("tested", ""), note=m.get("note", ""), voices=vs))
    return out


def tones_for_page():
    return [dict(id=t["id"], fa=t["fa"], tag=t.get("tag", ""), words=[t["fa"]] + list(t.get("match", [])), tests=t.get("tests", {}))
            for t in load_config()["tones"]]


def match_tones(text, cfg=None):
    """Tones whose Persian name or alias appears in the text, in the order they appear."""
    text, found = text or "", []
    for i, t in enumerate((cfg or load_config())["tones"]):
        pos = [text.find(w) for w in [t["fa"]] + list(t.get("match", [])) if w and w in text]
        if pos:
            found.append((min(pos), i, t))
    return [t for _, _, t in sorted(found, key=lambda x: x[:2])]


def tone_tags(text, cfg=None):
    """(audio tags to send, known). known is False when a non-empty tone matches no tone of the config."""
    hit = match_tones(text, cfg)
    tags = []
    for t in hit:
        if t.get("tag") and t["tag"] not in tags:
            tags.append(t["tag"])
    return tags[:MAX_TAGS], bool(hit) or not (text or "").strip()


def model_takes_tags(model, cfg=None):
    t = ((cfg or load_config())["models"].get(model) or {}).get("tags", "unknown")
    return t == "yes" or (t != "no" and model.startswith(TAG_PREFIX))


def known_voice(model, voice):
    """'' when fine or unknown, else a text: the config lists voices for this model and the voice is not among them."""
    vs = load_config()["voices"].get(model) or {}
    return "" if not vs or voice in vs else "مدل %s صدای «%s» را ندارد" % (model, voice)


def mark_test(model=None, voice=None, tone=None, result="", tags=None):
    """Record what you heard: a voice on a model, a tone on a model, or whether a model obeys tags."""
    if result not in ("", "good", "bad"):
        raise ValueError("bad result")
    with LOCK:
        cfg = load_config()
        if model not in cfg["models"]:
            raise ValueError("unknown model")
        if tags is not None:
            if tags not in ("yes", "no", "unknown"):
                raise ValueError("bad tags")
            cfg["models"][model]["tags"] = tags
        if voice:
            if voice not in cfg["voices"].get(model, {}):
                raise ValueError("unknown voice")
            cfg["voices"][model][voice]["tested"] = result
        if tone:
            t = next((x for x in cfg["tones"] if x["id"] == tone), None)
            if not t:
                raise ValueError("unknown tone")
            t.setdefault("tests", {})
            if result:
                t["tests"][model] = result
            else:
                t["tests"].pop(model, None)
        save_config(cfg)


TONE_NAME = re.compile(r"[^|()\[\]\n\r]{1,30}")
TONE_TAG = re.compile(r"\[[A-Za-z][A-Za-z \-]{1,30}\]")


def add_tone(fa, tag="", match=None):
    """A new tone: the Persian name (what is written in story.txt) and the English audio tag it sends ("" = a known tone that sends nothing)."""
    fa, tag = (fa or "").strip(), (tag or "").strip()
    if not TONE_NAME.fullmatch(fa):
        raise ValueError("اسم لحن باید فارسی و کوتاه باشه (تا ۳۰ حرف، بدون | و پرانتز)")
    if tag and not TONE_TAG.fullmatch(tag):
        raise ValueError("برچسب باید مثل [whispers] باشه: انگلیسی، توی کروشه")
    with LOCK:
        cfg = load_config()
        if match_tones(fa, cfg):
            raise ValueError("این لحن (یا یه لحن هم‌معنی‌اش) از قبل هست")
        n = 1 + max([int(t["id"][1:]) for t in cfg["tones"] if re.fullmatch(r"c\d+", t["id"])] or [0])
        cfg["tones"].append(dict(id="c%d" % n, fa=fa, match=[m.strip() for m in (match or []) if m and m.strip()], tag=tag, tests={}))
        save_config(cfg)
    return "c%d" % n


def remove_tone(tone_id):
    with LOCK:
        cfg = load_config()
        left = [t for t in cfg["tones"] if t["id"] != tone_id]
        if len(left) == len(cfg["tones"]):
            raise ValueError("unknown tone")
        cfg["tones"] = left
        save_config(cfg)


def status():
    return dict(has_key=bool(load_key()), updated=int(os.path.getmtime(CONFIG)) if os.path.exists(CONFIG) else None)


# ---------------------------------------------------------------- refresh from the API
def refresh():
    """Test the key, fetch the speech models and merge them into voice-config.json (your own fields stay). Returns {ok, message}."""
    key = load_key()
    if not key:
        return dict(ok=False, message="کلید پیدا نشد: OPENROUTER_API_KEY را در محیط یا در فایل .env کنار review.html بگذار.")
    try:
        _get("/key", key)
        data = _get("/models?output_modalities=speech", key)["data"]
    except urllib.error.HTTPError as e:
        return dict(ok=False, message="کلید رد شد یا سرویس جواب نداد (HTTP %s)." % e.code)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return dict(ok=False, message="اتصال برقرار نشد: %s" % str(e)[:80])
    with LOCK:
        cfg = load_config()
        known = {n: v.get("accent") for vs in cfg["voices"].values() for n, v in vs.items() if v.get("accent") not in (None, "", UNKNOWN)}
        models, voices, raw = {}, {}, ["# فهرست خام مدل‌ها و صداها؛ ساخته‌شده با «python tools/voices.py» در " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                       "# فایل اصلی voices/voice-config.json است؛ این فهرست هر بار دوباره نوشته می‌شود.", ""]
        for m in sorted(data, key=lambda m: m["id"]):
            mid = m["id"]
            price = ("%.4f" % (float(m.get("pricing", {}).get("prompt") or 0) * 1000)).rstrip("0").rstrip(".")
            name = m.get("name", mid).split(": ", 1)[-1]
            models[mid] = _model(name, price, cfg["models"].get(mid))
            voices[mid] = {}
            raw.append("model: %s | %s | %s" % (mid, price, name))
            for v in m.get("supported_voices") or []:
                voices[mid][v] = dict(cfg["voices"].get(mid, {}).get(v) or {}, accent=(cfg["voices"].get(mid, {}).get(v) or {}).get("accent") or known.get(v) or accent(v))
                raw.append("voice: %s | %s" % (v, voices[mid][v]["accent"]))
            raw.append("")
        cfg["models"], cfg["voices"] = models, voices
        save_config(cfg)
        os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
        open(CATALOG, "w", encoding="utf-8", newline="\n").write("\n".join(raw))
    return dict(ok=True, message="%d مدل صدا به‌روز شد." % len(data))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = refresh()
    print(r["message"])
    sys.exit(0 if r["ok"] else 1)
