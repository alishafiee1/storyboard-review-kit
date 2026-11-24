# -*- coding: utf-8 -*-
"""One copy-ready text with the prompts of a whole batch (IMG041..IMG050 = b05):
  python tools/batch.py b05          prints it (warnings about missing reference files go to stderr)
For every picture of the batch that is in story.txt or prompts.txt, in number order: a header «=== IMG045 ===», its «[REFS TO ATTACH: ...]» line with the real file names
of the references on disk, the prompt text, and «Output name: IMG045_<slug>» (the «[OUTPUT NAME: ...]» of the prompt, else the slug of the versions already on disk).
GET /api/batch?b=b05 returns the same text."""
import os, re, sys
from kitcore import MARKER, STORY, read_lines
from flowname import batch_of, output_slug, parse, settings
from story import parse_prompts
from media import scan_images, scan_refs

REFS_LINE = re.compile(r"^\[REFS TO ATTACH:[^\]]*\]\s*\n?")


def batch_ids(b, prompts, lines):
    ids = {m.group(1) for m in (MARKER.match(l.strip()) for l in lines) if m} | {k for k in prompts if re.fullmatch(r"IMG\d{3,4}", k)}
    return sorted((i for i in ids if batch_of(i) == b), key=lambda i: (int(i[3:]), i))


def batch_text(b):
    """dict(batch, ids, text, missing): `missing` = reference names with no file and pictures with no prompt."""
    if not re.fullmatch(r"b\d{2,3}", b or ""):
        raise ValueError("bad batch (like b05)")
    prompts, lines, cfg = parse_prompts(), read_lines(STORY), settings()
    ids = batch_ids(b, prompts, lines)
    refs = {r["name"]: os.path.basename(r["src"]) for r in scan_refs(prompts)}
    scans, missing, blocks = scan_images(), [], []
    for id_ in ids:
        pr = prompts.get(id_, {"prompt": "", "refs": []})
        names = []
        for r in pr["refs"]:
            if r not in refs:
                missing.append(r)
            names.append(refs.get(r, r))
        body = REFS_LINE.sub("", pr["prompt"]).strip()
        slug = output_slug(pr["prompt"], id_)
        if slug is None:
            slug = next((p["slug"] for v in reversed(scans.get(id_, {}).get("versions", [])) for p in [parse(v["name"], cfg)] if p and p["slug"]), "")
        if not body:
            missing.append(id_ + " (no prompt)")
        blocks.append("\n".join(["=== %s ===" % id_] + (["[REFS TO ATTACH: " + "| ".join(names) + "]"] if names else []) + ([body] if body else [])
                                + ["Output name: " + id_ + ("_" + slug if slug else "")]))
    return dict(batch=b, ids=ids, text="\n\n".join(blocks) + ("\n" if blocks else ""), missing=sorted(set(missing)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        sys.exit("Usage: python tools/batch.py b05")
    try:
        r = batch_text(sys.argv[1])
    except ValueError as e:
        sys.exit(str(e))
    print(r["text"], end="")
    for m in r["missing"]:
        print("warning: no file / prompt for " + m, file=sys.stderr)
