# -*- coding: utf-8 -*-
"""A simple Premiere / Final Cut 7 timeline (xmeml) made from the story order: one still per picture, one audio track with the chosen voices.
  python tools/premiere_export.py [--lang fa|en] [--absolute] [--fps 25] [-o out.xml]
Every picture that is not set aside (off; the thumbnail IMG000 never counts) is a still: the picked version at its best quality (media.resolve), as long as the sum of its dialogue
voices (the voice file's own length; a line without a voice file counts by its text, about 2.5 words a second; a picture without dialogue 3 s).
The voices (the chosen variant of each line in --lang) go to one audio track, each starting where its picture starts, one after the other.
Paths are relative to the XML's folder by default (they survive moving the project); --absolute writes file://localhost/... paths.
Default output: videos/final/premiere_<lang>.xml. `python tools/premiere_check.py` checks the result.
Note for projects that have their own tools/export_premiere.py: this engine file has another name (premiere_export.py) on purpose, so an update never replaces yours."""
import argparse, os, re, struct, sys, urllib.parse
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kitcore import ROOT, STORY, read_lines  # noqa: E402
from media import audio_index, resolve, scan_images  # noqa: E402
from story import clean_spoken, story_scenes  # noqa: E402

STILL_DEFAULT, WORDS_PER_SEC = 3.0, 2.5
BITRATES = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320], 2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def mp3_seconds(path):
    """Length of an mp3 in seconds, read from its frame headers (no other tool needed). None when the file has no readable frames."""
    try:
        data = open(path, "rb").read()
    except OSError:
        return None
    i = 0
    if data[:3] == b"ID3" and len(data) > 10:
        i = 10 + ((data[6] & 127) << 21 | (data[7] & 127) << 14 | (data[8] & 127) << 7 | (data[9] & 127))
    total, frames = 0.0, 0
    while i + 4 <= len(data):
        h = struct.unpack(">I", data[i:i + 4])[0]
        ver, layer, br, sr = (h >> 19) & 3, (h >> 17) & 3, (h >> 12) & 15, (h >> 10) & 3
        if (h >> 21) != 0x7FF or ver == 1 or layer != 1 or br in (0, 15) or sr == 3:
            i += 1
            continue
        mpeg1 = ver == 3
        rate = RATES[ver][sr]
        size = int((144 if mpeg1 else 72) * BITRATES[1 if mpeg1 else 2][br] * 1000 / rate + ((h >> 9) & 1))
        total += (1152 if mpeg1 else 576) / rate
        frames += 1
        i += max(size, 4)
    return total if frames else None


def estimate(text):
    """Seconds a text takes to read aloud when there is no voice file: about 2.5 words a second, at least one second."""
    return max(1.0, len(re.findall(r"\S+", clean_spoken(text))) / WORDS_PER_SEC)


def path_url(path, xml_dir, absolute):
    """The <pathurl> text of a file: relative to the XML's folder (default) or file://localhost/<drive>/... (the form Premiere itself writes)."""
    if not absolute:
        return urllib.parse.quote(os.path.relpath(path, xml_dir).replace("\\", "/"), safe="/")
    p = os.path.abspath(path).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):(/.*)$", p)
    return "file://localhost/" + ((m.group(1) + "%3a" + urllib.parse.quote(m.group(2), safe="/")) if m else urllib.parse.quote(p.lstrip("/"), safe="/"))


def timeline(lang):
    """[{id, name, image: path|None, start, dur (seconds), voices: [{id, path, start, dur}]}] in story order, pictures set aside left out."""
    scan, idx, out, t = scan_images(), audio_index(lang), [], 0.0
    for sc in story_scenes(read_lines(STORY)):
        if sc["off"]:
            continue
        for b in sc["blocks"]:
            for im in b["images"]:
                if im["off"] or re.fullmatch(r"IMG0+", im["id"]):  # set aside, or the thumbnail picture (IMG000): not part of the film
                    continue
                voices, at = [], t
                for it in b["items"]:
                    if it["k"] != "say":
                        continue
                    v = resolve("voice", it["id"], sc["voice_pick"].get(f"{it['id']}.{lang}", ""), lang, idx=idx)
                    text = it["fa"] if lang == "fa" else it["en"]
                    dur = (mp3_seconds(v["path"]) if v else None) or (estimate(text) if clean_spoken(text or "") else 0.0)
                    if v:
                        voices.append(dict(id=it["id"], path=v["path"], start=at, dur=dur))
                    at += dur
                pic = resolve("image", im["id"], im["pick"], scan=scan)
                out.append(dict(id=im["id"], image=pic["path"] if pic else None, start=t, dur=(at - t) or STILL_DEFAULT, voices=voices))
                t += (at - t) or STILL_DEFAULT
    return out


def frames(sec, fps):
    return int(round(sec * fps))


def clip(n, name, url, start, dur, fps, kind):
    f, d = frames(start, fps), max(1, frames(dur, fps))
    media = "<video><samplecharacteristics><width>1920</width><height>1080</height></samplecharacteristics></video>" if kind == "video" else \
        "<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics><channelcount>1</channelcount></audio>"
    still = "<stillframe>TRUE</stillframe>" if kind == "video" else ""
    return ("<clipitem id=\"clipitem-%d\"><name>%s</name><duration>%d</duration><rate><timebase>%d</timebase></rate><start>%d</start><end>%d</end><in>0</in><out>%d</out>%s"
            "<file id=\"file-%d\"><name>%s</name><pathurl>%s</pathurl><rate><timebase>%d</timebase></rate><duration>%d</duration><media>%s</media></file></clipitem>"
            % (n, escape(name), d, fps, f, f + d, d, still, n, escape(name), escape(url), fps, d, media))


def build(lang="fa", absolute=False, fps=25, out=None):
    """Write the xmeml file. Returns (path, [warnings])."""
    out = out or os.path.join(ROOT, "videos", "final", "premiere_%s.xml" % lang)
    xdir = os.path.dirname(os.path.abspath(out))
    tl, warns, n = timeline(lang), [], 0
    vid, aud, end = [], [], 0.0
    for e in tl:
        end = max(end, e["start"] + e["dur"])
        if e["image"]:
            n += 1
            vid.append(clip(n, os.path.basename(e["image"]), path_url(e["image"], xdir, absolute), e["start"], e["dur"], fps, "video"))
        else:
            warns.append("%s has no picture file: left out of the video track" % e["id"])
        for v in e["voices"]:
            n += 1
            aud.append(clip(n, os.path.basename(v["path"]), path_url(v["path"], xdir, absolute), v["start"], v["dur"], fps, "audio"))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">\n<sequence id="sequence-1"><name>%s %s</name><duration>%d</duration>'
           '<rate><timebase>%d</timebase></rate><media>\n<video><format><samplecharacteristics><width>1920</width><height>1080</height></samplecharacteristics></format>\n'
           '<track>\n%s\n</track></video>\n<audio><track>\n%s\n</track></audio>\n</media></sequence>\n</xmeml>\n'
           % (escape(os.path.basename(ROOT)), lang.upper(), frames(end, fps), fps, "\n".join(vid), "\n".join(aud)))
    os.makedirs(xdir, exist_ok=True)
    open(out, "w", encoding="utf-8", newline="\n").write(xml)
    return out, warns


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", choices=("fa", "en"), default="fa")
    ap.add_argument("--absolute", action="store_true", help="absolute file://localhost/ paths instead of paths relative to the XML")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    path, warns = build(a.lang, a.absolute, a.fps, a.out)
    for w in warns:
        print("⚠", w)
    print("written:", os.path.relpath(path, ROOT))
