# -*- coding: utf-8 -*-
"""Voice and tone test: makes the SAME English sentence with several models, voices and tones so YOU can listen and mark good / bad.
  python tools/voice_test.py                       show what would be made and what it costs (nothing is generated or charged)
  python tools/voice_test.py --yes                 generate the samples (existing files are skipped)
  python tools/voice_test.py --models elevenlabs/eleven-v4-turbo,elevenlabs/eleven-v3 --voices george,sarah --tones playful,mysterious --yes
Samples go to audio/_tests/ with an index.html. Open it from the running review server (python tools/serve.py):
  http://127.0.0.1:8765/audio/_tests/index.html
Every 👍 / 👎 is saved in voices/voice-config.json (voice on a model, tone on a model, «does the model obey tags»).
The tag is always sent in the test, whatever the config says about the model, because that is what is being tested."""
import argparse, html, os, sys, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voices  # noqa: E402
from kitcore import ROOT, STORY, read_lines  # noqa: E402
from story import parse_speakers  # noqa: E402
import tts  # noqa: E402

OUT = os.path.join(ROOT, "audio", "_tests")
TEXT = "I did not expect to find a door here. But here it is, and it is open."
MODELS = ["elevenlabs/eleven-v4-turbo", "elevenlabs/eleven-v3", "elevenlabs/eleven-v4", "elevenlabs/eleven-flash-v2.5"]
TONES = ["playful", "mysterious", "scared", "curious", "whisper", "thoughtful"]


def safe(x):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in x)


def file_of(model, voice, tone):
    return os.path.join(OUT, safe(model), "%s__%s.mp3" % (safe(voice), tone or "plain"))


def plan(args, cfg):
    models = [m for m in (args.models.split(",") if args.models else MODELS) if m in cfg["models"]]
    speakers = [s["voice"] for s in parse_speakers(read_lines(STORY)) if s["voice"]]
    tones = [t for t in cfg["tones"] if t["id"] in (args.tones.split(",") if args.tones else TONES) and t.get("tag")]
    jobs = []
    for m in models:
        have = list(cfg["voices"].get(m, {}))
        vs = [v for v in (args.voices.split(",") if args.voices else speakers) if v in have] or have[:2]
        for v in vs:
            for t in [None] + tones:
                jobs.append((m, v, t))
    return jobs


def page(jobs, cfg):
    rows = []
    for m in sorted({j[0] for j in jobs}):
        mj = [j for j in jobs if j[0] == m and os.path.exists(file_of(*[j[0], j[1], j[2]["id"] if j[2] else None]))]
        if not mj:
            continue
        rows.append('<h2>%s <small>برچسب‌ها: %s</small> <button onclick="send({model:\'%s\',tags:\'yes\'})">👍 این مدل برچسب را اعمال می‌کند</button>'
                    ' <button onclick="send({model:\'%s\',tags:\'no\'})">👎 اعمال نمی‌کند</button></h2><table>' % (
                        html.escape(m), cfg["models"][m].get("tags", "unknown"), m, m))
        for model, v, t in mj:
            tid = t["id"] if t else ""
            src = "%s/%s__%s.mp3" % (safe(model), safe(v), tid or "plain")
            rows.append('<tr><td dir="ltr">%s</td><td>%s</td><td dir="ltr">%s</td><td><audio controls preload="none" src="%s"></audio></td>'
                        '<td><button onclick="send({model:\'%s\',voice:\'%s\',result:\'good\'})">👍 صدا</button> <button onclick="send({model:\'%s\',voice:\'%s\',result:\'bad\'})">👎 صدا</button>%s</td></tr>'
                        % (html.escape(v), html.escape(t["fa"]) if t else "بدون لحن", html.escape(t["tag"]) if t else "",
                           src, model, v, model, v,
                           (' <button onclick="send({model:\'%s\',tone:\'%s\',result:\'good\'})">👍 لحن</button> <button onclick="send({model:\'%s\',tone:\'%s\',result:\'bad\'})">👎 لحن</button>'
                            % (model, tid, model, tid)) if t else ""))
        rows.append("</table>")
    doc = ('<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><title>تست صدا و لحن</title>'
           '<style>body{font:16px/1.8 Tahoma,sans-serif;margin:24px;background:#f6efe0}table{border-collapse:collapse;margin-bottom:24px}td{border-bottom:1px solid #d9ccb0;padding:4px 10px}'
           'button{font:inherit;cursor:pointer;border:1px solid #bdb394;border-radius:8px;background:#fff;padding:0 10px}small{color:#6b5320;font-weight:400}#m{position:fixed;top:8px;left:8px;background:#fff;padding:4px 12px;border-radius:8px}</style>'
           '<h1>تست صدا و لحن</h1><p dir="ltr">%s</p><div id="m"></div>%s'
           '<script>async function send(b){const r=await fetch("/api/voicetest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});'
           'document.getElementById("m").textContent=r.ok?"ثبت شد ✓":"خطا: "+(await r.json()).error}</script></html>') % (html.escape(TEXT), "".join(rows))
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8", newline="\n").write(doc)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models"); ap.add_argument("--voices"); ap.add_argument("--tones"); ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    cfg = voices.load_config()
    jobs = plan(args, cfg)
    todo = [j for j in jobs if not os.path.exists(file_of(j[0], j[1], j[2]["id"] if j[2] else None))]
    price = sum(float(cfg["models"][j[0]].get("price") or 0) * (len(TEXT) + (len(j[2]["tag"]) + 1 if j[2] else 0)) / 1000 for j in todo)
    print("%d samples in total, %d still to make; about $%.3f" % (len(jobs), len(todo), price))
    for m in sorted({j[0] for j in todo}):
        print("  ", m, sum(1 for j in todo if j[0] == m))
    if not args.yes:
        print("Nothing generated. Add --yes to make them.")
        return
    key = voices.load_key()
    if not key:
        sys.exit("OPENROUTER_API_KEY not found (environment or .env).")
    for m, v, t in todo:
        p = file_of(m, v, t["id"] if t else None)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            open(p, "wb").write(tts.synth(m, v, (t["tag"] + " " if t else "") + TEXT, key))
            print("ok  ", m, v, t["id"] if t else "plain", flush=True)
        except (RuntimeError, urllib.error.URLError) as e:
            print("FAIL", m, v, t["id"] if t else "plain", str(e)[:80], flush=True)
    os.makedirs(OUT, exist_ok=True)
    page(jobs, voices.load_config())
    print("Open: http://127.0.0.1:8765/audio/_tests/index.html  (while python tools/serve.py is running)")


if __name__ == "__main__":
    main()
