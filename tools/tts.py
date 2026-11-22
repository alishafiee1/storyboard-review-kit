# -*- coding: utf-8 -*-
"""Narration maker: one mp3 per dialogue line -> audio/<lang>/<id>.mp3, through OpenRouter's /audio/speech endpoint.
Voice = the line's speaker (speaker: line at the top of scenario/story.txt); model = the scene's «model:» line, else the file's «tts-model:» line.
The page's «بازسازی صدا» button calls make(); from a terminal:
  python tools/tts.py fa|en [id ...]       (existing files are skipped unless TTS_FORCE=1)
Key: OPENROUTER_API_KEY (environment or .env). Do not use google/gemini-3.8-*-tts for Persian: it reads Persian wrongly (tested)."""
import concurrent.futures as cf, json, os, subprocess, sys, time, urllib.error, urllib.request, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serve import ROOT, spoken_lines  # noqa: E402
from voices import load_key, read_catalog  # noqa: E402

PCM_ONLY = ("google/", "heygen/")  # these models answer raw 24 kHz pcm, the others answer mp3
# A line's tone (Persian words from story.txt) becomes an ElevenLabs v3/v4 audio tag in front of the English text, e.g. «[whispers] ...».
# First match wins. Only English lines on elevenlabs/eleven-v* models get a tag (other models would read the tag aloud).
TONE_TAGS = [("یواشکی", "[whispers]"), ("آهسته", "[whispers]"), ("طلبکار", "[annoyed]"), ("شرمنده", "[sheepishly]"), ("خنده", "[chuckles]"),
             ("نگران", "[worried]"), ("شیطون", "[mischievously]"), ("شوخ", "[playfully]")]


def style_text(text, tone, lang, model):
    if lang != "en" or not model.startswith("elevenlabs/eleven-v"):
        return text
    tag = next((t for k, t in TONE_TAGS if k in (tone or "")), "")
    return f"{tag} {text}" if tag else text


def synth(model, voice, text, key):
    """Returns mp3 bytes."""
    pcm = model.startswith(PCM_ONLY)
    body = {"model": model, "input": text, "voice": voice, "response_format": "pcm" if pcm else "mp3"}
    req = urllib.request.Request("https://openrouter.ai/api/v1/audio/speech", data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %s %s" % (e.code, e.read().decode("utf-8", "ignore")[:120]))
    if len(data) < 4800:
        raise RuntimeError("empty audio")
    if not pcm:
        return data
    tmp = "%s.%d.wav" % (os.path.join(ROOT, "audio", "_tmp"), os.getpid())
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(data)
    try:
        return subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-codec:a", "libmp3lame", "-q:a", "4", "-f", "mp3", "-"],
                              check=True, capture_output=True).stdout
    finally:
        os.remove(tmp)


def voice_problem(model, voice):
    """A text when the catalogue knows this model's voices and the voice is not one of them."""
    m = next((x for x in read_catalog() if x["id"] == model), None)
    if m and m["voices"] and voice not in [v["name"] for v in m["voices"]]:
        return "مدل %s صدای «%s» را ندارد" % (model, voice)
    return ""


def make(items, lang, force=False, workers=4, on_done=None):
    """items = spoken_lines() entries. Returns {id: 'ok' | 'cached' | 'FAILED ...'}."""
    key = load_key()
    out_dir = os.path.join(ROOT, "audio", lang)
    os.makedirs(out_dir, exist_ok=True)
    result = {}

    def one(it):
        mp3 = os.path.join(out_dir, it["id"] + ".mp3")
        if os.path.exists(mp3) and not force:
            return it["id"], "cached"
        if not key:
            return it["id"], "FAILED no key"
        bad = voice_problem(it["model"], it["voice"])
        if bad:
            return it["id"], "FAILED " + bad
        err = ""
        for attempt in range(4):
            try:
                data = synth(it["model"], it["voice"], style_text(it["spoken"], it.get("tone", ""), lang, it["model"]), key)
                tmp = mp3 + ".tmp"
                open(tmp, "wb").write(data)
                os.replace(tmp, mp3)
                return it["id"], "ok"
            except (urllib.error.URLError, RuntimeError, TimeoutError, subprocess.CalledProcessError) as e:
                err = str(e)[:100]
                if "HTTP 4" in err:  # a rejected request will not get better by retrying
                    break
                time.sleep(3 * (attempt + 1))
        return it["id"], "FAILED " + err

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for id_, st in ex.map(one, items):
            result[id_] = st
            if on_done:
                on_done(id_, st)
    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lang = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("fa", "en") else "fa"
    only = [a for a in sys.argv[1:] if a not in ("fa", "en")]
    items = [i for i in spoken_lines(lang) if not only or i["id"] in only]
    print(len(items), "lines, lang", lang, flush=True)
    res = make(items, lang, force=bool(os.environ.get("TTS_FORCE")), on_done=lambda i, s: s != "cached" and print(i, s, flush=True))
    print("done:", sum(v == "ok" for v in res.values()), "made,", sum(v.startswith("FAILED") for v in res.values()), "failed")
