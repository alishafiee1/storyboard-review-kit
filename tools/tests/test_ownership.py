# -*- coding: utf-8 -*-
"""Unit tests of v1.17: every line belongs to the nearest [IMG] above it, voice choices and out-of-date flags live under their own dialogue line
(the old scene-level keys are still read), lines are addressed by picture, and structural edits keep a snapshot for undo.
Run:  python -m unittest discover -s tools/tests -p "test_*.py"   (no browser, no network; files only in temp folders)"""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import edits, history, jobs, lineedits, story  # noqa: E402
from kitcore import Conflict  # noqa: E402

LEGACY = open(os.path.join(HERE, "fixture", "story-legacy.txt"), encoding="utf-8").read().split("\n")


def lines():
    return list(LEGACY)


def scene(ls, sid):
    return next(s for s in story.story_scenes(ls) if s["id"] == sid)


def says(ls, sid):
    return [i for b in scene(ls, sid)["blocks"] for i in b["items"] if i["k"] == "say"]


def block_of(ls, img):
    """The text of one picture's lines (from its marker to the next marker or scene)."""
    sid, s, m, end = edits.image_range(ls, img)
    return ls[m:end]


class Ownership(unittest.TestCase):
    def test_consecutive_markers_are_separate_images_and_the_lines_belong_to_the_last(self):
        sc = scene(lines(), "scene-01")
        self.assertEqual([[i["id"] for i in b["images"]] for b in sc["blocks"]], [["IMG001"], ["IMG002"], ["IMG003"]])
        self.assertEqual([len(b["items"]) for b in sc["blocks"]], [0, 3, 1])
        self.assertEqual([i["img"] for b in sc["blocks"] for i in b["items"]], ["IMG002"] * 3 + ["IMG003"])

    def test_old_line_ids_resolve_exactly_as_before(self):
        # before: IMG001 + IMG002 shared one block, so its lines were named after the FIRST picture, counted inside the block
        self.assertEqual([i["id"] for i in says(lines(), "scene-01")], ["IMG001_1", "IMG001_2", "L001"])
        self.assertEqual([i["id"] for i in says(lines(), "scene-02")], ["IMG004_1"])

    def test_every_picture_knows_where_its_lines_end(self):
        ims = {i["id"]: i for b in scene(lines(), "scene-01")["blocks"] for i in b["images"]}
        self.assertEqual(ims["IMG001"]["end"], ims["IMG002"]["ln"])
        self.assertEqual(ims["IMG002"]["end"], ims["IMG003"]["ln"])

    def test_lines_above_the_first_picture_are_kept_as_scene_level_items_and_reported(self):
        sc = scene(lines(), "scene-02")
        top = sc["blocks"][0]
        self.assertEqual(top["images"], [])
        self.assertEqual([(i["k"], i["img"]) for i in top["items"]], [("act", None)])
        self.assertTrue(any("before the first [IMG]" in w["text"] for w in sc["warnings"]))
        self.assertEqual(scene(lines(), "scene-01")["warnings"], [])  # the old scene keys are not a warning

    def test_an_old_file_without_shared_blocks_reads_the_same_as_before(self):
        fx = open(os.path.join(HERE, "fixture", "story.txt"), encoding="utf-8").read().split("\n")
        sc = scene(fx, "scene-01")
        self.assertEqual([[i["id"] for i in b["images"]] for b in sc["blocks"]], [["IMG001"], ["IMG002"]])
        self.assertEqual([i["id"] for b in sc["blocks"] for i in b["items"] if i["k"] == "say"], ["IMG001_1", "IMG001_2", "IMG002_1"])


class VoiceKeys(unittest.TestCase):
    def test_old_scene_level_keys_are_read_and_mapped_onto_the_lines(self):
        ls = lines()
        sc = scene(ls, "scene-01")
        self.assertEqual(sc["voice_pick"], {"IMG001_1.fa": "eleven-v3", "IMG001_2.en": "default", "L001.fa": "eleven-v4"})
        first, second, third = says(ls, "scene-01")
        self.assertEqual(first["vstale"], ["fa"])  # the scene's «voice-stale: fa» reaches every dialogue line
        self.assertEqual(third["vstale"], ["en", "fa"])  # plus this line's own «voice-stale: en»
        self.assertEqual(third["voice"], {"fa": "eleven-v4"})
        self.assertEqual(sc["voice_stale"], {"fa", "en"})

    def test_a_line_s_own_choice_wins_over_the_old_scene_level_one(self):
        ls = lines()
        ls.insert(ls.index("voice-pick: IMG001_1.fa=eleven-v3, IMG001_2.en=default"), "voice-pick: L001.fa=eleven-v3")
        self.assertEqual(scene(ls, "scene-01")["voice_pick"]["L001.fa"], "eleven-v4")

    def test_writing_a_pick_goes_under_the_line_and_removes_the_migrated_entry(self):
        ls = lines()
        self.assertTrue(edits.set_line_pick(ls, "IMG001_1", "fa", "eleven-v4"))
        self.assertIn("voice-pick: IMG001_2.en=default", ls)  # the other old entry stays where it was
        self.assertNotIn("IMG001_1.fa", "\n".join(l for l in ls if l.startswith("voice-pick")))
        i = ls.index("say: راوی | این علیه. صبح‌ها بدون قهوه آدم نیست.")
        self.assertEqual(ls[i + 1:i + 3], ["en: This is Ali.", "voice: fa=eleven-v4"])  # after id: / en:
        sc = scene(ls, "scene-01")
        self.assertEqual(sc["voice_pick"]["IMG001_1.fa"], "eleven-v4")
        self.assertEqual(sc["voice_pick"]["IMG001_2.en"], "default")

    def test_the_last_old_entry_takes_the_whole_scene_line_with_it(self):
        ls = lines()
        edits.set_line_pick(ls, "IMG001_1", "fa", "default")
        edits.set_line_pick(ls, "IMG001_2", "en", "eleven-v3")
        self.assertFalse(any(l.startswith("voice-pick:") for l in ls))
        self.assertEqual(scene(ls, "scene-01")["voice_pick"], {"IMG001_1.fa": "default", "IMG001_2.en": "eleven-v3", "L001.fa": "eleven-v4"})

    def test_clearing_a_pick_removes_old_and_new_forms(self):
        ls = lines()
        edits.set_line_pick(ls, "L001", "fa", "")
        self.assertNotIn("voice: fa=eleven-v4", ls)
        self.assertNotIn("L001.fa", scene(ls, "scene-01")["voice_pick"])
        edits.set_line_pick(ls, "IMG001_1", "fa", "")
        self.assertNotIn("IMG001_1.fa", scene(ls, "scene-01")["voice_pick"])

    def test_a_pick_for_a_line_that_is_gone_is_ignored(self):
        ls = lines()
        self.assertFalse(edits.set_line_pick(ls, "NOPE_9", "fa", "x"))
        self.assertEqual(ls, LEGACY)

    def test_both_languages_in_one_voice_line_in_a_fixed_order(self):
        ls = lines()
        edits.set_line_pick(ls, "L001", "en", "default")
        self.assertIn("voice: fa=eleven-v4, en=default", ls)

    def test_clearing_one_line_s_flag_keeps_the_old_scene_flag_on_the_others(self):
        ls = lines()
        edits.set_stale(ls, "IMG001_2", ["fa"], False)
        a, b, c = says(ls, "scene-01")
        self.assertEqual((a["vstale"], b["vstale"], c["vstale"]), (["fa"], [], ["en", "fa"]))
        self.assertNotIn("voice-stale: fa", ls[:ls.index("[IMG001]")])  # the scene-level line is gone
        self.assertEqual(scene(ls, "scene-01")["legacy_stale"], set())

    def test_marking_a_line_touches_only_that_line(self):
        ls = lines()
        ls = [l for l in ls if l != "voice-stale: fa"]  # a project without the old flag
        edits.set_stale(ls, "IMG001_2", ["fa", "en"], True)
        a, b, c = says(ls, "scene-01")
        self.assertEqual((a["vstale"], b["vstale"], c["vstale"]), ([], ["en", "fa"], ["en"]))
        i = ls.index("say: علی (با تعجب) | این دیگه از کجا پیداش شد؟")
        self.assertEqual(ls[i + 1], "voice-stale: fa, en")

    def test_key_order_under_a_line_is_id_en_voice_stale(self):
        ls = lines()
        edits.set_say_attr(ls, ls.index("say: راوی | خطی که شناسهٔ خودش را دارد."), "format-issue", "x")
        edits.set_say_attr(ls, ls.index("say: راوی | خطی که شناسهٔ خودش را دارد."), "voice", "fa=a")
        i = ls.index("say: راوی | خطی که شناسهٔ خودش را دارد.")
        self.assertEqual([l.split(":")[0] for l in ls[i + 1:i + 6]], ["id", "en", "voice", "voice-stale", "format-issue"])

    def test_mark_stale_by_speaker_flags_only_that_speaker_s_lines(self):
        ls = [l for l in lines() if l != "voice-stale: fa"]
        edits.mark_stale(ls, speaker="علی")
        self.assertEqual([i["vstale"] for i in says(ls, "scene-01")], [[], ["en", "fa"], ["en"]])
        self.assertEqual([i["vstale"] for i in says(ls, "scene-02")], [["en", "fa"]])


class LineAddress(unittest.TestCase):
    def test_an_image_address_counts_from_the_marker(self):
        ls = lines()
        sid, idx = lineedits.locate(ls, dict(image="IMG003", index=1))
        s = story.scene_span(ls, sid)[0]
        self.assertEqual((sid, ls[s + idx]), ("scene-01", "say: راوی | خطی که شناسهٔ خودش را دارد."))

    def test_it_survives_the_picture_moving_to_another_scene(self):
        ls = lines()
        edits.move_scene(ls, "scene-02", -1)  # scene-02 now sits above scene-01: scene-relative numbers of scene-01 are unchanged, so move the picture itself
        i = ls.index("[IMG003]")
        block = ls[i:i + 6]
        del ls[i:i + 6]
        j = ls.index("[IMG004]")
        ls[j:j] = block
        sid, idx = lineedits.locate(ls, dict(image="IMG003", index=1))
        self.assertEqual(sid, "scene-02")
        s = story.scene_span(ls, sid)[0]
        self.assertEqual(ls[s + idx], "say: راوی | خطی که شناسهٔ خودش را دارد.")

    def test_old_scene_form_still_works(self):
        self.assertEqual(lineedits.locate(lines(), dict(scene="scene-01", index=5)), ("scene-01", 5))

    def test_out_of_range_or_bad_ids_are_refused(self):
        for d in (dict(image="IMG001", index=1), dict(image="IMG003", index=-1), dict(image="IMG9", index=0), dict(image="IMG077", index=0), dict(scene="x", index=1)):
            with self.assertRaises(ValueError):
                lineedits.locate(lines(), d)

    def test_editing_a_line_of_the_shared_block_flags_only_that_line(self):
        ls = [l for l in lines() if l != "voice-stale: fa"]
        sid, idx = lineedits.locate(ls, dict(image="IMG002", index=5))
        lineedits.edit_line(ls, sid, idx, "این دیگه از کجا پیداش شد؟", "متن تازه", "edit")
        self.assertEqual([i["vstale"] for i in says(ls, "scene-01")], [[], ["fa"], ["en"]])

    def test_a_new_dialogue_line_belongs_to_the_picture_it_was_added_to_and_starts_out_of_date(self):
        ls = lines()
        sid, after = lineedits.locate(ls, dict(image="IMG003", after=0), "after")
        lineedits.add_line(ls, sid, after, "say", "علی", "خط تازه")
        new = next(i for i in says(ls, "scene-01") if i["fa"] == "خط تازه")
        self.assertEqual(new["img"], "IMG003")
        self.assertTrue(new["id"] == "IMG003-1" and new["vstale"] == ["fa"])  # named after the picture, not L001
        self.assertEqual(new["stale_own"], ["fa"])
        self.assertEqual([i["id"] for i in says(ls, "scene-01")], ["IMG001_1", "IMG001_2", new["id"], "L001"])  # the old names were pinned, nothing moved

    def test_deleting_a_dialogue_line_takes_its_voice_keys_along(self):
        ls = lines()
        sid, idx = lineedits.locate(ls, dict(image="IMG003", index=1))
        lineedits.delete_line(ls, sid, idx, "خطی که شناسهٔ خودش را دارد.")
        text = "\n".join(ls)
        for gone in ("L001", "voice: fa=eleven-v4", "A line with its own id.", "voice-stale: en"):
            self.assertNotIn(gone, text)


class Snapshots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.story = os.path.join(self.tmp.name, "story.txt")
        self.old = (history.STORY, history.DIR, history.UNDONE)
        history.STORY, history.DIR, history.UNDONE = self.story, os.path.join(self.tmp.name, ".kit", "history"), os.path.join(self.tmp.name, ".kit", "undone")

    def tearDown(self):
        history.STORY, history.DIR, history.UNDONE = self.old
        self.tmp.cleanup()

    def edit(self, label, data):
        before = history.read_story()
        with open(self.story, "wb") as f:
            f.write(data)
        return history.record(label, before)

    def test_undo_puts_the_bytes_back_exactly_and_empties_the_history(self):
        first = "سلام\r\nبا CRLF و بدون خط آخر".encode("utf-8")
        with open(self.story, "wb") as f:
            f.write(first)
        self.assertTrue(self.edit("addimage", b"changed\n"))
        self.assertEqual([e["label"] for e in history.entries()], ["addimage"])
        history.undo()
        self.assertEqual(open(self.story, "rb").read(), first)
        self.assertEqual(history.entries(), [])
        with self.assertRaises(ValueError):
            history.undo()

    def test_an_edit_that_changed_nothing_leaves_no_snapshot(self):
        open(self.story, "wb").write(b"a\n")
        self.assertIsNone(self.edit("delete", b"a\n"))
        self.assertEqual(history.entries(), [])

    def test_the_last_30_are_kept_and_undo_walks_back_one_by_one(self):
        open(self.story, "wb").write(b"v0\n")
        for k in range(1, 36):
            self.edit("add", b"v%d\n" % k)
        self.assertEqual(len(history.entries()), 30)
        history.undo()
        self.assertEqual(open(self.story, "rb").read(), b"v34\n")
        history.undo()
        self.assertEqual(open(self.story, "rb").read(), b"v33\n")  # the second undo needs no force: the file is what the edit before produced

    def test_undo_refuses_when_the_file_changed_since_unless_forced_and_keeps_a_copy(self):
        open(self.story, "wb").write(b"a\n")
        self.edit("add", b"b\n")
        open(self.story, "wb").write(b"b plus a typo fix\n")
        with self.assertRaises(Conflict):
            history.undo()
        self.assertEqual(open(self.story, "rb").read(), b"b plus a typo fix\n")
        history.undo(force=True)
        self.assertEqual(open(self.story, "rb").read(), b"a\n")
        kept = [open(os.path.join(history.UNDONE, f), "rb").read() for f in os.listdir(history.UNDONE) if f.endswith(".txt")]
        self.assertEqual(kept, [b"b plus a typo fix\n"])

    def test_undo_refuses_when_the_page_knows_another_newest_snapshot(self):
        open(self.story, "wb").write(b"a\n")
        self.edit("add", b"b\n")
        with self.assertRaises(Conflict):
            history.undo(expect="19990101-000000-000000_add_00000000")
        history.undo(expect=history.entries()[-1]["id"])
        self.assertEqual(open(self.story, "rb").read(), b"a\n")

    def test_the_history_folder_keeps_itself_out_of_git(self):
        open(self.story, "wb").write(b"a\n")
        self.edit("add", b"b\n")
        self.assertEqual(open(os.path.join(history.DIR, ".gitignore"), encoding="utf-8").read().splitlines()[-1], "*")

    def test_structural_endpoints_are_the_ones_that_keep_a_snapshot(self):
        import api
        self.assertEqual(api.STRUCTURAL, {"/api/add", "/api/delete", "/api/addimage", "/api/addscene", "/api/scenemove", "/api/sceneoff", "/api/move", "/api/scenemark"})
        self.assertIn("/api/undo", api.ROUTES)


class StaleScope(unittest.TestCase):
    def test_voices_are_made_for_the_stale_lines_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "story.txt")
            open(p, "w", encoding="utf-8").write("\n".join(LEGACY))
            old = story.STORY
            story.STORY = p
            try:
                every = jobs.story_stale()
                self.assertEqual([(i["id"], i["stale"]) for i in every], [("IMG001_1", ["fa"]), ("IMG001_2", ["fa"]), ("L001", ["en", "fa"])])
                self.assertEqual([i["id"] for i in jobs.story_stale(image="IMG003")], ["L001"])
                self.assertEqual([i["id"] for i in jobs.story_stale(image="IMG002")], ["IMG001_1", "IMG001_2"])
                self.assertEqual([i["id"] for i in jobs.story_stale(scene="scene-02")], [])
            finally:
                story.STORY = old


if __name__ == "__main__":
    unittest.main()
