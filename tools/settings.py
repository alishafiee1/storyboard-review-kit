# -*- coding: utf-8 -*-
"""The page's settings panel: the OpenRouter key (.env), the Downloads watcher (kit-config.json) and the kit version.
The key is only ever written, never sent back to the page: the page learns just whether one is set and where it comes from."""
import json, os, re
import voices
from kitcore import ROOT, write_lines
from flowname import config

ENV = os.path.join(ROOT, ".env")
CFG = os.path.join(ROOT, "kit-config.json")
KEYLINE = re.compile(r"\s*OPENROUTER_API_KEY\s*=")


def watch_enabled():
    """On by default; kit-config.json "watch_downloads": false turns it off; the tests set STORYBOARD_NO_WATCH=1 so a throw-away project never
    touches the real Downloads folder (an explicit true still wins)."""
    wd = config().get("watch_downloads")
    return wd is True or (wd is not False and not os.environ.get("STORYBOARD_NO_WATCH"))


def downloads_dir():
    import watch
    return watch.downloads_dir()


def version():
    try:
        return open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    except OSError:
        return ""


def key_source():
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        return "env"
    return ".env" if voices.load_key() else ""


def get():
    src = key_source()
    d = config().get("downloads")
    return dict(key_set=bool(src), key_source=src, watch=watch_enabled(), downloads=downloads_dir(),
                downloads_custom=d.strip() if isinstance(d, str) else "", version=version())


def _set_key(key):
    key = (key or "").strip().strip("\"'")
    if not re.fullmatch(r"[\x21-\x7e]{8,400}", key):
        raise ValueError("کلید درست به نظر نمی‌رسه (فقط حروف و عدد انگلیسی، بدون فاصله)")
    lines = open(ENV, encoding="utf-8").read().splitlines() if os.path.exists(ENV) else []
    lines = [l for l in lines if not KEYLINE.match(l)] + ["OPENROUTER_API_KEY=" + key]
    write_lines(ENV, lines)


def _set_config(patch):
    cfg = config()
    for k, v in patch.items():
        if v is None:
            cfg.pop(k, None)
        else:
            cfg[k] = v
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, CFG)


def save(d):
    """{key?, downloads?, watch_downloads?}: only the fields that are present change. Returns the new state (and a note if an
    environment variable hides the .env key)."""
    note = ""
    if "key" in d:
        _set_key(str(d["key"]))
        if os.environ.get("OPENROUTER_API_KEY", "").strip():
            note = "یه متغیر محیطی OPENROUTER_API_KEY هم تنظیم شده و جلوتر از .env حساب می‌شه؛ برای اثر گرفتن حذفش کن."
    patch = {}
    if "downloads" in d:
        p = str(d["downloads"] or "").strip()
        if p:
            if not os.path.isdir(os.path.expanduser(p) if os.path.isabs(os.path.expanduser(p)) else os.path.join(ROOT, p)):
                raise ValueError("این پوشه وجود نداره: " + p)
            patch["downloads"] = p
        else:
            patch["downloads"] = None
    if "watch_downloads" in d:
        if not isinstance(d["watch_downloads"], bool):
            raise ValueError("watch_downloads باید روشن یا خاموش باشه")
        patch["watch_downloads"] = d["watch_downloads"]
    if patch:
        _set_config(patch)
    return dict(ok=True, note=note, **get())


def test_key():
    """Ask OpenRouter about the key (GET /key). Never returns the key itself."""
    key = voices.load_key()
    if not key:
        return dict(ok=False, message="هنوز کلیدی تنظیم نشده.")
    try:
        r = voices._get("/key", key).get("data", {})
    except Exception as e:
        code = getattr(e, "code", None)
        return dict(ok=False, message="کلید رد شد (HTTP %s)." % code if code else "اتصال برقرار نشد: %s" % str(e)[:80])
    left = r.get("limit_remaining")
    return dict(ok=True, message="کلید درسته" + (" · اعتبار باقی‌مانده: %s دلار" % round(left, 2) if isinstance(left, (int, float)) else ""))
