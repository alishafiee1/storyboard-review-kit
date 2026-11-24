# -*- coding: utf-8 -*-
"""Narration maker: one mp3 per dialogue line and take -> audio/<lang>/<id>_<rid>.mp3 (id = IMG045-1, rid = 8 random hex digits: every take is its own
version and nothing is overwritten), through OpenRouter's /audio/speech endpoint. Who made it (model, voice, tone, time) goes to audio/<lang>/voices.tsv.
Voice = the line's speaker (speaker: line at the top of scenario/story.txt); model = the scene's «model:» line, else the file's «tts-model:» line.
The page's «بازسازی صدا» button calls make(); from a terminal:
  python tools/tts.py fa|en [id ...]       (existing files are skipped unless TTS_FORCE=1)
Key: OPENROUTER_API_KEY (environment or .env). Do not use google/gemini-3.8-*-tts for Persian: it reads Persian wrongly (tested)."""
import concurrent.futures as cf, json, os, secrets, subprocess, sys, threading, time, urllib.error, urllib.request, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kitcore import ROOT  # noqa: E402
from media import audio_index, audio_variants, variant_tag  # noqa: E402
from edits import pick_made  # noqa: E402
from story import spoken_lines  # noqa: E402
import voices  # noqa: E402
from voices import load_key  # noqa: E402

PCM_ONLY = ("google/", "heygen/")  # these models answer raw 24 kHz pcm, the others answer mp3
# A line's tone (Persian words from story.txt) becomes up to two audio tags in front of the English text, e.g. «[whispers] ...».
# The tones, their tags and which models take tags all live in voices/voice-config.json (see tools/voices.py).


def style_text(text, tone, lang, model, warn=None):
    """Tag + text. An unknown tone is reported through warn(tone) instead of being ignored silently."""
    if not (tone or "").strip():
        return text
    tags, known = voices.tone_tags(tone)
    if not known and warn:
        warn(tone)
    if lang != "en" or not tags or not voices.model_takes_tags(model):
        return text
    return " ".join(tags) + " " + text


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


TSV_LOCK = threading.Lock()
TSV_HEAD = "file\tmodel\tvoice\ttone\ttime"


def log_voice(out_dir, name, it):
    """One line in audio/<lang>/voices.tsv for the file just made (the model is not part of the file name any more)."""
    clean = lambda s: str(s or "").replace("\t", " ").replace("\n", " ")
    path = os.path.join(out_dir, "voices.tsv")
    with TSV_LOCK:
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8", newline="") as fh:
            fh.write((TSV_HEAD + "\n" if new else "") + "\t".join([name, clean(it["model"]), clean(it["voice"]), clean(it.get("tone")), time.strftime("%Y-%m-%d %H:%M:%S")]) + "\n")


def made_by(out_dir, lang, id_, model, idx):
    """True when this line already has a voice of this model: an old <id>.<tag>.mp3, or a take recorded in voices.tsv with that model."""
    tag = variant_tag(model)
    for v in audio_variants(lang, id_, idx):
        if v["name"] == tag:
            return True
    try:
        rows = [l.split("\t") for l in open(os.path.join(out_dir, "voices.tsv"), encoding="utf-8").read().split("\n")[1:] if l.strip()]
    except OSError:
        return False
    have = {os.path.basename(v["path"]) for v in audio_variants(lang, id_, idx)}
    return any(len(r) > 1 and r[1] == model and r[0] in have for r in rows)


def voice_problem(model, voice):
    """A text when the config knows this model's voices and the voice is not one of them."""
    return voices.known_voice(model, voice)


def make(items, lang, force=False, workers=4, on_done=None, warnings=None):
    """items = spoken_lines() entries. Returns {id: 'ok' | 'cached' | 'FAILED ...'}. Unknown tones are appended (once each) to warnings."""
    warnings = warnings if warnings is not None else []

    def warn(tone):
        msg = "لحن «%s» توی voices/voice-config.json نیست؛ بدون برچسب ساخته شد" % tone
        if msg not in warnings:
            warnings.append(msg)

    key = load_key()
    out_dir = os.path.join(ROOT, "audio", lang)
    os.makedirs(out_dir, exist_ok=True)
    result = {}
    idx = audio_index(lang)  # read the folder once, not once per line

    def one(it):
        rid = secrets.token_hex(4)  # every take is a new version: IMG045-1_ab12cd34.mp3, nothing is overwritten or archived
        mp3 = os.path.join(out_dir, "%s_%s.mp3" % (it["id"], rid))
        if not force and made_by(out_dir, lang, it["id"], it["model"], idx):
            return it["id"], "cached"
        if not key:
            return it["id"], "FAILED no key"
        bad = voice_problem(it["model"], it["voice"])
        if bad:
            return it["id"], "FAILED " + bad
        err = ""
        for attempt in range(4):
            try:
                data = synth(it["model"], it["voice"], style_text(it["spoken"], it.get("tone", ""), lang, it["model"], warn), key)
                tmp = mp3 + ".tmp"
                open(tmp, "wb").write(data)
                os.replace(tmp, mp3)
                log_voice(out_dir, os.path.basename(mp3), it)
                it["variant"] = rid  # the page's choice for this line: pick_made() writes it under the line
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
    warns = []
    res = make(items, lang, force=bool(os.environ.get("TTS_FORCE")), on_done=lambda i, s: s != "cached" and print(i, s, flush=True), warnings=warns)
    pick_made(items, res, lang)
    for w in warns:
        print("⚠", w)
    print("done:", sum(v == "ok" for v in res.values()), "made,", sum(v.startswith("FAILED") for v in res.values()), "failed")
