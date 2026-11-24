# -*- coding: utf-8 -*-
"""Checks an editor-package XML (Premiere / FCP7 xmeml): every media file it points to must exist.
Paths in the XML are written relative to the XML's own folder («../images/scenes/IMG001.jpg», «./media/overlays/a.mov»);
an absolute path (D:\\..., file://localhost/...) still works but is reported, because it breaks on the editor's computer.
  python tools/premiere_check.py [file.xml ...]      (no argument: every *premiere*.xml in the project)
  python tools/premiere_check.py --fix [file.xml ...]   first repair the paths of files that were renamed (by tools/migrate.py), using .kit/renames.tsv
Exit code 1 when a file is missing."""
import glob, os, re, shutil, sys, time, urllib.parse
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


PATHURL = re.compile(rb"(<pathurl>)(.*?)(</pathurl>)", re.S)
RENAMES = os.path.join(ROOT, ".kit", "renames.tsv")  # time <TAB> old path <TAB> new path (project-relative, forward slashes), one line per renamed file


def read_renames(root=None, time_=None):
    """{old: new} from .kit/renames.tsv in file order; a file renamed twice (A->B, B->C) maps A->C. `time_` = only the rows of that migration."""
    path = os.path.join(root or ROOT, ".kit", "renames.tsv")
    out = {}
    try:
        rows = [l.rstrip("\r").split("\t") for l in open(path, encoding="utf-8").read().split("\n") if l.strip() and not l.startswith("#")]
    except OSError:
        return out
    for r in rows:
        if len(r) == 3 and (time_ is None or r[0] == time_):
            for k, v in out.items():
                if v == r[1]:
                    out[k] = r[2]
            out[r[1]] = r[2]
    return out


def rewrite_pathurls(data, xml_dir, renames, root=None, only_missing=False):
    """(new bytes, [(old text, new text)]): every <pathurl> that points at a renamed file gets the new file name; every other byte is kept as it was.
    `renames` = {old project-relative path: new path in the same folder}. A path matches when it ends with the old relative path («.../1-mimo/audio/en/IMG001_1.mp3»,
    also as file://localhost/D%3a/... or D:\\...) or when, taken from the XML's folder, it is that file. With only_missing a path whose file exists is left alone."""
    root = root or ROOT
    by_base = {}
    for old, new in renames.items():
        if os.path.dirname(old) == os.path.dirname(new):
            by_base.setdefault(os.path.basename(old).lower(), []).append((old, new))
    changes = []

    def one(m):
        raw = m.group(2).decode("utf-8", "surrogateescape")
        text = raw.strip()
        norm = urllib.parse.unquote(text).replace("\\", "/")
        cands = by_base.get(norm.rsplit("/", 1)[-1].lower())
        if not cands:
            return m.group(0)
        local = norm if is_absolute(text) else os.path.normpath(os.path.join(xml_dir, norm))
        hit = next((c for c in cands if norm.lower().endswith("/" + c[0].lower()) or norm.lower() == c[0].lower()
                    or os.path.normcase(os.path.normpath(local)) == os.path.normcase(os.path.normpath(os.path.join(root, c[0])))), None)
        if hit is None or (only_missing and os.path.exists(resolve(text, xml_dir))):
            return m.group(0)
        cut = max(text.rfind("/"), text.rfind("\\")) + 1
        last, old_b, new_b = text[cut:], os.path.basename(hit[0]), os.path.basename(hit[1])
        quoted = urllib.parse.quote(old_b) != old_b and last == urllib.parse.quote(old_b)
        if last != old_b and not quoted and last.lower() != urllib.parse.quote(old_b).lower():
            return m.group(0)
        new_text = text[:cut] + (urllib.parse.quote(new_b) if quoted else new_b)
        changes.append((text, new_text))
        return m.group(1) + raw.replace(text, new_text, 1).encode("utf-8", "surrogateescape") + m.group(3)
    return PATHURL.sub(one, data), changes


def fix(xml_path):
    """Repair one XML with .kit/renames.tsv (a copy of the old file goes to .engine-backup/premiere-fix-<time>/ first). Returns the number of paths changed."""
    renames = read_renames()
    data = open(xml_path, "rb").read()
    new, changes = rewrite_pathurls(data, os.path.dirname(os.path.abspath(xml_path)), renames, only_missing=True)
    if changes:
        bak = os.path.join(ROOT, ".engine-backup", "premiere-fix-" + time.strftime("%Y%m%d-%H%M%S"), os.path.relpath(xml_path, ROOT))
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        shutil.copy2(xml_path, bak)
        open(xml_path, "wb").write(new)
    print("%s: %d path(s) repaired from .kit/renames.tsv (%d renames known)" % (os.path.relpath(xml_path, ROOT), len(changes), len(renames)))
    return len(changes)


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
    args = [a for a in sys.argv[1:] if a != "--fix"]
    xmls = args or find_xmls()
    if not xmls:
        sys.exit("no Premiere XML found")
    if "--fix" in sys.argv:
        for x in xmls:
            fix(x)
    bad = 0
    for x in xmls:
        bad += len(report(x)["missing"])
    print("OK: every file is there" if not bad else "FAILED: %d file(s) missing" % bad)
    sys.exit(1 if bad else 0)
