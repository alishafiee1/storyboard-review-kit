# -*- coding: utf-8 -*-
"""A throw-away project that looks like a real old one («1-mimo-white-head»): Flow-named pictures in part01 / part02, old voice names
(IMG001_1.mp3, IMG003_2.eleven-v3.mp3, L007.mp3), a shared block, scene-level voice-pick, and a Premiere XML with absolute Windows paths.
Used by test_migrate.py and by the browser tests. Nothing here touches a real project."""
import hashlib, os, shutil, struct, subprocess, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))
WIN = "file://localhost/Z%3a/mimo-other-pc/1-mimo-white-head/"  # where the XML was made (another computer; Z: never exists here)
_cache = {}


def png(seed):
    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes([(seed * 37) % 256, (seed * 91) % 256, 80]) * 16 for _ in range(9))
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 16, 9, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


def mp3(seed):
    """A short real mp3 with its own pitch (so two files never share bytes); fake MPEG frames when ffmpeg is not installed."""
    if seed not in _cache:
        data = None
        if shutil.which("ffmpeg"):
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=%d:duration=0.4" % (200 + 23 * seed), "-ac", "1", "-ar", "22050",
                                "-f", "mp3", "-"], capture_output=True)
            data = r.stdout if r.returncode == 0 and r.stdout else None
        _cache[seed] = data or (b"\xff\xfb\x90\x64" + bytes([seed]) * 413) * 10
    return _cache[seed]


# (path, seed): pictures; part01 = IMG000-009, part02 = IMG010+
IMAGES = [("images/scenes/part01/IMG001_hook_bench_passersby_edfa6fe0_2K.jpg", 1)]
IMAGES += [("images/scenes/part01/IMG%03d_%s_%08x_2K.jpg" % (n, name, 0xedfa6fe0 + n), n) for n, name in
           ((2, "bench_close"), (3, "crowd_walks"), (4, "pigeons"), (5, "head_white"), (6, "factory_gate"))]
IMAGES += [("images/scenes/part01/IMG001_hook_bench_passersby_edfa6fe0.jpg", 20), ("images/scenes/part02/IMG010_part_two_1b901f0a_2K.jpg", 30),
           ("images/refs/CH/CH_MIMO_4eb46d68.jpg", 40)]
# voices: old names, in both languages
VOICES = ["IMG001_1.mp3", "IMG001_1.eleven-v3.mp3", "IMG003_1.mp3", "IMG003_2.mp3", "IMG003_2.eleven-v3.mp3", "IMG004_1.mp3", "L007.mp3", "L007.eleven-v3.mp3",
          "IMG010_1.mp3", "archive/IMG001_1.eleven-v4.mp3", "_samples/sample.mp3", "IMG099_1.mp3"]


def xml():
    """The Premiere XML the editor made on another computer: absolute file://localhost/D%3a/... paths, one relative path, CRLF line ends."""
    def clip(i, name, url, kind):
        return ("<clipitem id=\"clipitem-%d\"><name>%s</name><duration>25</duration><file id=\"file-%d\"><name>%s</name><pathurl>%s</pathurl>"
                "<media><%s/></media></file></clipitem>" % (i, name, i, name, url, kind))
    items = [clip(1, "IMG001_hook_bench_passersby_edfa6fe0_2K.jpg", WIN + "images/scenes/part01/IMG001_hook_bench_passersby_edfa6fe0_2K.jpg", "video"),
             clip(2, "IMG001_1.mp3", WIN + "audio/en/IMG001_1.mp3", "audio"),
             clip(3, "IMG003_1.mp3", WIN + "audio/en/IMG003_1.mp3", "audio"),
             clip(4, "IMG003_2.mp3", WIN + "audio/en/IMG003_2.mp3", "audio"),
             clip(5, "IMG003_2.eleven-v3.mp3", WIN + "audio/en/IMG003_2.eleven-v3.mp3", "audio"),
             clip(6, "IMG004_1.mp3", WIN + "audio/en/IMG004_1.mp3", "audio"),
             clip(7, "L007.mp3", WIN + "audio/en/L007.mp3", "audio"),
             clip(8, "IMG001_1.mp3", "../../audio/en/IMG001_1.mp3", "audio"),
             clip(9, "IMG001_1.mp3", "Z:\\mimo-other-pc\\1-mimo-white-head\\audio\\fa\\IMG001_1.mp3", "audio")]
    return ('<?xml version="1.0" encoding="UTF-8"?>\r\n<!DOCTYPE xmeml>\r\n<xmeml version="4"><sequence><name>EP01 EN</name><media>\r\n'
            + "\r\n".join(items) + "\r\n</media></sequence></xmeml>\r\n").encode("utf-8")


def build(root, tools=True):
    """Write the old-style project into `root` (the folder must exist)."""
    if tools:
        shutil.copytree(os.path.join(KIT, "tools"), os.path.join(root, "tools"), ignore=shutil.ignore_patterns("tests", "__pycache__"))
    os.makedirs(os.path.join(root, "scenario"), exist_ok=True)
    shutil.copy2(os.path.join(HERE, "fixture", "mimo-story.txt"), os.path.join(root, "scenario", "story.txt"))
    for rel, seed in IMAGES:
        put(root, rel, png(seed))
    for i, name in enumerate(VOICES):
        for lg in ("fa", "en"):
            if lg == "en" and name in ("IMG010_1.mp3", "archive/IMG001_1.eleven-v4.mp3"):
                continue
            put(root, "audio/%s/%s" % (lg, name), mp3(i * 2 + (lg == "en") + 1))
    put(root, "videos/final/EP01_EN_premiere.xml", xml())
    put(root, "videos/final/notes.xml", b"<notes>no media here</notes>\n")


def put(root, rel, data):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data)


def snapshot(root, skip=(".kit", ".engine-backup", ".git", "tools")):
    """{relative path: sha1} of every file (the folders in `skip` left out): equal snapshots = byte-for-byte equal projects."""
    out = {}
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if not (os.path.relpath(os.path.join(d, x), root) in skip)]
        for f in fs:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root).replace("\\", "/")] = hashlib.sha1(fh.read()).hexdigest()
    return out


RESOLVE = r"""
import sys, json, hashlib, os
sys.path.insert(0, 'tools')
import project
out = []
for sc in project.project()['scenes']:
    for b in sc['blocks']:
        for it in b['items']:
            if it['k'] == 'say':
                row = {'img': it['img'], 'fa': it['fa'][:12]}
                for lg in ('fa', 'en'):
                    u = it['audio'][lg]
                    row[lg] = hashlib.sha1(open(u.split('?')[0], 'rb').read()).hexdigest()[:10] if u else None
                    row[lg + '_n'] = len(it['audio_v'][lg]['names'])
                out.append(row)
print(json.dumps(out))
"""
