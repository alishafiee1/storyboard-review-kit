# -*- coding: utf-8 -*-
"""Reads the file names Flow (and the browser) give to downloads, and groups the files of one picture / one voice line into VERSIONS.
  IMG001_hook_bench_passersby_edfa6fe0_2K.jpg   base IMG001, slug «hook_bench_passersby», rid edfa6fe0, quality 2K
  LOC_FACTORY_YARD_4eb46d68.jpg                 base LOC_FACTORY_YARD, rid 4eb46d68
  IMG018_dna_bookshelf (1).jpg                  «(1)» is the browser's copy counter and is ignored
A version is (base, rid); without a rid it is (base, slug); a bare «IMG018.jpg» is (base, ""). Several qualities of one version are ONE version:
the best file (4K, then 2K, then 1K, then no suffix) is the one shown and exported. Nothing here renames or deletes a file.
The pattern and the quality order can be changed per project in kit-config.json: {"name_pattern": "<regex with named groups base, slug, rid, q>", "quality": ["4K", "2K", "1K"]}."""
import json, math, os, re
from kitcore import ROOT

SKIP_DIRS = ("archive", "_rejected", "inbox")  # folders the recursive scans never read
BASE = r"(?P<base>IMG\d{3,4}|[A-Z]+(?:_(?!\d{8}(?![A-Za-z0-9]))[A-Z0-9]+)+)"  # IMG045, or CH_MIMO / LOC_FACTORY_YARD (an 8-digit tail is a random id, not a name part)
DEFAULT_PATTERN = (BASE + r"(?:_(?P<slug>[^.]*?))??(?:_(?P<rid>(?i:[0-9a-f]{8})))?(?:_(?P<q>(?i:[124]K)))?"
                   r"(?P<dup>\s\(\d+\))?\.(?P<ext>(?i:jpe?g|png|webp))$")
QUALITY = ("4K", "2K", "1K")  # best first; a file without a suffix ranks below all of them
LEGACY_IMG = re.compile(r"(IMG\d{3})(?!\d)")  # old projects: any file name that starts with the id still counts, even when it does not follow the pattern
AUDIO_NAME = re.compile(r"^(?P<stem>.+?)(?P<dup>\s\(\d+\))?\.mp3$", re.I)
AUDIO_RID = re.compile(r"^(?P<id>.+)_(?P<rid>[0-9a-f]{8})$")
_cache = {}


def config():
    """kit-config.json at the project root, or {} (a missing or broken file never stops the page)."""
    try:
        with open(os.path.join(ROOT, "kit-config.json"), encoding="utf-8") as fh:
            c = json.load(fh)
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def settings():
    """(compiled name pattern, quality order best first). A pattern that does not compile falls back to the default."""
    cfg = config()
    src = cfg.get("name_pattern") if isinstance(cfg.get("name_pattern"), str) else DEFAULT_PATTERN
    if src not in _cache:
        try:
            _cache[src] = re.compile(src)
        except re.error:
            _cache[src] = re.compile(DEFAULT_PATTERN)
    q = cfg.get("quality")
    order = tuple(str(x).upper() for x in q) if isinstance(q, list) and all(isinstance(x, str) for x in q) else QUALITY
    return _cache[src], order


def parse(name, cfg=None):
    """File name -> dict(base, slug, rid, q, dup, key, name) or None when it is not a project file. `cfg` = settings() (pass it when parsing many)."""
    pat, _ = cfg or settings()
    m = pat.match(name)
    if not m:
        return None
    g = m.groupdict()
    base, slug, rid = g.get("base") or "", (g.get("slug") or "").strip(), (g.get("rid") or "").lower()
    q = (g.get("q") or "").upper()
    return dict(base=base, slug=slug, rid=rid, q=q, dup=bool(g.get("dup")), key=(base, rid) if rid else (base, slug), name=name)


def quality_rank(q, cfg=None):
    """Smaller is better: 0 = best quality in the order, len(order) = no suffix (or one the order does not know)."""
    order = (cfg or settings())[1]
    return order.index(q) if q in order else len(order)


def batch_of(base):
    """IMG001..IMG010 -> b01, IMG011..IMG020 -> b02, IMG000 -> b00. Anything that is not IMG<number> -> ''."""
    m = re.fullmatch(r"IMG(\d{3,4})", base or "")
    return "b%02d" % math.ceil(int(m.group(1)) / 10) if m else ""


def walk(folder, skip=SKIP_DIRS):
    """Every file under folder (all levels), leaving out archive/, _rejected/ and inbox/. Sorted, so the result does not depend on the disk."""
    out = []
    for d, ds, fs in os.walk(folder):
        ds[:] = sorted(x for x in ds if x not in skip)
        out += [os.path.join(d, f) for f in sorted(fs)]
    return out


def group(files, cfg=None):
    """[(path, parsed)] -> versions, oldest first: dict(key, base, slug, rid, id, files, best, q). `files` = every file of the version (best first),
    `best` = the one to show, `id` = what pick: stores (the rid, or the file name for a version without one)."""
    cfg = cfg or settings()
    by = {}
    for path, p in files:
        by.setdefault(p["key"], []).append((path, p))
    out = []
    for key, fs in by.items():
        # best quality first; of identical files the original beats the browser's « (1)» copy; then the newest
        fs.sort(key=lambda x: (quality_rank(x[1]["q"], cfg), x[1]["dup"], -os.path.getmtime(x[0]), x[0]))
        best_path, best = fs[0]
        out.append(dict(key=key, base=best["base"], slug=best["slug"], rid=best["rid"], q=best["q"], best=best_path, files=[x[0] for x in fs],
                        id=best["rid"] or os.path.basename(best_path), first=min(os.path.getmtime(x[0]) for x in fs)))
    out.sort(key=lambda v: (v["first"], v["best"]))
    return out


def find_version(versions, want):
    """The version a pick: value means. The rid, a version id, or any file name of the version (the old form of pick:). None when nothing fits."""
    want = (want or "").strip()
    if not want:
        return None
    low = want.lower()
    for v in versions:
        if want == v["id"] or low == v["id"].lower():
            return v
    return next((v for v in versions if any(os.path.basename(f) == want for f in v["files"])), None)


def audio_parse(name):
    """Voice file name -> (line id, variant name, dup) or None. IMG045-1_ab12cd34.mp3 -> ('IMG045-1','ab12cd34'); IMG045-1.eleven-v3.mp3 -> ('IMG045-1','eleven-v3');
    IMG045-1.mp3 or the old L007.mp3 -> (id, 'default'). A trailing « (1)» only sets dup."""
    m = AUDIO_NAME.match(name)
    if not m:
        return None
    stem, dup = m.group("stem"), bool(m.group("dup"))
    if "." in stem:
        id_, _, variant = stem.partition(".")
        return (id_, variant, dup) if id_ and variant else None
    r = AUDIO_RID.match(stem)
    return (r.group("id"), r.group("rid"), dup) if r else (stem, "default", dup)
