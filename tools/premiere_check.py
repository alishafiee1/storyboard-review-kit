# -*- coding: utf-8 -*-
"""Checks an editor-package XML (Premiere / FCP7 xmeml): every media file it points to must exist.
Paths in the XML are written relative to the XML's own folder («../images/scenes/IMG001.jpg», «./media/overlays/a.mov»);
an absolute path (D:\\..., file://localhost/...) still works but is reported, because it breaks on the editor's computer.
  python tools/premiere_check.py [file.xml ...]      (no argument: every *premiere*.xml in the project)
Exit code 1 when a file is missing."""
import glob, os, re, sys, urllib.parse
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_absolute(url):
    u = url.strip()
    return u.startswith("file:") or bool(re.match(r"^[A-Za-z]:[\\/]", u)) or u.startswith(("/", "\\"))


def resolve(url, base):
    """The local path a pathurl means. Relative ones are taken from the XML's folder."""
    u = url.strip()
    if u.startswith("file:"):
        p = urllib.parse.unquote(urllib.parse.urlparse(u).path)
        return p[1:] if re.match(r"^/[A-Za-z]:", p) else p
    return os.path.normpath(os.path.join(base, urllib.parse.unquote(u)))


def check(xml_path):
    """{'total': n, 'missing': [path], 'absolute': [url]} for the files this XML uses (each file counted once)."""
    base = os.path.dirname(os.path.abspath(xml_path))
    urls = []
    for el in ET.parse(xml_path).getroot().iter("pathurl"):
        if el.text and el.text.strip() and el.text.strip() not in urls:
            urls.append(el.text.strip())
    paths = {u: resolve(u, base) for u in urls}
    return dict(total=len(urls), missing=[p for p in paths.values() if not os.path.exists(p)], absolute=[u for u in urls if is_absolute(u)], paths=list(paths.values()))


def find_xmls():
    out = [f for f in glob.glob(os.path.join(ROOT, "**", "*premiere*.xml"), recursive=True)
           if not any(x in f.replace("\\", "/") for x in ("/.git/", "/.engine-backup/", "/graphify-out/"))]
    return sorted(out)


def report(xml_path):
    r = check(xml_path)
    name = os.path.relpath(xml_path, ROOT)
    print("%s: %d files used, %d missing, %d with an absolute path" % (name, r["total"], len(r["missing"]), len(r["absolute"])))
    for m in r["missing"][:20]:
        print("  ✗ missing:", m)
    if r["absolute"]:
        print("  ⚠ absolute paths break on another computer (first one: %s)" % r["absolute"][0])
    return r


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    xmls = sys.argv[1:] or find_xmls()
    if not xmls:
        sys.exit("no Premiere XML found")
    bad = 0
    for x in xmls:
        bad += len(report(x)["missing"])
    print("OK: every file is there" if not bad else "FAILED: %d file(s) missing" % bad)
    sys.exit(1 if bad else 0)
