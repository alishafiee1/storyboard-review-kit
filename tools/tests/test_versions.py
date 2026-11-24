# -*- coding: utf-8 -*-
"""Unit tests of the Flow file-name reader (tools/flowname.py) and of the shared resolver (media.resolve) on a throw-away folder of fake files.
Run:  python -m unittest discover -s tools/tests -p "test_*.py" """
import json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import flowname, media  # noqa: E402

# (path inside the project, age in seconds: bigger = older). Every file is an empty fake.
FILES = [
    ("images/scenes/part01/IMG001_hook_bench_passersby_edfa6fe0.jpg", 900),     # the normal file of version edfa6fe0 ...
    ("images/scenes/part01/IMG001_hook_bench_passersby_edfa6fe0_2K.jpg", 800),  # ... its 2K ...
    ("images/scenes/b01/IMG001_hook_bench_passersby_edfa6fe0_4K.jpg", 700),     # ... and its 4K (another folder)
    ("images/scenes/b01/IMG001_hook_bench_passersby_edfa6fe0_4K (1).jpg", 650),   # browser copy of the 4K: ignored
    ("images/scenes/IMG001_other_take_1b901f0a_2K.jpg", 500),                    # a second version, only 2K
    ("images/scenes/IMG001_old_name.png", 950),                                   # an old version without a random id
    ("images/scenes/IMG001_only_copy (1).png", 400),                              # only the browser copy exists: it still counts
    ("images/scenes/IMG045_cave.png", 300),
    ("images/scenes/IMG0451_not_045.png", 300),                                   # IMG0451 is not IMG045
    ("images/scenes/IMG046notasep.png", 300),                                     # old style name: still IMG046 (legacy rule)
    ("images/scenes/IMG010_x/IMG010_a_aaaaaaaa.png", 300),
    ("images/scenes/archive/IMG010_b_bbbbbbbb.png", 300),                          # archive: skipped
    ("images/scenes/_rejected/IMG010_c_cccccccc.png", 300),                       # rejected: not a version
    ("images/scenes/inbox/IMG010_d_dddddddd.png", 300),                           # inbox: skipped
    ("images/refs/LOC/LOC_FACTORY_YARD_4eb46d68.jpg", 300),
    ("images/refs/CH/deep/CH_MIMO_12345678.png", 300),                            # an all-digit random id must not become part of the name
    ("images/refs/CH/Engineering_sketch_of_unmanned_a…_be66d232_2K (1).jpg", 300),  # not a project name
    ("audio/fa/IMG045-1_ab12cd34.mp3", 200),
    ("audio/fa/b05/IMG045-1_ab12cd34 (1).mp3", 190),
    ("audio/fa/b05/IMG045-1_00ff00ff.mp3", 100),
    ("audio/fa/IMG045-1.mp3", 300),
    ("audio/fa/IMG045-1.eleven-v3.mp3", 250),
    ("audio/fa/L007.mp3", 300),
    ("audio/fa/archive/IMG045-1_99999999.mp3", 100),
]


class Folder(unittest.TestCase):
    def setUp(self):
        import time
        self.root = tempfile.mkdtemp()
        now = time.time()
        for rel, age in FILES:
            p = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").close()
            os.utime(p, (now - age, now - age))
        self.old = (media.ROOT, flowname.ROOT)
        media.ROOT = flowname.ROOT = self.root

    def tearDown(self):
        media.ROOT, flowname.ROOT = self.old
        shutil.rmtree(self.root, ignore_errors=True)

    def config(self, **c):
        with open(os.path.join(self.root, "kit-config.json"), "w", encoding="utf-8") as fh:
            json.dump(c, fh)


class NameParsing(unittest.TestCase):
    def test_real_flow_names(self):
        p = flowname.parse("IMG001_hook_bench_passersby_edfa6fe0_2K.jpg")
        self.assertEqual((p["base"], p["slug"], p["rid"], p["q"], p["dup"]), ("IMG001", "hook_bench_passersby", "edfa6fe0", "2K", False))
        self.assertEqual(p["key"], ("IMG001", "edfa6fe0"))
        p = flowname.parse("IMG018_dna_bookshelf_8c45285a.jpg")
        self.assertEqual((p["slug"], p["rid"], p["q"]), ("dna_bookshelf", "8c45285a", ""))
        p = flowname.parse("LOC_FACTORY_YARD_4eb46d68.jpg")
        self.assertEqual((p["base"], p["slug"], p["rid"]), ("LOC_FACTORY_YARD", "", "4eb46d68"))
        self.assertEqual(flowname.parse("CH_MIMO.png")["key"], ("CH_MIMO", ""))

    def test_quality_is_case_insensitive_and_dup_is_noticed(self):
        p = flowname.parse("IMG047_morning_after_1b901f0a_4k (2).JPG")
        self.assertEqual((p["q"], p["dup"], p["rid"]), ("4K", True, "1b901f0a"))

    def test_without_a_random_id_the_slug_is_the_key(self):
        self.assertEqual(flowname.parse("IMG001_start.png")["key"], ("IMG001", "start"))
        self.assertEqual(flowname.parse("IMG001.png")["key"], ("IMG001", ""))
        self.assertEqual(flowname.parse("IMG001_start_2K.png")["key"], ("IMG001", "start"))

    def test_truncated_slug_with_ellipsis(self):
        p = flowname.parse("IMG012_a_very_long_prom…_be66d232_2K (1).jpg")
        self.assertEqual((p["slug"], p["rid"], p["q"], p["dup"]), ("a_very_long_prom…", "be66d232", "2K", True))

    def test_not_project_files(self):
        for n in ("Engineering_sketch_of_unmanned_a…_be66d232_2K (1).jpg", "IMG045.txt", "photo.jpg", "IMG045abc.png"):
            self.assertIsNone(flowname.parse(n), n)

    def test_img0451_is_not_img045(self):
        self.assertEqual(flowname.parse("IMG0451_x.png")["base"], "IMG0451")
        self.assertEqual(flowname.parse("IMG045_x.png")["base"], "IMG045")

    def test_all_digit_random_id_is_not_a_name_part(self):
        p = flowname.parse("CH_MIMO_12345678.png")
        self.assertEqual((p["base"], p["rid"]), ("CH_MIMO", "12345678"))

    def test_batch_comes_from_the_number(self):
        self.assertEqual([flowname.batch_of(x) for x in ("IMG000", "IMG001", "IMG010", "IMG011", "IMG020", "IMG021", "IMG045", "CH_MIMO")],
                         ["b00", "b01", "b01", "b02", "b02", "b03", "b05", "" ])

    def test_voice_names(self):
        a = flowname.audio_parse
        self.assertEqual(a("IMG045-1_ab12cd34.mp3"), ("IMG045-1", "ab12cd34", False))
        self.assertEqual(a("IMG045-1_ab12cd34 (1).mp3"), ("IMG045-1", "ab12cd34", True))
        self.assertEqual(a("IMG045-1.eleven-v3.mp3"), ("IMG045-1", "eleven-v3", False))
        self.assertEqual(a("IMG001_1.mp3"), ("IMG001_1", "default", False))
        self.assertEqual(a("L007.mp3"), ("L007", "default", False))
        self.assertIsNone(a("note.txt"))


class Versions(Folder):
    def versions(self, id_):
        return media.scan_images()[id_]["versions"]

    def test_qualities_of_one_random_id_are_one_version(self):
        vs = self.versions("IMG001")
        v = next(x for x in vs if x["id"] == "edfa6fe0")
        self.assertEqual(v["name"], "IMG001_hook_bench_passersby_edfa6fe0_4K.jpg")  # 4K beats 2K beats the normal file
        self.assertEqual(v["q"], "4K")
        self.assertEqual(len(v["files"]), 4)  # normal, 2K, 4K and the 4K's « (1)» copy (kept in the list so an archive takes it too; it is never shown)
        self.assertNotIn("(1)", v["name"])
        self.assertEqual(len([x for x in vs if x["id"] == "edfa6fe0"]), 1)

    def test_versions_are_counted_without_quality_duplicates(self):
        ids = [v["id"] for v in self.versions("IMG001")]
        self.assertEqual(ids[:2], ["IMG001_old_name.png", "edfa6fe0"])  # oldest first
        self.assertEqual(len(ids), 4)  # old_name, edfa6fe0, 1b901f0a and the only-copy-with-(1)
        self.assertIn("IMG001_only_copy (1).png", ids)  # no original: the browser copy is the version

    def test_browser_copy_is_ignored_only_when_the_original_exists(self):
        v = next(x for x in self.versions("IMG001") if x["id"] == "edfa6fe0")
        self.assertNotIn("(1)", v["name"])

    def test_img0451_does_not_join_img045(self):
        scan = media.scan_images()
        self.assertEqual([v["name"] for v in scan["IMG045"]["versions"]], ["IMG045_cave.png"])
        self.assertIn("IMG0451", scan)

    def test_old_style_name_without_separator_still_belongs_to_its_image(self):
        self.assertEqual([v["name"] for v in media.scan_images()["IMG046"]["versions"]], ["IMG046notasep.png"])

    def test_scan_is_recursive_and_skips_archive_rejected_inbox(self):
        scan = media.scan_images()["IMG010"]
        self.assertEqual([v["name"] for v in scan["versions"]], ["IMG010_a_aaaaaaaa.png"])
        self.assertEqual(scan["rejected"], ["images/scenes/_rejected/IMG010_c_cccccccc.png"])

    def test_pick_by_random_id_survives_a_new_4k(self):
        scan = media.scan_images()
        r = media.resolve("image", "IMG001", "1b901f0a", scan=scan)
        self.assertEqual((r["name"], r["picked"]), ("IMG001_other_take_1b901f0a_2K.jpg", True))
        path = os.path.join(self.root, "images", "scenes", "b01", "IMG001_other_take_1b901f0a_4K.jpg")
        open(path, "wb").close()
        r = media.resolve("image", "IMG001", "1b901f0a")  # the pick did not change; the shown file did
        self.assertEqual((r["name"], r["q"], r["picked"]), ("IMG001_other_take_1b901f0a_4K.jpg", "4K", True))
        self.assertEqual(len(self.versions("IMG001")), 4)  # still four versions

    def test_pick_by_old_file_name_still_finds_its_version(self):
        for old in ("IMG001_hook_bench_passersby_edfa6fe0_2K.jpg", "IMG001_hook_bench_passersby_edfa6fe0.jpg", "IMG001_hook_bench_passersby_edfa6fe0_4K (1).jpg"):
            r = media.resolve("image", "IMG001", old)
            self.assertEqual((r["id"], r["name"]), ("edfa6fe0", "IMG001_hook_bench_passersby_edfa6fe0_4K.jpg"), old)
        st = media.image_state(dict(id="IMG001", pick="IMG001_hook_bench_passersby_edfa6fe0_2K.jpg", status=""), media.scan_images()["IMG001"])
        self.assertEqual((st["picked"], st["status"], st["batch"]), ("edfa6fe0", "ok", "b01"))

    def test_no_pick_shows_the_newest_version_and_unknown_pick_is_no_pick(self):
        self.assertEqual(media.resolve("image", "IMG001", "")["name"], "IMG001_only_copy (1).png")
        r = media.resolve("image", "IMG001", "zzzzzzzz")
        self.assertEqual((r["name"], r["picked"]), ("IMG001_only_copy (1).png", False))
        self.assertIsNone(media.resolve("image", "IMG999"))

    def test_nothing_is_renamed_or_removed(self):
        before = sorted(os.path.join(d, f) for d, _, fs in os.walk(self.root) for f in fs)
        media.scan_images(), media.scan_refs({}), media.resolve("image", "IMG001", "edfa6fe0")
        self.assertEqual(before, sorted(os.path.join(d, f) for d, _, fs in os.walk(self.root) for f in fs))

    def test_references_are_found_recursively_and_listed_once(self):
        refs = {r["name"]: r for r in media.scan_refs({})}
        self.assertEqual(sorted(refs)[0::2], ["CH_MIMO", "LOC_FACTORY_YARD"])  # (an odd file in refs/ is still listed, as in old projects, under its cleaned-up name)
        self.assertNotIn("(1)", " ".join(refs))
        self.assertEqual((refs["LOC_FACTORY_YARD"]["kind"], refs["CH_MIMO"]["kind"]), ("LOC", "CH"))

    def test_archive_takes_every_quality_of_the_version(self):
        media.archive_item("image", "IMG001", "IMG001_hook_bench_passersby_edfa6fe0_2K.jpg")
        arch = os.listdir(os.path.join(self.root, "images", "archive"))
        self.assertEqual(len([a for a in arch if "edfa6fe0" in a]), 4)  # normal, 2K, 4K and the 4K's « (1)» copy go together
        self.assertNotIn("edfa6fe0", [v["id"] for v in self.versions("IMG001")])


class Voices(Folder):
    def names(self, id_):
        return [v["name"] for v in media.audio_variants("fa", id_)]

    def test_new_and_old_voice_names_are_versions_of_one_line(self):
        self.assertEqual(self.names("IMG045-1"), ["default", "eleven-v3", "ab12cd34", "00ff00ff"])  # default first, then oldest first; the « (1)» copy is ignored
        self.assertEqual(self.names("L007"), ["default"])

    def test_archive_is_not_read_and_resolve_follows_the_pick(self):
        self.assertNotIn("99999999", self.names("IMG045-1"))
        self.assertEqual(media.resolve("voice", "IMG045-1", "", "fa")["name"], "default")
        r = media.resolve("voice", "IMG045-1", "00ff00ff", "fa")
        self.assertEqual((r["name"], r["src"]), ("00ff00ff", "audio/fa/b05/IMG045-1_00ff00ff.mp3"))
        self.assertEqual(media.resolve("voice", "IMG045-1", "eleven-v3", "fa")["name"], "eleven-v3")
        self.assertIsNone(media.resolve("voice", "IMG777-1", "", "fa"))

    def test_audio_url_and_choice_use_the_pick_map(self):
        url, v = media.audio_url("fa", "IMG045-1", {"IMG045-1.fa": "ab12cd34"})
        self.assertTrue(url.startswith("audio/fa/IMG045-1_ab12cd34.mp3?v="))
        self.assertEqual((v["chosen"], len(v["names"])), ("ab12cd34", 4))

    def test_archived_voices_are_listed_with_the_same_rule(self):
        self.assertEqual([a["name"] for a in media.archived_voices("fa", "IMG045-1")], ["99999999"])


class Config(Folder):
    def test_custom_pattern_and_quality_order(self):
        self.config(name_pattern=r"^(?P<base>IMG\d{3})-(?P<rid>[0-9a-f]{8})(?:-(?P<q>hi|lo))?\.(?P<ext>png)$", quality=["hi", "lo"])
        open(os.path.join(self.root, "images", "scenes", "IMG200-0a0a0a0a-lo.png"), "wb").close()
        open(os.path.join(self.root, "images", "scenes", "IMG200-0a0a0a0a-hi.png"), "wb").close()
        v = media.scan_images()["IMG200"]["versions"]
        self.assertEqual((len(v), v[0]["id"]), (1, "0a0a0a0a"))
        self.assertEqual(v[0]["name"], "IMG200-0a0a0a0a-HI.png".replace("HI", "hi"))

    def test_broken_config_falls_back_to_the_default(self):
        with open(os.path.join(self.root, "kit-config.json"), "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        self.assertEqual(flowname.parse("IMG001_a_edfa6fe0.jpg")["rid"], "edfa6fe0")
        self.config(name_pattern="(unclosed")
        self.assertEqual(flowname.parse("IMG001_a_edfa6fe0.jpg")["rid"], "edfa6fe0")


if __name__ == "__main__":
    unittest.main()
