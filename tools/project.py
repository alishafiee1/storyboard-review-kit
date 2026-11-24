# -*- coding: utf-8 -*-
"""The one JSON the page loads: scenes + pictures + audio + speakers + voice settings."""
import datetime, os, re
from kitcore import LANGS, ROOT, STORY, VOICE_LIST, VPROMPTS, read_lines
from story import default_model, parse_prompts, parse_speakers, story_scenes
from media import archived_images, archived_voices, audio_index, audio_url, image_state, refs_triage, scan_inbox, scan_images, scan_refs, scan_videos, video_for
from jobs import JOB
import history, watch


def project():
    import voices
    lines = read_lines(STORY)
    cat = voices.read_catalog()
    dm = default_model(lines)
    images, prompts = scan_images(), parse_prompts()
    vprompts = parse_prompts(read_lines(VPROMPTS)) if os.path.exists(VPROMPTS) else {}
    vids = scan_videos()
    aidx = {lg: audio_index(lg) for lg in LANGS}
    refs = scan_refs(prompts)
    for r in refs:
        r["video"] = video_for(r["name"], vids)
    ref_src = {r["name"]: r["src"] for r in refs}
    ref_vid = {r["name"]: r["video"] for r in refs}
    scenes = []
    for sc in story_scenes(lines):
        for b in sc["blocks"]:
            b["images"] = [dict(im, **image_state(im, images.get(im["id"], {})),
                                prompt=prompts.get(im["id"], {}).get("prompt", ""),
                                vprompt=vprompts.get(im["id"], {}).get("prompt", ""), video=video_for(im["id"], vids), archived=archived_images(im["id"]),
                                refs=[dict(name=n, src=ref_src.get(n), video=ref_vid.get(n)) for n in prompts.get(im["id"], {}).get("refs", [])])
                           for im in b["images"]]
            for it in b["items"]:
                if "id" in it:
                    au = {lg: audio_url(lg, it["id"], sc["voice_pick"], aidx[lg]) for lg in LANGS}
                    it["audio"] = {lg: au[lg][0] for lg in LANGS}
                    it["audio_v"] = {lg: dict(au[lg][1], archived=archived_voices(lg, it["id"])) for lg in LANGS}
        scenes.append(dict(id=sc["id"], title=sc["title"], time=sc["time"], env=sc["env"], issues=sc["issues"],
                           warnings=sc["warnings"], model=sc["model"], fx=sc["fx"], off=sc["off"], voice_stale=sorted(sc["voice_stale"]), blocks=sc["blocks"]))
    placed = {im["id"] for sc in scenes for b in sc["blocks"] for im in b["images"]}
    unplaced = [dict(dict(id=i, prompt=bool(prompts.get(i, {}).get("prompt"))), **image_state(dict(id=i, pick="", status=""), images.get(i, {})))
                for i in sorted((set(images) | set(prompts)) - placed) if re.fullmatch(r"IMG\d{3,4}", i) and (images.get(i) or prompts.get(i, {}).get("prompt"))]  # ids with files or a prompt but no [IMG] marker
    return dict(name=os.path.basename(ROOT), scenes=scenes, unplaced=unplaced, refs=refs, speakers=parse_speakers(lines), voices=VOICE_LIST, inbox=scan_inbox(), triage=refs_triage(), imports=watch.recent_imports(n=20), history=[dict(id=h["id"], label=h["label"], time=h["time"]) for h in history.entries()],
                tts=dict(default=dm, catalog=cat, tones=voices.tones_for_page(), job=JOB, **voices.status()), time=datetime.datetime.now().isoformat(timespec="seconds"))
