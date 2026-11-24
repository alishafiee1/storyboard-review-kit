# -*- coding: utf-8 -*-
"""Unit tests of v1.21: tools/watch.py (Downloads -> bNN / refs/<KIND>), the batch text (tools/batch.py), odd files in images/refs/, the inbox listing, and files the
user puts into the folders by hand. Everything runs in throw-away folders. Run:  python -m unittest discover -s tools/tests -p "test_*.py" """
import errno, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))

import flowname  # noqa: E402
import watch  # noqa: E402

STORY = """=== scene-01 | One | 0:00-0:10 ===
[IMG001]
say: A | hello
[IMG045]
[IMG046]
=== scene-02 | Two | 0:10-0:20 ===
[IMG041]
[IMG050]
[IMG051]
"""
PROMPTS = """=== IMG001 ===
[REFS TO ATTACH: STYLE_ANCHOR| CH_MIMO]
Prompt one.

=== IMG045 ===
[REFS TO ATTACH: STYLE_ANCHOR| LOC_CAVE| CH_NOFILE]
[OUTPUT NAME: IMG045_cave_wall]
Prompt of the cave wall.

=== IMG046 ===
Prompt 46 without refs.

=== IMG041 ===
[REFS TO ATTACH: CH_MIMO]
Prompt 41.

=== IMG050 ===
Prompt 50.

=== CH_MIMO ===
The hero.

=== LOC_NEWPLACE ===
A place with no picture yet.
"""


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srk-intake-")
        self.root = os.path.join(self.tmp, "proj")
        self.dl = os.path.join(self.tmp, "Downloads")
        os.makedirs(self.dl)
        write(os.path.join(self.root, "scenario", "story.txt"), STORY)
        write(os.path.join(self.root, "prompts", "prompts.txt"), PROMPTS)
        write(os.path.join(self.root, "images", "refs", "CH", "CH_MIMO_4eb46d68.jpg"), b"mimo")
        write(os.path.join(self.root, "images", "refs", "LOC", "LOC_CAVE_11112222.jpg"), b"cave")
        write(os.path.join(self.root, "images", "scenes", "b01", "IMG001_hook_bench_edfa6fe0_2K.jpg"), b"one")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, name, data=b"x"):
        write(os.path.join(self.dl, name), data)
        return os.path.join(self.dl, name)

    def p(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def run_w(self, **kw):
        return {r["file"]: r for r in watch.run_once(self.root, self.dl, settle=0, **kw)}


class Watch(Base):
    def test_scene_file_goes_to_its_batch_folder(self):
        src = self.put("IMG045_cave_wall_1b901f0a_2K.jpg", b"new")
        r = self.run_w()["IMG045_cave_wall_1b901f0a_2K.jpg"]
        self.assertEqual((r["action"], r["to"]), ("moved", "images/scenes/b05/IMG045_cave_wall_1b901f0a_2K.jpg"))
        self.assertFalse(os.path.exists(src))  # cut, not copied
        self.assertEqual(open(self.p(r["to"]), "rb").read(), b"new")

    def test_batch_numbers(self):
        for n, b in (("IMG000", "b00"), ("IMG010", "b01"), ("IMG011", "b02"), ("IMG1000", "b100")):
            self.assertEqual(watch.destination(n, "scene"), "images/scenes/" + b)

    def test_reference_goes_to_its_kind_folder(self):
        self.put("CH_MIMO_99999999.png", b"1")
        self.put("LOC_NEWPLACE_aaaabbbb.jpg", b"2")
        r = self.run_w()
        self.assertEqual(r["CH_MIMO_99999999.png"]["to"], "images/refs/CH/CH_MIMO_99999999.png")
        self.assertEqual(r["LOC_NEWPLACE_aaaabbbb.jpg"]["to"], "images/refs/LOC/LOC_NEWPLACE_aaaabbbb.jpg")  # known from its prompts.txt header

    def test_wrong_episode_unknown_base_and_strangers_are_untouched(self):
        a = self.put("IMG045_other_episode_scene_1b901f0a.jpg")  # same id, another slug
        b = self.put("IMG777_cave_wall_1b901f0a.jpg")  # not in this project
        c = self.put("Engineering_sketch_of_unmanned_a…_be66d232_2K (1).jpg")
        d = self.put("notes.txt")
        e = self.put("FOO_BAR_1b901f0a.jpg")  # parses, but nothing in the project calls it that
        r = self.run_w()
        self.assertEqual({k: v["action"] for k, v in r.items()}, {os.path.basename(a): "skip", os.path.basename(b): "skip", os.path.basename(e): "skip"})
        for f in (a, b, c, d, e):
            self.assertTrue(os.path.exists(f), f)
        self.assertFalse(os.path.exists(self.p(".kit/imports.tsv")))

    def test_slug_is_tolerant_of_case_underscores_and_flow_cutoff(self):
        for got, want, ok in (("Cave_Wall", "cave_wall", True), ("cave-wall", "cave_wall", True), ("cave_w…", "cave_wall", True), ("cave_wall", "cave_w…", True),
                              ("cave_wal…", "cave_wall", True), ("other", "cave_wall", False), ("…", "cave_wall", False), ("", "cave_wall", True), ("cave_wall_2", "cave_wall", False)):
            self.assertEqual(flowname.slugs_match(got, want), ok, (got, want))
        self.put("IMG045_Cave_Wal…_1b901f0a.jpg")
        self.assertEqual(self.run_w()["IMG045_Cave_Wal…_1b901f0a.jpg"]["action"], "moved")

    def test_slug_of_existing_versions_is_the_expectation_without_output_name(self):
        self.put("IMG001_hook_bench_aaaa1111.jpg", b"v2")
        self.put("IMG001_somewhere_else_aaaa2222.jpg", b"v3")
        r = self.run_w()
        self.assertEqual(r["IMG001_hook_bench_aaaa1111.jpg"]["action"], "moved")
        self.assertEqual(r["IMG001_somewhere_else_aaaa2222.jpg"]["action"], "skip")

    def test_no_expectation_and_a_slug_is_left_alone_unless_match_slug_is_off(self):
        f = self.put("IMG046_whatever_aaaa1111.jpg")
        self.assertEqual(self.run_w()["IMG046_whatever_aaaa1111.jpg"]["action"], "skip")
        write(self.p("kit-config.json"), json.dumps({"match_slug": False}))
        self.assertEqual(self.run_w()["IMG046_whatever_aaaa1111.jpg"]["action"], "moved")
        self.assertFalse(os.path.exists(f))

    def test_partial_downloads_are_skipped(self):
        a = self.put("IMG045_cave_wall_1b901f0a.jpg.crdownload")
        b = self.put("IMG045_cave_wall_1b901f0a.jpg.part")
        self.assertEqual(self.run_w(), {})
        self.assertTrue(os.path.exists(a) and os.path.exists(b))
        # a file that grows while the watcher looks is not taken
        name = "IMG045_cave_wall_2b901f0a.jpg"
        path = self.put(name)
        real = os.stat
        calls = []

        def growing(p, *a, **k):
            if os.fspath(p) == path:
                calls.append(1)
                if len(calls) >= 2:
                    open(path, "ab").write(b"more")
            return real(p, *a, **k)
        with mock.patch("watch.os.stat", growing), mock.patch("watch.time.sleep"):
            r = {x["file"]: x for x in watch.run_once(self.root, self.dl, settle=0.01)}
        self.assertEqual((r[name]["action"], r[name]["reason"]), ("skip", "still being downloaded"))
        self.assertTrue(os.path.exists(path))

    def test_taken_name_gets_a_free_number_never_overwrites(self):
        write(self.p("images/scenes/b05/IMG045_cave_wall_1b901f0a.jpg"), b"old")
        self.put("IMG045_cave_wall_1b901f0a.jpg", b"different")
        r = self.run_w()["IMG045_cave_wall_1b901f0a.jpg"]
        self.assertEqual(r["to"], "images/scenes/b05/IMG045_cave_wall_1b901f0a (1).jpg")
        self.assertEqual(open(self.p("images/scenes/b05/IMG045_cave_wall_1b901f0a.jpg"), "rb").read(), b"old")
        self.put("IMG045_cave_wall_1b901f0a.jpg", b"third")
        self.assertEqual(self.run_w()["IMG045_cave_wall_1b901f0a.jpg"]["to"], "images/scenes/b05/IMG045_cave_wall_1b901f0a (2).jpg")

    def test_identical_file_is_only_dropped_from_downloads(self):
        write(self.p("images/scenes/part01/IMG045_cave_wall_1b901f0a.jpg"), b"same")  # an old folder: anywhere in the project counts
        d = self.put("IMG045_cave_wall_1b901f0a (1).jpg", b"same")
        r = self.run_w()["IMG045_cave_wall_1b901f0a (1).jpg"]
        self.assertEqual(r["action"], "duplicate")
        self.assertFalse(os.path.exists(d))
        self.assertEqual(sorted(os.listdir(self.p("images/scenes"))), ["b01", "part01"])  # nothing new in the project

    def test_log_is_written_and_dry_run_changes_nothing(self):
        src = self.put("IMG045_cave_wall_1b901f0a.jpg", b"abc")
        r = self.run_w(dry_run=True)["IMG045_cave_wall_1b901f0a.jpg"]
        self.assertEqual(r["action"], "moved")
        self.assertTrue(os.path.exists(src))
        self.assertFalse(os.path.exists(self.p(".kit/imports.tsv")) or os.path.exists(self.p("images/scenes/b05")))
        self.run_w()
        t, frm, to, size = open(self.p(".kit/imports.tsv"), encoding="utf-8").read().rstrip("\n").split("\t")
        self.assertEqual((frm, to, size), (src, "images/scenes/b05/IMG045_cave_wall_1b901f0a.jpg", "3"))
        self.assertRegex(t, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        self.assertEqual(watch.recent_imports(self.root)[0]["to"], to)

    def test_cross_drive_move_falls_back_to_shutil_move(self):
        src = self.put("IMG045_cave_wall_1b901f0a.jpg", b"across")
        real = os.replace

        def replace(a, b):
            if os.fspath(a) == src:
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return real(a, b)
        with mock.patch("watch.os.replace", replace), mock.patch("shutil.os.rename", side_effect=OSError(errno.EXDEV, "x"), create=True):
            r = self.run_w()["IMG045_cave_wall_1b901f0a.jpg"]
        self.assertEqual(r["action"], "moved")
        self.assertFalse(os.path.exists(src))
        self.assertEqual(open(self.p(r["to"]), "rb").read(), b"across")
        self.assertFalse([f for f in os.listdir(self.p("images/scenes/b05")) if f.endswith(".tmp")])

    def test_downloads_folder_from_config_and_default(self):
        write(self.p("kit-config.json"), json.dumps({"downloads": "dl-here"}))
        self.assertEqual(watch.downloads_dir(self.root), os.path.join(self.root, "dl-here"))
        os.remove(self.p("kit-config.json"))
        self.assertEqual(watch.downloads_dir(self.root), os.path.join(os.path.expanduser("~"), "Downloads"))


class Folders(Base):
    def test_files_put_by_hand_into_any_subfolder_just_work(self):
        write(self.p("images/scenes/my own folder/IMG046_by_hand_aaaa1111.png"), b"h")
        write(self.p("images/refs/CH/deep/er/CH_HAND_bbbb2222.png"), b"r")
        write(self.p("images/refs/PROP_FLAT.png"), b"p")  # straight into refs/
        import_cmd = ("import json, media, story; s = media.scan_images(); r = media.scan_refs(story.parse_prompts());"
                      "print(json.dumps(dict(v=[x['src'] for x in s['IMG046']['versions']], r=[(x['name'], x['kind']) for x in r])))")
        res = self.sub(import_cmd)
        self.assertEqual(res["v"], ["images/scenes/my own folder/IMG046_by_hand_aaaa1111.png"])
        self.assertIn(["CH_HAND", "CH"], res["r"])
        self.assertIn(["PROP_FLAT", "PROP"], res["r"])

    def test_odd_names_in_refs_need_triage_and_are_not_references(self):
        write(self.p("images/refs/Engineering_sketch_a…_be66d232_2K (1).jpg"), b"o")
        write(self.p("images/refs/CH/photo.jpg"), b"o")
        res = self.sub("import json, media, story; print(json.dumps(dict(r=[x['name'] for x in media.scan_refs(story.parse_prompts())], t=[x['name'] for x in media.refs_triage()])))")
        self.assertEqual(sorted(res["r"]), ["CH_MIMO", "LOC_CAVE"])
        self.assertEqual(sorted(res["t"]), ["Engineering_sketch_a…_be66d232_2K (1).jpg", "photo.jpg"])

    def test_inbox_is_listed_and_not_scanned_for_versions(self):
        write(self.p("inbox/IMG046_stray_aaaa1111.jpg"), b"1234")
        write(self.p("inbox/sub/voice note.mp3"), b"12")
        write(self.p("inbox/brief.docx"), b"x")
        res = self.sub("import json, media; print(json.dumps(dict(i=media.scan_inbox(), s=sorted(media.scan_images()))))")
        self.assertEqual({(f["name"], f["kind"], f["size"]) for f in res["i"]}, {("IMG046_stray_aaaa1111.jpg", "image", 4), ("sub/voice note.mp3", "audio", 2), ("brief.docx", "text", 1)})
        self.assertEqual(res["s"], ["IMG001"])

    def sub(self, code):
        tools = os.path.join(self.root, "tools")
        if not os.path.isdir(tools):
            shutil.copytree(os.path.join(KIT, "tools"), tools, ignore=shutil.ignore_patterns("tests", "__pycache__"))
        r = subprocess.run([sys.executable, "-c", code], cwd=tools, capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        return json.loads(r.stdout) if r.stdout.strip() else None


class Batch(Folders):
    def cli(self, *a):
        self.sub("pass")
        return subprocess.run([sys.executable, "tools/batch.py", *a], cwd=self.root, capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))

    def test_text_of_a_batch(self):
        r = self.cli("b05")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = r.stdout
        self.assertEqual([l for l in t.split("\n") if l.startswith("=== ")], ["=== IMG041 ===", "=== IMG045 ===", "=== IMG046 ===", "=== IMG050 ==="])  # IMG051 is b06, in order, no gaps invented
        i45 = t[t.index("=== IMG045 ==="):t.index("=== IMG046 ===")]
        self.assertIn("[REFS TO ATTACH: STYLE_ANCHOR| LOC_CAVE_11112222.jpg| CH_NOFILE]", i45)  # real file names; a name with no file stays as written
        self.assertIn("[OUTPUT NAME: IMG045_cave_wall]\nPrompt of the cave wall.", i45)
        self.assertTrue(i45.rstrip().endswith("Output name: IMG045_cave_wall"))
        self.assertIn("CH_MIMO_4eb46d68.jpg", t[t.index("=== IMG041 ==="):t.index("=== IMG045 ===")])
        self.assertIn("Output name: IMG050\n", t)  # no slug known yet
        self.assertIn("CH_NOFILE", r.stderr)
        self.assertIn("IMG001", self.cli("b01").stdout)
        self.assertIn("Output name: IMG001_hook_bench", self.cli("b01").stdout)  # slug of the version on disk
        self.assertNotEqual(self.cli("b5x").returncode, 0)

    def test_full_batch_of_ten(self):
        write(self.p("scenario/story.txt"), "=== scene-01 | T | 0:00-0:10 ===\n" + "".join("[IMG%03d]\n" % n for n in range(41, 51)))
        write(self.p("prompts/prompts.txt"), "".join("=== IMG%03d ===\n[REFS TO ATTACH: STYLE_ANCHOR| CH_MIMO]\n[OUTPUT NAME: IMG%03d_s%d]\nP%d\n\n" % (n, n, n, n) for n in range(41, 51)))
        t = self.cli("b05").stdout
        self.assertEqual(t.count("=== IMG"), 10)
        self.assertEqual(t.count("[REFS TO ATTACH: STYLE_ANCHOR| CH_MIMO_4eb46d68.jpg]"), 10)
        self.assertIn("Output name: IMG049_s49", t)


class Manifest(unittest.TestCase):
    def test_new_engine_files_are_listed(self):
        files = open(os.path.join(KIT, "ENGINE.txt"), encoding="utf-8").read().split("\n")
        for f in ("tools/watch.py", "tools/batch.py"):
            self.assertIn(f, files)


if __name__ == "__main__":
    unittest.main()
