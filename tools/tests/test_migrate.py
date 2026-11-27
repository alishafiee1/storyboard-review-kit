# -*- coding: utf-8 -*-
"""Unit tests of v1.20: tools/migrate.py (dry-run, apply, undo, collisions, dirty git), premiere_check --fix, the new voice names of tts.py (+ voices.tsv),
image-based ids of new dialogue lines, and tools/premiere_export.py. Everything runs on throw-away copies of the «1-mimo-white-head» fixture (tests/mimo.py);
migrate.py is started as a program inside the copy, like a user would.
Run:  python -m unittest discover -s tools/tests -p "test_*.py" """
import glob, json, os, re, shutil, struct, subprocess, sys, tempfile, unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import mimo  # noqa: E402
import premiere_check  # noqa: E402


def run(root, *args, code=None):
    """Run a tool of the copy as a program. Returns CompletedProcess (text)."""
    cmd = [sys.executable, "-c", code] if code else [sys.executable] + list(args)
    return subprocess.run(cmd, cwd=root, capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def git(root, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t"] + list(a), cwd=root, capture_output=True, text=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srk-mig-")
        self.root = os.path.join(self.tmp, "1-mimo-white-head")
        os.makedirs(self.root)
        mimo.build(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def read(self, rel):
        return open(self.path(rel), encoding="utf-8").read()

    def lines(self):
        """What every dialogue line plays now: [{img, fa, fa (sha1 of the chosen file), en, ...}] in story order (read by the real project code in the copy)."""
        r = run(self.root, code=mimo.RESOLVE)
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        return json.loads(r.stdout)

    def apply(self, *extra):
        r = run(self.root, "tools/migrate.py", "--apply", "--allow-dirty", *extra)
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        return re.search(r"--undo (\d{8}-\d{6})", r.stdout).group(1)


class DryRun(Base):
    def test_changes_nothing_and_reports_everything(self):
        before = mimo.snapshot(self.root)
        r = run(self.root, "tools/migrate.py")
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        self.assertEqual(mimo.snapshot(self.root), before)  # no file of the project changed
        self.assertFalse(os.path.exists(self.path(".engine-backup")) or os.path.exists(self.path(".kit/renames.tsv")))
        for want in ("`IMG001_1` | `IMG001-1`", "`L007` | `IMG006-1`", "`IMG004_1` | `IMG005-1`", "audio/fa/IMG001_1.eleven-v3.mp3` | `audio/fa/IMG001-1.eleven-v3.mp3",
                     "audio/en/L007.mp3` | `audio/en/IMG006-1.mp3", "audio/fa/archive/IMG001_1.eleven-v4.mp3", "shared block", "IMG099_1", "EP01_EN_premiere.xml"):
            self.assertIn(want, r.stdout)
        self.assertNotIn("_samples/sample", r.stdout)  # samples are not touched, so they are not even listed
        saved = glob.glob(self.path(".kit/migrate-report-*.md"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(open(saved[0], encoding="utf-8").read().strip(), r.stdout.split("report saved to")[0].strip())

    def test_dry_run_flag_is_the_same_as_no_flag(self):
        self.assertEqual(run(self.root, "tools/migrate.py", "--dry-run").returncode, 0)
        self.assertFalse(os.path.exists(self.path(".engine-backup")))


class Apply(Base):
    def test_renames_files_and_updates_story_and_xml(self):
        stamp = self.apply()
        for lg in ("fa", "en"):
            names = sorted(os.listdir(self.path("audio/" + lg)))
            for want in ("IMG001-1.mp3", "IMG001-1.eleven-v3.mp3", "IMG003-1.mp3", "IMG003-2.mp3", "IMG003-2.eleven-v3.mp3", "IMG005-1.mp3", "IMG006-1.mp3", "IMG006-1.eleven-v3.mp3"):
                self.assertIn(want, names)
            for old in ("IMG001_1.mp3", "IMG003_2.mp3", "IMG004_1.mp3", "L007.mp3"):
                self.assertNotIn(old, names)
            self.assertIn("sample.mp3", os.listdir(self.path("audio/%s/_samples" % lg)))  # untouched
            self.assertIn("IMG099_1.mp3", names)  # belongs to no line: untouched
        self.assertIn("IMG001-1.eleven-v4.mp3", os.listdir(self.path("audio/fa/archive")))
        st = self.read("scenario/story.txt")
        for want in ("id: IMG001-1", "id: IMG003-1", "id: IMG003-2", "id: IMG005-1", "id: IMG006-1", "id: IMG010-1"):
            self.assertIn(want, st)
        self.assertNotIn("id: L007", st)
        self.assertEqual(st.count("voice-pick:"), 1)  # only the entry that names no line of its scene stays (IMG999_1)
        self.assertIn("voice-pick: IMG999_1.fa=eleven-v3", st)
        self.assertEqual(re.search(r"\[IMG001\]\n(?:.*\n)*?voice: (.*)\n", st).group(1), "fa=eleven-v3")  # the scene-level choice sits under its line
        self.assertIn("voice: en=eleven-v3", st)
        self.assertNotIn("voice-stale: en\nvoice-pick", st)
        rows = [l.split("\t") for l in self.read(".kit/renames.tsv").split("\n") if l]
        self.assertEqual(len(rows), 18)
        self.assertTrue(all(r[0] == stamp and len(r) == 3 for r in rows))
        self.assertIn(["%s" % stamp, "audio/en/L007.mp3", "audio/en/IMG006-1.mp3"], rows)
        self.assertTrue(os.path.isfile(self.path(".engine-backup/migrate-%s/scenario/story.txt" % stamp)))
        self.assertTrue(os.path.isfile(self.path(".engine-backup/migrate-%s/videos/final/EP01_EN_premiere.xml" % stamp)))

    def test_every_voice_still_plays_the_same_bytes(self):
        before = self.lines()
        self.assertTrue(any(r["en"] and r["fa"] for r in before))
        self.apply()
        after = self.lines()
        self.assertEqual(after, before)  # same chosen file (by content) for every line and language, and as many variants as before

    def test_xml_changes_only_the_pathurls_of_renamed_voices(self):
        orig = open(self.path("videos/final/EP01_EN_premiere.xml"), "rb").read()
        notes = open(self.path("videos/final/notes.xml"), "rb").read()
        self.apply()
        new = open(self.path("videos/final/EP01_EN_premiere.xml"), "rb").read()
        self.assertIn(b"\r\n", new)
        self.assertEqual(open(self.path("videos/final/notes.xml"), "rb").read(), notes)
        strip = lambda b: re.sub(rb"<pathurl>.*?</pathurl>", b"<pathurl/>", b)
        self.assertEqual(strip(new), strip(orig))  # everything outside the pathurls: byte identical
        old_urls, new_urls = re.findall(rb"<pathurl>(.*?)</pathurl>", orig), re.findall(rb"<pathurl>(.*?)</pathurl>", new)
        self.assertEqual(len(old_urls), len(new_urls))
        want = {b"/audio/en/IMG001_1.mp3": b"/audio/en/IMG001-1.mp3", b"/audio/en/IMG003_2.eleven-v3.mp3": b"/audio/en/IMG003-2.eleven-v3.mp3", b"/audio/en/L007.mp3": b"/audio/en/IMG006-1.mp3",
                b"/audio/en/IMG004_1.mp3": b"/audio/en/IMG005-1.mp3"}
        for o, n in zip(old_urls, new_urls):
            if o.endswith(b".jpg"):
                self.assertEqual(o, n)  # pictures are not renamed
                continue
            self.assertNotEqual(o, n)
            self.assertTrue(n.startswith(o[:o.rindex(b"audio") + 5]))  # the folder part stays exactly as it was (URL-encoded D%3a, backslashes, ../..)
        self.assertIn(b"file://localhost/Z%3a/mimo-other-pc/1-mimo-white-head/audio/en/IMG005-1.mp3", new)
        self.assertIn(b"<pathurl>../../audio/en/IMG001-1.mp3</pathurl>", new)
        self.assertIn(b"Z:\\mimo-other-pc\\1-mimo-white-head\\audio\\fa\\IMG001-1.mp3", new)
        for n in want.values():
            self.assertIn(n, new)

    def test_second_run_finds_nothing_to_do(self):
        self.apply()
        r = run(self.root, "tools/migrate.py")
        self.assertIn("dialogue lines that get a new id: **0**", r.stdout)
        self.assertIn("voice files renamed: **0**", r.stdout)

    def test_new_ids_never_reuse_an_existing_one(self):
        """A picture that already has IMG003-1 (a line added with the new version) gets its old lines the next free numbers."""
        p = self.path("scenario/story.txt")
        st = open(p, encoding="utf-8").read().replace("[IMG003]\n", "[IMG003]\nsay: علی | یک خط تازه.\nid: IMG003-1\n")
        open(p, "w", encoding="utf-8").write(st)
        self.apply()
        ids = re.findall(r"^id: (IMG003-\d)$", self.read("scenario/story.txt"), re.M)
        self.assertEqual(sorted(ids), ["IMG003-1", "IMG003-2", "IMG003-3"])


class Undo(Base):
    def test_restores_files_story_and_xml_byte_for_byte(self):
        before = mimo.snapshot(self.root)
        stamp = self.apply()
        self.assertNotEqual(mimo.snapshot(self.root), before)
        r = run(self.root, "tools/migrate.py", "--undo", stamp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr[-500:])
        self.assertEqual(mimo.snapshot(self.root), before)
        self.assertFalse(os.path.exists(self.path(".kit/renames.tsv")))  # its rows were this migration's

    def test_refuses_when_story_changed_since_unless_forced(self):
        stamp = self.apply()
        with open(self.path("scenario/story.txt"), "a", encoding="utf-8") as fh:
            fh.write("# a later edit\n")
        r = run(self.root, "tools/migrate.py", "--undo", stamp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("changed since the migration", r.stderr + r.stdout)
        self.assertTrue(os.path.exists(self.path("audio/en/IMG001-1.mp3")))  # nothing was touched
        self.assertEqual(run(self.root, "tools/migrate.py", "--undo", stamp, "--force").returncode, 0)
        self.assertTrue(os.path.exists(self.path("audio/en/IMG001_1.mp3")))

    def test_unknown_time(self):
        self.assertNotEqual(run(self.root, "tools/migrate.py", "--undo", "20200101-000000").returncode, 0)


class Collisions(Base):
    def test_a_taken_name_is_never_overwritten_and_the_line_keeps_its_old_name(self):
        taken = b"someone elses file"
        with open(self.path("audio/fa/IMG003-1.mp3"), "wb") as fh:
            fh.write(taken)
        before = self.lines()
        r = run(self.root, "tools/migrate.py")
        self.assertIn("a voice file of this line would get a name that is already taken", r.stdout)
        self.apply()
        self.assertEqual(open(self.path("audio/fa/IMG003-1.mp3"), "rb").read(), taken)
        self.assertTrue(os.path.exists(self.path("audio/fa/IMG003_1.mp3")) and os.path.exists(self.path("audio/en/IMG003_1.mp3")))  # both languages stay
        st = self.read("scenario/story.txt")
        self.assertIn("id: IMG003-2", st)  # the other lines moved on
        self.assertNotIn("id: IMG003-1\n", st)
        after = self.lines()
        self.assertEqual([(r["img"], r["fa"], r["en"], r["fa_n"], r["en_n"]) for r in after if r["img"] != "IMG003"], [(r["img"], r["fa"], r["en"], r["fa_n"], r["en_n"]) for r in before if r["img"] != "IMG003"])
        self.assertEqual([r["en"] for r in after if r["img"] == "IMG003"], [r["en"] for r in before if r["img"] == "IMG003"])  # the line still plays its own voice

    def test_undo_after_a_collision_run_is_clean(self):
        with open(self.path("audio/fa/IMG003-1.mp3"), "wb") as fh:
            fh.write(b"x")
        before = mimo.snapshot(self.root)
        stamp = self.apply()
        run(self.root, "tools/migrate.py", "--undo", stamp)
        self.assertEqual(mimo.snapshot(self.root), before)


class DirtyGit(Base):
    def setUp(self):
        super().setUp()
        open(self.path(".gitignore"), "w").write("__pycache__/\n.kit/migrate-report-*.md\n")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        self.assertEqual(git(self.root, "commit", "-qm", "start").returncode, 0)

    def test_refuses_with_uncommitted_changes_and_changes_nothing(self):
        open(self.path("scenario/story.txt"), "a", encoding="utf-8").write("# edit\n")
        before = mimo.snapshot(self.root)
        r = run(self.root, "tools/migrate.py", "--apply")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("uncommitted changes", r.stderr)
        self.assertEqual(mimo.snapshot(self.root), before)
        self.assertFalse(os.path.exists(self.path(".engine-backup")))

    def test_dry_run_report_does_not_make_the_tree_dirty(self):
        self.assertEqual(run(self.root, "tools/migrate.py").returncode, 0)
        r = run(self.root, "tools/migrate.py", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertTrue(os.path.exists(self.path("audio/en/IMG001-1.mp3")))

    def test_allow_dirty_overrides(self):
        open(self.path("scenario/story.txt"), "a", encoding="utf-8").write("# edit\n")
        r = run(self.root, "tools/migrate.py", "--apply", "--allow-dirty")
        self.assertEqual(r.returncode, 0, r.stderr[-400:])


class PremiereFix(Base):
    def test_fix_repairs_an_old_xml_from_the_rename_log_and_reports_missing(self):
        orig = open(self.path("videos/final/EP01_EN_premiere.xml"), "rb").read()
        self.apply()
        shutil.copy(self.path(".engine-backup/migrate-%s/videos/final/EP01_EN_premiere.xml" % os.listdir(self.path(".engine-backup"))[0].split("migrate-")[1]), self.path("videos/final/EP01_EN_premiere.xml"))
        self.assertEqual(open(self.path("videos/final/EP01_EN_premiere.xml"), "rb").read(), orig)  # an old XML comes back (an editor re-exported it)
        r = run(self.root, "tools/premiere_check.py", "--fix", "videos/final/EP01_EN_premiere.xml")
        self.assertIn("8 path(s) repaired", r.stdout)
        self.assertIn(b"audio/en/IMG005-1.mp3", open(self.path("videos/final/EP01_EN_premiere.xml"), "rb").read())
        self.assertTrue(glob.glob(self.path(".engine-backup/premiere-fix-*/videos/final/EP01_EN_premiere.xml")))
        r = run(self.root, "tools/premiere_check.py", "--fix", "videos/final/EP01_EN_premiere.xml")
        self.assertIn("0 path(s) repaired", r.stdout)

    def test_fix_reports_a_file_that_is_missing(self):
        self.apply()
        os.remove(self.path("audio/en/IMG001-1.mp3"))
        r = run(self.root, "tools/premiere_check.py", "--fix", "videos/final/EP01_EN_premiere.xml")
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing", r.stdout)

    def test_log_chains_are_followed(self):
        os.makedirs(self.path(".kit"))
        open(self.path(".kit/renames.tsv"), "w").write("t1\ta/x.mp3\ta/y.mp3\nt2\ta/y.mp3\ta/z.mp3\n")
        self.assertEqual(premiere_check.read_renames(self.root), {"a/x.mp3": "a/z.mp3", "a/y.mp3": "a/z.mp3"})


class NewVoiceNames(Base):
    CODE = ("import sys, os, json; sys.path.insert(0,'tools'); import tts, media\n"
            "tts.synth=lambda *a: b'x'*6000; tts.load_key=lambda: 'k'; tts.voice_problem=lambda m,v: None\n"
            "it=dict(id='IMG003-1', scene='scene-01', speaker='راوی', voice='george', model='elevenlabs/eleven-v3', spoken='سلام', tone='آرام')\n"
            "r1=tts.make([it],'fa',force=True); v1=it['variant']; r2=tts.make([it],'fa',force=True); v2=it['variant']\n"
            "r3=tts.make([dict(it)],'fa')\n"
            "print(json.dumps([r1,r2,r3,v1,v2,sorted(os.listdir('audio/fa'))]))")

    def test_every_take_is_a_new_file_with_a_random_id_and_is_logged(self):
        r = run(self.root, code=self.CODE)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        r1, r2, r3, v1, v2, names = json.loads(r.stdout)
        self.assertEqual((r1, r2, r3), ({"IMG003-1": "ok"}, {"IMG003-1": "ok"}, {"IMG003-1": "cached"}))  # without force a line that has this model is skipped
        self.assertTrue(re.fullmatch(r"[0-9a-f]{8}", v1) and v1 != v2)
        self.assertIn("IMG003-1_%s.mp3" % v1, names)
        self.assertIn("IMG003-1_%s.mp3" % v2, names)
        rows = [l.split("\t") for l in self.read("audio/fa/voices.tsv").split("\n") if l]
        self.assertEqual(rows[0], ["file", "model", "voice", "tone", "time"])
        self.assertEqual([r[:4] for r in rows[1:]], [["IMG003-1_%s.mp3" % v, "elevenlabs/eleven-v3", "george", "آرام"] for v in (v1, v2)])
        self.assertTrue(re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", rows[1][4]))

    def test_the_new_take_is_read_and_becomes_the_chosen_voice(self):
        self.apply()  # the line has its image-based id now
        code = self.CODE.split("print(")[0] + ("import edits\nedits.pick_made([it], r2, 'fa')\n"
                                               "print(json.dumps([it['variant'], [v['name'] for v in media.audio_variants('fa','IMG003-1')]]))")
        r = run(self.root, code=code)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        v, names = json.loads(r.stdout)
        self.assertIn(v, names)
        self.assertIn("voice: fa=%s" % v, self.read("scenario/story.txt"))

    def test_a_new_dialogue_line_is_named_after_its_picture_and_the_number_is_never_reused(self):
        self.apply()
        code = ("import sys, json; sys.path.insert(0,'tools'); import lineedits, kitcore\n"
                "ls=kitcore.read_lines(kitcore.STORY); sid,after=lineedits.locate(ls, dict(image='IMG003', after=0), 'after')\n"
                "lineedits.add_line(ls, sid, after, 'say', 'علی', 'خط تازه')\n"
                "print(json.dumps([l for l in ls if l.startswith('id: IMG003')]))\n"
                "kitcore.write_lines(kitcore.STORY, ls)\n")
        code = code.replace("kitcore.write_lines(kitcore.STORY, ls)", "")
        self.assertEqual(sorted(json.loads(run(self.root, code=code).stdout)), ["id: IMG003-1", "id: IMG003-2", "id: IMG003-3"])  # the next free k of IMG003
        with open(self.path("audio/fa/archive/IMG003-9_ab12cd34.mp3"), "wb") as fh:  # the line that had this id is gone, its (archived) voice is not
            fh.write(b"x")
        self.assertIn("id: IMG003-10", json.loads(run(self.root, code=code).stdout))  # IMG003-9 is never given to a new line

    def test_a_line_above_the_first_picture_keeps_the_old_form(self):
        code = ("import sys, json; sys.path.insert(0,'tools'); import lineedits\n"
                "ls=['=== scene-01 | a | - ===', 'act: x', '[IMG001]']\n"
                "lineedits.add_line(ls, 'scene-01', 1, 'say', 'علی', 'متن')\n"
                "print(json.dumps(ls))")
        out = json.loads(run(self.root, code=code).stdout)
        self.assertTrue(any(re.fullmatch(r"id: L\d{3}", l) for l in out), out)


class Export(Base):
    def setUp(self):
        super().setUp()
        self.apply()

    def export(self, *a):
        r = run(self.root, "tools/premiere_export.py", *a)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        return r

    def test_timeline_from_story_order_with_relative_paths(self):
        self.export("--lang", "en")
        tree = ET.parse(self.path("videos/final/premiere_en.xml"))
        vclips = tree.getroot().findall("./sequence/media/video/track/clipitem")
        names = [c.find("name").text for c in vclips]
        self.assertEqual([n[:6] for n in names], ["IMG001", "IMG002", "IMG003", "IMG004", "IMG005", "IMG006", "IMG010"])  # story order, IMG000 left out
        self.assertEqual(names[0], "IMG001_hook_bench_passersby_edfa6fe0_2K.jpg")  # the picked version at its best quality
        starts = [int(c.find("start").text) for c in vclips]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(int(vclips[1].find("start").text), int(vclips[0].find("end").text))  # no gaps
        urls = [e.text for e in tree.getroot().iter("pathurl")]
        self.assertTrue(all(u.startswith("../../") for u in urls), urls[:3])
        aud = tree.getroot().findall("./sequence/media/audio/track/clipitem")
        self.assertEqual([c.find("name").text for c in aud][:4], ["IMG001-1.mp3", "IMG003-1.mp3", "IMG003-2.eleven-v3.mp3", "IMG005-1.mp3"])  # the voice the line picked
        self.assertEqual(int(aud[0].find("start").text), int(vclips[0].find("start").text))
        self.assertEqual(int(aud[0].find("end").text) - int(aud[0].find("start").text), int(vclips[0].find("end").text) - int(vclips[0].find("start").text))
        r = run(self.root, "tools/premiere_check.py", "videos/final/premiere_en.xml")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 missing, 0 with an absolute path", r.stdout)

    def test_a_picture_set_aside_is_left_out_and_a_line_without_voice_is_estimated(self):
        p = self.path("scenario/story.txt")
        st = open(p, encoding="utf-8").read().replace("[IMG004]\n", "[IMG004]\noff: yes\n")
        open(p, "w", encoding="utf-8").write(st)
        os.remove(self.path("audio/fa/IMG010-1.mp3"))
        self.export("--lang", "fa")
        root = ET.parse(self.path("videos/final/premiere_fa.xml")).getroot()
        names = [c.find("name").text[:6] for c in root.findall("./sequence/media/video/track/clipitem")]
        self.assertNotIn("IMG004", names)
        last = root.findall("./sequence/media/video/track/clipitem")[-1]
        self.assertEqual(last.find("name").text[:6], "IMG010")
        self.assertGreaterEqual(int(last.find("end").text) - int(last.find("start").text), 25)  # the estimate: at least a second

    def test_absolute_paths(self):
        self.export("--lang", "en", "--absolute", "-o", self.path("videos/final/abs_premiere.xml"))
        urls = [e.text for e in ET.parse(self.path("videos/final/abs_premiere.xml")).getroot().iter("pathurl")]
        self.assertTrue(all(u.startswith("file://localhost/") for u in urls))
        r = run(self.root, "tools/premiere_check.py", "videos/final/abs_premiere.xml")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_mp3_length_is_read_from_the_frames(self):
        sys.path.insert(0, os.path.join(os.path.dirname(HERE)))
        import premiere_export
        frame = b"\xff\xfb\x90\x64" + b"\x00" * 413  # MPEG-1 layer III, 128 kbit/s, 44.1 kHz: 417 bytes = 26.12 ms
        p = os.path.join(self.tmp, "t.mp3")
        open(p, "wb").write(b"ID3\x04\x00\x00\x00\x00\x00\x05xxxxx" + frame * 100)
        self.assertAlmostEqual(premiere_export.mp3_seconds(p), 100 * 1152 / 44100, places=3)
        open(p, "wb").write(b"not an mp3")
        self.assertIsNone(premiere_export.mp3_seconds(p))
        self.assertIsNone(premiere_export.mp3_seconds(os.path.join(self.tmp, "nothing.mp3")))


class Manifest(unittest.TestCase):
    def test_new_engine_files_are_listed(self):
        files = open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "ENGINE.txt"), encoding="utf-8").read().split("\n")
        for f in ("tools/migrate.py", "tools/premiere_export.py"):
            self.assertIn(f, files)
        self.assertNotIn("tools/export_premiere.py", files)  # a project's own file of that name must never be replaced by an update


if __name__ == "__main__":
    unittest.main()
