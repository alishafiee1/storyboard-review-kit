# -*- coding: utf-8 -*-
"""Voice catalogue: asks OpenRouter which speech models and voices this key can use and writes voices/catalog.txt.
Usage:  python tools/voices.py            (check the key, refresh voices/catalog.txt)
Key:    OPENROUTER_API_KEY in the environment, or in a .env file next to review.html (.env is git-ignored; never put the key in story.txt).
Format of voices/catalog.txt (plain text, safe to commit):
  model: <id> | <price per 1000 input units, USD> | <name>
  voice: <name> | <accent / language, or ؟ when the API does not say>
An accent written by hand (anything but ؟) survives the next refresh."""
import datetime, json, os, re, sys, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "voices", "catalog.txt")
API = "https://openrouter.ai/api/v1"
UNKNOWN = "؟"


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


def read_catalog():
    """[{id, price, name, voices:[{name, accent}]}] ([] when the file does not exist yet)."""
    out = []
    if not os.path.exists(CATALOG):
        return out
    for l in open(CATALOG, encoding="utf-8"):
        l = l.rstrip("\n")
        if l.startswith("model:"):
            p = [x.strip() for x in l[6:].split("|")]
            out.append(dict(id=p[0], price=p[1] if len(p) > 1 else "", name=p[2] if len(p) > 2 else p[0], voices=[]))
        elif l.startswith("voice:") and out:
            p = [x.strip() for x in l[6:].split("|")]
            out[-1]["voices"].append(dict(name=p[0], accent=p[1] if len(p) > 1 and p[1] else UNKNOWN))
    return out


def status():
    return dict(has_key=bool(load_key()), updated=int(os.path.getmtime(CATALOG)) if os.path.exists(CATALOG) else None)


def refresh():
    """Test the key, fetch the speech models and write voices/catalog.txt. Returns {ok, message}."""
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
    old = {v["name"]: v["accent"] for m in read_catalog() for v in m["voices"] if v["accent"] != UNKNOWN}
    out = ["# فهرست مدل‌ها و صداهای قابل استفاده با کلید فعلی؛ ساخته‌شده با «python tools/voices.py» در " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "# لهجه را API نمی‌دهد؛ جایی که ؟ هست یا از اسم صدا حدس زده شده، با دست هم می‌شود نوشت و با رفرش بعدی پاک نمی‌شود.", ""]
    for m in sorted(data, key=lambda m: m["id"]):
        price = float(m.get("pricing", {}).get("prompt") or 0) * 1000
        out.append("model: %s | %s | %s" % (m["id"], ("%.4f" % price).rstrip("0").rstrip("."), m.get("name", m["id"]).split(": ", 1)[-1]))
        for v in m.get("supported_voices") or []:
            out.append("voice: %s | %s" % (v, old.get(v) or accent(v)))
        out.append("")
    os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
    tmp = CATALOG + ".tmp"
    open(tmp, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    os.replace(tmp, CATALOG)
    return dict(ok=True, message="%d مدل صدا به‌روز شد." % len(data))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = refresh()
    print(r["message"])
    sys.exit(0 if r["ok"] else 1)
