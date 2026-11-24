# -*- coding: utf-8 -*-
"""Slow actions that talk to the network (voices, samples, subtitles) and the shared state of the running voice job."""
import os, re, threading
from kitcore import LANGS, LOCK, MODEL_RE, ROOT, STORY, VOICE_RE, read_lines, write_lines
from story import spoken_lines, story_scenes
from edits import pick_made, stale_lines


JOB = dict(state="idle", scene="", done=0, total=0, errors=[], warnings=[])


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


def regen_job(scene="", image=""):
    """Make the voices of every dialogue line that is out of date (only the lines of one scene or one picture when given). Per line: a line whose
    voice was made loses its out-of-date flag; a failed line keeps it."""
    import tts
    try:
        with LOCK:
            stale = story_stale(scene, image)
        todo = []
        for lg in LANGS:
            want = {i["id"] for i in stale if lg in i["stale"]}
            if want:
                todo.append((lg, want, [i for i in spoken_lines(lg) if i["id"] in want]))
        JOB["total"] = sum(len(items) for _, _, items in todo)

        def tick(id_, st):
            JOB["done"] += 1
            if st.startswith("FAILED"):
                JOB["errors"].append(f"{id_}: {st[7:]}")
        for lg, want, items in todo:
            res = tts.make(items, lg, force=True, on_done=tick, warnings=JOB["warnings"]) if items else {}
            pick_made(items, res, lg)
            ok = want - {i for i, st in res.items() if st.startswith("FAILED")}
            with LOCK:  # lines with nothing to say in this language have nothing to make: they are up to date too
                lines = read_lines(STORY)
                for sid, ids in by_scene(stale, ok).items():
                    stale_lines(lines, sid, lambda it: it["id"] in ids, [lg], False)
                write_lines(STORY, lines)
        JOB["state"] = "failed" if JOB["errors"] else "done"
    except Exception as e:  # the page must always get an end state
        JOB["errors"].append(str(e)[:150])
        JOB["state"] = "failed"


def story_stale(scene="", image=""):
    """[{id, scene, stale}] of the dialogue lines (of scenes that are on) whose voice is out of date, limited to one scene or one picture."""
    out = []
    for sc in story_scenes():
        if sc["off"] or scene and sc["id"] != scene:
            continue
        for b in sc["blocks"]:
            out += [dict(id=it["id"], scene=sc["id"], stale=it["vstale"]) for it in b["items"]
                    if it["k"] == "say" and it["vstale"] and (not image or it["img"] == image)]
    return out


def by_scene(stale, ids):
    out = {}
    for i in stale:
        if i["id"] in ids:
            out.setdefault(i["scene"], set()).add(i["id"])
    return out


def api_regen(d):
    """Make the voices of the lines that are out of date: all of them, or only those of one picture (`image`) or one scene (`scene`)."""
    scene, image = str(d.get("scene", "")), str(d.get("image", ""))
    if scene and not re.fullmatch(r"scene-\d{2,3}", scene) or image and not re.fullmatch(r"IMG\d{3}", image):
        raise ValueError("bad scene or image")
    if JOB["state"] == "running":
        raise ValueError("یک بازسازی دیگر در حال انجام است")
    shown = scene or next((s["id"] for s in story_scenes() for b in s["blocks"] if any(im["id"] == image for im in b["images"])), "")  # progress shows next to this scene
    JOB.update(state="running", scene=shown, done=0, total=0, errors=[], warnings=[])
    threading.Thread(target=regen_job, args=(scene, image), daemon=True).start()
    return {"ok": True}


def line_voice_job(id_, langs, model):
    import tts
    try:
        todo = []
        for lg in langs:
            its = [dict(i, model=model) for i in spoken_lines(lg) if i["id"] == id_]
            if its:
                todo.append((lg, its))
        JOB["total"] = sum(len(x) for _, x in todo)

        def tick(i, st):
            JOB["done"] += 1
            if st.startswith("FAILED"):
                JOB["errors"].append(f"{i}: {st[7:]}")
        for lg, its in todo:
            res = tts.make(its, lg, force=True, on_done=tick, warnings=JOB["warnings"])
            pick_made(its, res, lg)  # the voice just made is the chosen one; the old file of the same model went to the archive
        JOB["state"] = "failed" if JOB["errors"] else "done"
    except Exception as e:
        JOB["errors"].append(str(e)[:150])
        JOB["state"] = "failed"


def api_linevoice(d):
    """Make one line's voice with a chosen model (fa, en or both); it sits next to the voices the line already has."""
    scene, id_, model = str(d.get("scene", "")), str(d.get("id", "")), str(d.get("model", ""))
    langs = [lg for lg in d.get("langs", []) if lg in LANGS]
    if scene and not re.fullmatch(r"scene-\d{2,3}", scene) or not re.fullmatch(r"[A-Za-z0-9_-]+", id_) or not MODEL_RE.fullmatch(model) or not langs:
        raise ValueError("bad scene, id, model or language")
    if JOB["state"] == "running":
        raise ValueError("یک ساخت صدای دیگه در حال انجام است")
    JOB.update(state="running", scene=scene, done=0, total=0, errors=[], warnings=[])
    threading.Thread(target=line_voice_job, args=(id_, langs, model), daemon=True).start()
    return {"ok": True}


def api_subtitles(d):
    import subtitles
    return subtitles.make_all()


SLOW = {"/api/subtitles": api_subtitles, "/api/voices/refresh": api_refresh, "/api/sample": api_sample, "/api/regen": api_regen, "/api/linevoice": api_linevoice}


SAMPLE_TEXT = "سلام، این یه نمونهٔ صداست. امروز می‌خوام یه چیز جالب بهت نشون بدم."
