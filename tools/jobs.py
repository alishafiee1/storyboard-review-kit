# -*- coding: utf-8 -*-
"""Slow actions that talk to the network (voices, samples, subtitles) and the shared state of the running voice job."""
import os, re, threading
from kitcore import BOOK_RULES, LANGS, LOCK, MODEL_RE, ROOT, STORY, VOICE_RE, book_path, read_lines, write_lines
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


def regen_job(scene="", image="", book="story"):
    """Make the voices of every dialogue line that is out of date (only the lines of one scene or one picture when given). Per line: a line whose
    voice was made loses its out-of-date flag; a failed line keeps it."""
    import tts
    try:
        with LOCK:
            stale = story_stale(scene, image, book=book)
        todo = []
        for lg in LANGS:
            want = {i["id"] for i in stale if lg in i["stale"]}
            if want:
                todo.append((lg, want, [i for i in spoken_lines(lg, book=book) if i["id"] in want]))
        JOB["total"] = sum(len(items) for _, _, items in todo)

        def tick(id_, st):
            JOB["done"] += 1
            if st.startswith("FAILED"):
                JOB["errors"].append(f"{id_}: {st[7:]}")
        bpath = book_path(book)
        for lg, want, items in todo:
            res = tts.make(items, lg, force=True, on_done=tick, warnings=JOB["warnings"]) if items else {}
            pick_made(items, res, lg)
            ok = want - {i for i, st in res.items() if st.startswith("FAILED")}
            with LOCK:  # lines with nothing to say in this language have nothing to make: they are up to date too
                lines = read_lines(bpath)
                for sid, ids in by_scene(stale, ok).items():
                    stale_lines(lines, sid, lambda it: it["id"] in ids, [lg], False, book=book)
                write_lines(bpath, lines)
        JOB["state"] = "failed" if JOB["errors"] else "done"
    except Exception as e:  # the page must always get an end state
        JOB["errors"].append(str(e)[:150])
        JOB["state"] = "failed"


def story_stale(scene="", image="", book="story"):
    """[{id, scene, stale}] of the dialogue lines (of scenes that are on) whose voice is out of date, limited to one scene or one picture."""
    out = []
    for sc in story_scenes(book=book):
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
    book = d.get("book") or "story"
    rules = BOOK_RULES[book]
    scene, image = str(d.get("scene", "")), str(d.get("image", ""))
    if scene and not rules["section_re"].fullmatch(scene) or image and not rules["item_re"].fullmatch(image):
        raise ValueError("bad scene or image")
    if JOB["state"] == "running":
        raise ValueError("یک بازسازی دیگر در حال انجام است")
    shown = scene or next((s["id"] for s in story_scenes(book=book) for b in s["blocks"] if any(im["id"] == image for im in b["images"])), "")  # progress shows next to this scene
    JOB.update(state="running", scene=shown, done=0, total=0, errors=[], warnings=[])
    threading.Thread(target=regen_job, args=(scene, image, book), daemon=True).start()
    return {"ok": True}


def line_voice_job(id_, langs, model, book="story"):
    import tts
    try:
        todo = []
        for lg in langs:
            its = [dict(i, model=model) for i in spoken_lines(lg, book=book) if i["id"] == id_]
            if its:
                todo.append((lg, its))
        JOB["total"] = sum(len(x) for _, x in todo)

        def tick(i, st):
            JOB["done"] += 1
            if st.startswith("FAILED"):
                JOB["errors"].append(f"{i}: {st[7:]}")
        for lg, its in todo:
            res = tts.make(its, lg, force=True, on_done=tick, warnings=JOB["warnings"])
            pick_made(its, res, lg)  # the voice just made is the chosen one; it is a new file next to the older takes
        JOB["state"] = "failed" if JOB["errors"] else "done"
    except Exception as e:
        JOB["errors"].append(str(e)[:150])
        JOB["state"] = "failed"


def api_linevoice(d):
    """Make one line's voice with a chosen model (fa, en or both); it sits next to the voices the line already has."""
    book = d.get("book") or "story"
    rules = BOOK_RULES[book]
    scene, id_, model = str(d.get("scene", "")), str(d.get("id", "")), str(d.get("model", ""))
    langs = [lg for lg in d.get("langs", []) if lg in LANGS]
    if scene and not rules["section_re"].fullmatch(scene) or not re.fullmatch(r"[A-Za-z0-9_-]+", id_) or not MODEL_RE.fullmatch(model) or not langs:
        raise ValueError("bad scene, id, model or language")
    if JOB["state"] == "running":
        raise ValueError("یک ساخت صدای دیگه در حال انجام است")
    JOB.update(state="running", scene=scene, done=0, total=0, errors=[], warnings=[])
    threading.Thread(target=line_voice_job, args=(id_, langs, model, book), daemon=True).start()
    return {"ok": True}


def api_subtitles(d):
    import subtitles
    return subtitles.make_all()


def api_tonesample(d):
    """The fixed Persian sentence with a tone's tag in front, in this model + voice (cached): so a tone can be heard before it is marked as working."""
    import tts, voices
    model, voice, tid = str(d.get("model", "")), str(d.get("voice", "")), str(d.get("tone", ""))
    if not MODEL_RE.fullmatch(model) or not VOICE_RE.fullmatch(voice):
        raise ValueError("bad model or voice")
    t = next((x for x in voices.load_config()["tones"] if x["id"] == tid), None)
    if not t or not t.get("tag"):
        raise ValueError("این لحن برچسبی نداره که تست بشه")
    bad = tts.voice_problem(model, voice)
    if bad:
        raise ValueError(bad)
    key = voices.load_key()
    if not key:
        raise ValueError("کلید API پیدا نشد")
    name = "%s__%s__%s.mp3" % (re.sub(r"[^A-Za-z0-9_.-]", "_", model), re.sub(r"[^A-Za-z0-9_.-]", "_", voice), re.sub(r"[^A-Za-z0-9_.-]", "_", tid))
    p = os.path.join(ROOT, "audio", "_samples", name)
    if not os.path.exists(p):
        try:
            data = tts.synth(model, voice, t["tag"] + " " + SAMPLE_TEXT, key)
        except RuntimeError as e:
            raise ValueError(str(e))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)
    return {"ok": True, "url": "audio/_samples/" + name}


def api_pack(d):
    """The zip for the editor (chosen pictures and voices, the review page, the Premiere package): written next to the project folder."""
    import pack
    pkg = pack.pick_package(None)
    miss = pack.problems(bool(d.get("clips")), pkg)
    path, n = pack.pack(bool(d.get("clips")), None, pkg, selected=True)
    return {"ok": True, "path": path, "files": n, "mb": round(os.path.getsize(path) / 1e6, 1), "package": pkg or "", "missing": miss[:20]}


def api_premiere_export(d):
    """Build a simple Premiere XML timeline into premiere/premiere_<lang>.xml."""
    import premiere_export
    lang = str(d.get("lang", "fa"))
    if lang not in LANGS:
        raise ValueError("bad lang")
    out = os.path.join(ROOT, "premiere", f"premiere_{lang}.xml")
    path, warns = premiere_export.build(lang=lang, out=out)
    return {"ok": True, "path": os.path.relpath(path, ROOT).replace("\\", "/"), "warnings": warns[:20]}


def api_premiere_check(d):
    """Check all Premiere XML files in the project for missing or absolute paths."""
    import premiere_check
    xmls = premiere_check.find_xmls()
    out = []
    for x in xmls:
        r = premiere_check.check(x)
        out.append({"name": os.path.relpath(x, ROOT).replace("\\", "/"), "total": r["total"], "missing": len(r["missing"]), "absolute": len(r["absolute"])})
    return {"ok": True, "xmls": out}


SLOW = {"/api/pack": api_pack, "/api/premiere/export": api_premiere_export, "/api/premiere/check": api_premiere_check, "/api/tonesample": api_tonesample, "/api/settings/testkey": lambda d: __import__("settings").test_key(), "/api/subtitles": api_subtitles, "/api/voices/refresh": api_refresh, "/api/sample": api_sample, "/api/regen": api_regen, "/api/linevoice": api_linevoice}


SAMPLE_TEXT = "سلام، این یه نمونهٔ صداست. امروز می‌خوام یه چیز جالب بهت نشون بدم."
