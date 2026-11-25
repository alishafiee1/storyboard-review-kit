# -*- coding: utf-8 -*-
"""The page's write API: one small function per endpoint, registered with @route. Each runs under the file lock and may raise
ValueError (-> 400) or Conflict (-> 409); returning nothing means {"ok": true}."""
import os, re
import history, settings
from kitcore import LANGS, MARKS, MODEL_RE, PROMPTS, STORY, VPROMPTS, read_lines, write_lines
from story import clean_name, clean_tone, ensure_speaker, parse_prompts, parse_speakers, scene_ranges, story_scenes
from media import archive_item, audio_variants, find_version, scan_images, scan_refs
from edits import add_image, add_scene, mark_stale, move_scene, patch_image, set_default_model, set_flag, set_line_pick, set_scene_fx, set_scene_off, set_stale, speech_scenes
from moves import add_image_at, move_images, scene_mark
from lineedits import add_issue, add_line, clear_issue, delete_line, edit_line, locate
from promptedits import replace_prompt, set_prompt_refs, upsert_prompt

ROUTES = {}
STRUCTURAL = set()  # endpoints that change the structure of story.txt: a snapshot is kept before each (see history.py)


def route(*paths, snapshot=False):
    def reg(fn):
        for p in paths:
            ROUTES[p] = fn
            if snapshot:
                STRUCTURAL.add(p)
        return fn
    return reg


def handle(path, d):
    """Run the endpoint for `path` (the caller already holds the file lock). Returns the JSON answer."""
    fn = ROUTES.get(path)
    if fn is None:
        raise ValueError("unknown endpoint")
    before = history.read_story() if path in STRUCTURAL else None
    res = fn(d)
    if path in STRUCTURAL:
        history.record(path.rsplit("/", 1)[-1], before)  # only when the edit succeeded and really changed the file
    return {"ok": True} if res is None else res


@route("/api/settings")
def settings_save(d):
    """change the key / the Downloads folder / the watcher switch (only the fields sent); answers the new state, never the key"""
    return settings.save(d)


@route("/api/undo")
def undo(d):
    """put story.txt back as it was before the last structural edit (byte for byte); `id` = the snapshot the page thinks is the newest, `force` = even if the file changed since"""
    return dict(ok=True, undone=history.undo(str(d["id"]) if d.get("id") else None, bool(d.get("force"))))


@route("/api/image")
def image(d):
    """one picture: status, note, edit advice (fx), stale flag, chosen version (pick), set aside (off)"""
    id_ = str(d["id"])
    if not re.fullmatch(r"IMG\d{3,4}", id_) or str(d.get("status", "")) not in MARKS:
        raise ValueError("bad id or status")
    lines = read_lines(STORY)
    pick, status = d.get("pick"), d.get("status")
    if pick is not None:
        pick = str(pick)
        v = find_version(scan_images().get(id_, {}).get("versions", []), pick) if pick else None
        if pick and not v:
            raise ValueError("no such picture file")
        if pick:
            pick = v["id"]  # the random id (or, for a version without one, the file name); a better quality file of it later changes nothing
            status = ""  # choosing a picture approves it (and clears an old «redo»)
    patch_image(lines, id_, status, None if d.get("note") is None else str(d["note"])[:4000], d.get("stale"),
                None if d.get("fx") is None else str(d["fx"])[:2000], pick, None if d.get("off") is None else bool(d["off"]))
    write_lines(STORY, lines)


@route("/api/voicepick")
def voicepick(d):
    """the voice variant the user listened to and chose for one line (found by its id; an old request may also carry the scene, which is ignored)"""
    id_, lang, variant = str(d["id"]), str(d["lang"]), str(d.get("variant", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", id_) or lang not in LANGS:
        raise ValueError("bad id or lang")
    if variant and variant not in [v["name"] for v in audio_variants(lang, id_)]:
        raise ValueError("no such voice file")
    lines = read_lines(STORY)
    if not set_line_pick(lines, id_, lang, variant):
        raise ValueError("no such dialogue line")
    write_lines(STORY, lines)


@route("/api/archive")
def archive(d):
    """move a picture version or a voice to the archive folder; a chosen one loses its pick"""
    return _archive_or_restore(d, back=False)


@route("/api/restore")
def restore(d):
    """bring an archived picture version or voice back"""
    return _archive_or_restore(d, back=True)


def _archive_or_restore(d, back):
    kind, id_, name, lang = str(d["kind"]), str(d["id"]), str(d["name"]), str(d.get("lang", ""))
    vs = scan_images().get(id_, {}).get("versions", []) if kind == "image" and not back else []
    gone = find_version(vs, name)  # the version that is about to leave (all its quality files go together)
    archive_item(kind, id_, name, lang, back)
    if not back:
        lines = read_lines(STORY)
        if kind == "image":
            im = next((x for sc in story_scenes(lines) for b in sc["blocks"] for x in b["images"] if x["id"] == id_), None)
            if im and im["pick"] and gone and find_version([gone], im["pick"]):
                patch_image(lines, id_, pick="")
                write_lines(STORY, lines)
        else:
            sc = next((s for s in story_scenes(lines) if any(it.get("id") == id_ for b in s["blocks"] for it in b["items"])), None)
            if sc and sc["voice_pick"].get(f"{id_}.{lang}") == name:
                set_line_pick(lines, id_, lang, "")
                write_lines(STORY, lines)


@route("/api/sceneoff", snapshot=True)
def sceneoff(d):
    """set a scene aside or bring it back (off: yes)"""
    sid = str(d["scene"])
    if not re.fullmatch(r"scene-\d{2,3}", sid):
        raise ValueError("bad scene")
    lines = read_lines(STORY)
    set_scene_off(lines, sid, bool(d["off"]))
    write_lines(STORY, lines)


@route("/api/scenemove", snapshot=True)
def scenemove(d):
    """move a scene one place up or down (only the block moves)"""
    sid = str(d["scene"])
    if not re.fullmatch(r"scene-\d{2,3}", sid):
        raise ValueError("bad scene")
    lines = read_lines(STORY)
    move_scene(lines, sid, -1 if int(d["step"]) < 0 else 1)
    write_lines(STORY, lines)


@route("/api/addscene", snapshot=True)
def addscene(d):
    """new scene with 0 to 12 empty picture slots, after a given scene"""
    after = str(d.get("after", ""))
    if after and not re.fullmatch(r"scene-\d{2,3}", after):
        raise ValueError("bad scene")
    lines = read_lines(STORY)
    sid = add_scene(lines, after, d.get("title", ""), d.get("images", 1))
    write_lines(STORY, lines)
    return {"ok": True, "scene": sid}


@route("/api/addimage", snapshot=True)
def addimage(d):
    """one more empty picture slot: at the end of a scene {scene}, or right {after: IMG} / {before: IMG} a picture; {id: IMG045} places a picture id
    that has files or a prompt but no marker yet (409 when it already has one)"""
    anchors = [k for k in ("after", "before") if d.get(k)]
    if len(anchors) + bool(d.get("scene")) != 1:
        raise ValueError("دقیقاً یکی از scene و after و before لازم است")
    lines = read_lines(STORY)
    if anchors:
        iid = add_image_at(lines, before=d.get("before"), after=d.get("after"), image_id=d.get("id"))
    else:
        sid = str(d["scene"])
        if not re.fullmatch(r"scene-\d{2,3}", sid):
            raise ValueError("bad scene")
        if d.get("id"):
            if not any(r[0] == sid for r in scene_ranges(lines)):
                raise ValueError("scene not found")
            iid = add_image_at(lines, scene=sid, image_id=d["id"])
        else:
            iid = add_image(lines, sid)
    write_lines(STORY, lines)
    return {"ok": True, "id": iid}


@route("/api/move", snapshot=True)
def move(d):
    """move one or several pictures (their [IMG] line and all that belongs to it) {ids:[IMG..]} to just {before: IMG} / {after: IMG} a picture or
    {to_end_of_scene: scene-id}, also across scene headers; they keep their order in the file; onto itself changes nothing; 409 when a picture
    or scene is not in the file any more"""
    ids = d.get("ids", [d["id"]] if d.get("id") else [])
    if not isinstance(ids, list):
        raise ValueError("ids must be a list")
    lines = read_lines(STORY)
    scene = move_images(lines, ids, before=d.get("before"), after=d.get("after"), to_end=d.get("to_end_of_scene"))
    if scene is None:
        return {"ok": True, "moved": 0}
    write_lines(STORY, lines)
    return {"ok": True, "moved": len(ids), "scene": scene}


@route("/api/scenemark", snapshot=True)
def scenemark(d):
    """the scene markers: op=insert {before: IMG, title, env?} starts a new scene at that picture; op=remove {scene, force?} deletes only the
    header so its pictures join the previous scene; op=edit {scene, title?, env?, fx?}"""
    lines = read_lines(STORY)
    res = scene_mark(lines, str(d.get("op", "")), d)
    write_lines(STORY, lines)
    return dict(res, ok=True)


@route("/api/flag")
def flag(d):
    """mark the voice (fa / en) of one dialogue line (by id) as out of date or up to date; the old form with a scene marks every line of it"""
    if d["lang"] not in LANGS:
        raise ValueError("bad lang")
    lines = read_lines(STORY)
    if d.get("id"):
        set_stale(lines, str(d["id"]), [d["lang"]], bool(d["value"]))
    elif re.fullmatch(r"scene-\d{2,3}", str(d.get("scene", ""))):
        set_flag(lines, d["scene"], d["lang"], bool(d["value"]))
    else:
        raise ValueError("bad id or scene")
    write_lines(STORY, lines)


@route("/api/line")
def line(d):
    """change the text, speaker or tone of one line: {image, index} (index counted from the [IMG] line), or the old {scene, index}"""
    lines = read_lines(STORY)
    sid, idx = locate(lines, d)
    edit_line(lines, sid, idx, d.get("old", ""), d["new"], d.get("op", "edit"))
    write_lines(STORY, lines)


@route("/api/add", snapshot=True)
def add(d):
    """add a dialogue or action line after a given line: {image, after} (counted from the [IMG] line), or the old {scene, after}"""
    lines = read_lines(STORY)
    sid, after = locate(lines, d, "after")
    add_line(lines, sid, after, d["kind"], d.get("speaker", ""), d["text"], d.get("label", ""), d.get("tone", ""))
    write_lines(STORY, lines)


@route("/api/speaker")
def speaker(d):
    """create or change a speaker (colour, voice, default tone)"""
    name = clean_name(d["name"])
    color, voice = d.get("color"), d.get("voice")
    if color is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(color)):
        raise ValueError("bad color")
    if voice is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{0,60}", str(voice)):
        raise ValueError("bad voice")
    tone = d.get("tone")
    tone = None if tone is None else clean_tone(tone)
    lines = read_lines(STORY)
    before = next((x["voice"] for x in parse_speakers(lines) if x["name"] == name), None)
    ensure_speaker(lines, name, color, voice, tone)
    if voice and before is not None and voice != before:  # another voice = every line of this speaker must be made again
        mark_stale(lines, speaker=name)
    write_lines(STORY, lines)


@route("/api/ttsmodel")
def ttsmodel(d):
    """set the default model (a scene-level «model:» line in an old story.txt is still read, but no longer written)"""
    model = str(d.get("model", "")).strip()
    if not model or not MODEL_RE.fullmatch(model):
        raise ValueError("bad model")
    lines = read_lines(STORY)
    set_default_model(lines, model)
    mark_stale(lines, speech_scenes(lines, own_model=False))
    write_lines(STORY, lines)


@route("/api/voicetest")
def voicetest(d):
    """what you heard in audio/_tests/index.html: a voice, a tone, or the model's tag support"""
    import voices
    voices.mark_test(model=str(d.get("model", "")), voice=d.get("voice") or None, tone=d.get("tone") or None,
                     result=str(d.get("result", "")), tags=d.get("tags"))


@route("/api/delete", snapshot=True)
def delete(d):
    """delete one dialogue / action / translation line: {image, index} or the old {scene, index}"""
    lines = read_lines(STORY)
    sid, idx = locate(lines, d)
    delete_line(lines, sid, idx, d.get("old", ""))
    write_lines(STORY, lines)


@route("/api/issue")
def issue(d):
    """add or clear a format-issue note on a line: {image, index} or the old {scene, index}"""
    lines = read_lines(STORY)
    sid, idx = locate(lines, d)
    if d.get("clear"):
        clear_issue(lines, sid, idx)
    else:
        add_issue(lines, sid, idx, d.get("message", ""))
    write_lines(STORY, lines)


@route("/api/scenefx")
def scenefx(d):
    """edit advice (fx) of a whole scene"""
    if not re.fullmatch(r"scene-\d{2,3}", str(d["scene"])):
        raise ValueError("bad scene")
    lines = read_lines(STORY)
    set_scene_fx(lines, d["scene"], str(d.get("fx", ""))[:2000])
    write_lines(STORY, lines)


@route("/api/vprompt")
def vprompt(d):
    """save the image-to-video prompt of a picture"""
    id_ = str(d["id"])
    if not re.fullmatch(r"IMG\d{3,4}", id_):
        raise ValueError("bad id")
    lines = read_lines(VPROMPTS) if os.path.exists(VPROMPTS) else [
        "# پرامپت‌های ویدیو (تصویر به ویدیو). هر بلوک با «=== IMG### ===» شروع می‌شه و کامل و مستقل است؛ تصویر همان شناسه، فریم اول ویدیوست.", ""]
    upsert_prompt(lines, id_, str(d.get("old", "")), str(d["new"]))
    write_lines(VPROMPTS, lines)


@route("/api/refs")
def refs(d):
    """attach / detach reference pictures of one shot (edits the top line of its prompt)"""
    id_ = str(d["id"])
    names = [str(n) for n in d["refs"]]
    if not re.fullmatch(r"IMG\d{3,4}", id_) or len(names) > 12 or len(set(names)) != len(names) or not all(re.fullmatch(r"[A-Za-z0-9_]+", n) for n in names):
        raise ValueError("bad id or reference names")
    lines = read_lines(PROMPTS)
    pr = parse_prompts(lines)
    known = {r["name"] for r in scan_refs(pr)} | {n for rec in pr.values() for n in rec["refs"]}  # a reference picture on disk, or one another prompt already uses
    if any(n not in known for n in names):
        raise ValueError("no such reference picture")
    if set_prompt_refs(lines, id_, names):
        write_lines(PROMPTS, lines)
        sl = read_lines(STORY)
        try:
            patch_image(sl, id_, stale=True)  # the picture was made with the old references
            write_lines(STORY, sl)
        except ValueError:
            pass


@route("/api/prompt")
def prompt(d):
    """save the image prompt of a picture or reference"""
    id_ = str(d["id"])
    if not re.fullmatch(r"[A-Za-z0-9_]+", id_):
        raise ValueError("bad id")
    lines = read_lines(PROMPTS)
    changed = replace_prompt(lines, id_, str(d["old"]), str(d["new"]))
    write_lines(PROMPTS, lines)
    if changed and re.fullmatch(r"IMG\d{3,4}", id_):  # the picture was made from the old prompt
        sl = read_lines(STORY)
        try:
            patch_image(sl, id_, stale=True)
            write_lines(STORY, sl)
        except ValueError:
            pass
