# -*- coding: utf-8 -*-
"""Unit tests of v1.19: moving pictures (also across scene headers), the scene markers (insert / remove / edit), adding a picture at a position or
with an existing id, four-digit picture ids, and that every one of these is a structural edit (snapshot + undo + 409 for a stale page).
Run:  python -m unittest discover -s tools/tests -p "test_*.py"   (no browser, no network; files only in temp folders)"""
import collections, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import api, edits, history, moves, story  # noqa: E402
from kitcore import Conflict, MARKER  # noqa: E402

LEGACY = open(os.path.join(HERE, "fixture", "story-legacy.txt"), encoding="utf-8").read().split("\n")

MODERN = """# پروژهٔ تست جابه‌جایی
tts-model: elevenlabs/eleven-v4-turbo

speaker: راوی | #1565c0 | george | گرم
speaker: علی | #ef6c00 | charlie

=== scene-00 | تامبنیل | - ===
[IMG000]

=== scene-01 | غار | 0:00-0:10 ===
env: غار تاریک
fx: نور لرزان
[IMG001]
pick: aaaa1111
note: یادداشت یک
act: علی وارد غار می‌شود.
say: راوی | خط یک.
id: IMG001-1
en: Line one.
voice: fa=bbbb2222
voice-stale: en
[IMG002]
status: redo
say: علی | خط دو.
id: IMG002-1
[IMG003]
note: بدون دیالوگ

=== scene-02 | دریا | 0:10-0:20 ===
env: ساحل
[IMG004]
say: راوی | خط چهار.
id: IMG004-1
voice: fa=cccc3333, en=dddd4444
[IMG005]
image-stale: yes
act: موج می‌آید.

=== scene-03 | شهر | 0:20-0:30 ===
off: yes
[IMG006]
say: علی | خط شش.
id: IMG006-1
"""


def modern():
    return MODERN.split("\n")


def nonblank(ls):
    return collections.Counter(l for l in ls if l.strip())


def layout(ls):
    return [(s["id"], [i["id"] for b in s["blocks"] for i in b["images"]]) for s in story.story_scenes(ls)]


def block(ls, img):
    sid, s, m, end = edits.image_range(ls, img)
    return [l for l in ls[m:end] if l.strip()]


class Move(unittest.TestCase):
    def mv(self, ids, **kw):
        ls = modern()
        res = moves.move_images(ls, ids, **kw)
        self.assertEqual(nonblank(ls), nonblank(modern()), "no line is lost or duplicated")
        self.assertNotIn("\n\n\n", "\n".join(ls))
        for sid in [s["id"] for s in story.story_scenes(ls)][1:]:
            self.assertIn("\n\n=== " + sid, "\n".join(ls))
        return ls, res

    def test_within_a_scene_the_picture_takes_everything_it_owns(self):
        ls, res = self.mv(["IMG001"], after="IMG002")
        self.assertEqual(res, "scene-01")
        self.assertEqual(layout(ls)[1], ("scene-01", ["IMG002", "IMG001", "IMG003"]))
        self.assertEqual(block(ls, "IMG001"), [l for l in block(modern(), "IMG001")])
        self.assertIn("voice: fa=bbbb2222", block(ls, "IMG001"))
        self.assertIn("pick: aaaa1111", block(ls, "IMG001"))

    def test_before_the_first_picture_and_after_the_last(self):
        ls, _ = self.mv(["IMG003"], before="IMG001")
        self.assertEqual(layout(ls)[1][1], ["IMG003", "IMG001", "IMG002"])
        ls, _ = self.mv(["IMG001"], after="IMG003")
        self.assertEqual(layout(ls)[1][1], ["IMG002", "IMG003", "IMG001"])
        ls, _ = self.mv(["IMG001"], to_end="scene-01")
        self.assertEqual(layout(ls)[1][1], ["IMG002", "IMG003", "IMG001"])

    def test_across_a_scene_header_the_picture_joins_the_destination_scene(self):
        ls, res = self.mv(["IMG003"], before="IMG004")
        self.assertEqual(res, "scene-02")
        self.assertEqual(layout(ls)[1:3], [("scene-01", ["IMG001", "IMG002"]), ("scene-02", ["IMG003", "IMG004", "IMG005"])])
        self.assertEqual(story.story_scenes(ls)[2]["env"][0]["text"], "ساحل")
        ls, res = self.mv(["IMG001"], to_end="scene-03")
        self.assertEqual(res, "scene-03")
        self.assertEqual(layout(ls)[3], ("scene-03", ["IMG006", "IMG001"]))
        self.assertEqual(block(ls, "IMG001")[0], "[IMG001]")

    def test_moving_the_last_picture_of_a_scene_keeps_one_blank_line_between_scenes(self):
        ls, _ = self.mv(["IMG005"], before="IMG001")
        self.assertEqual(layout(ls)[1:3], [("scene-01", ["IMG005", "IMG001", "IMG002", "IMG003"]), ("scene-02", ["IMG004"])])

    def test_a_scene_can_lose_all_its_pictures_and_keeps_its_header(self):
        ls, _ = self.mv(["IMG006"], to_end="scene-02")
        self.assertEqual(layout(ls)[3], ("scene-03", []))
        self.assertIn("off: yes", ls)

    def test_several_pictures_move_together_in_file_order(self):
        ls, res = self.mv(["IMG005", "IMG002"], before="IMG006")  # asked in the wrong order: they still keep the order they have in the file
        self.assertEqual(res, "scene-03")
        self.assertEqual(layout(ls)[1:], [("scene-01", ["IMG001", "IMG003"]), ("scene-02", ["IMG004"]), ("scene-03", ["IMG002", "IMG005", "IMG006"])])
        ls, _ = self.mv(["IMG001", "IMG003"], after="IMG004")
        self.assertEqual(layout(ls)[1:3], [("scene-01", ["IMG002"]), ("scene-02", ["IMG004", "IMG001", "IMG003", "IMG005"])])

    def test_onto_itself_or_to_where_it_already_is_changes_nothing(self):
        for kw in (dict(before="IMG002"), dict(after="IMG002")):
            ls, res = self.mv(["IMG002"], **kw)
            self.assertIsNone(res)
            self.assertEqual(ls, modern())
        ls, res = self.mv(["IMG002"], before="IMG003")  # already right before it
        self.assertIsNone(res)
        self.assertEqual(ls, modern())
        ls, res = self.mv(["IMG003"], to_end="scene-01")
        self.assertIsNone(res)
        self.assertEqual(ls, modern())

    def test_the_thumbnail_scene_stays_as_it_is(self):
        for ids, kw in ((["IMG000"], dict(before="IMG001")), (["IMG001"], dict(after="IMG000")), (["IMG001"], dict(to_end="scene-00")), (["IMG001"], dict(before="IMG000"))):
            with self.assertRaises(ValueError):
                moves.move_images(modern(), ids, **kw)
        ls, _ = self.mv(["IMG001"], before="IMG002")
        self.assertEqual(layout(ls)[0], ("scene-00", ["IMG000"]))

    def test_bad_requests_are_400_and_stale_ones_409(self):
        for kw in (dict(), dict(before="IMG001", after="IMG002"), dict(before="bad"), dict(to_end="nope")):
            with self.assertRaises(ValueError):
                moves.move_images(modern(), ["IMG002"], **kw)
        for ids in ([], ["IMG1"], ["IMG002", "IMG002"]):
            with self.assertRaises(ValueError):
                moves.move_images(modern(), ids, before="IMG001")
        with self.assertRaises(ValueError):
            moves.move_images(modern(), ["IMG001", "IMG002"], before="IMG002")  # the destination is one of the moved
        for ids, kw in ((["IMG777"], dict(before="IMG001")), (["IMG001"], dict(before="IMG777")), (["IMG001"], dict(to_end="scene-77"))):
            with self.assertRaises(Conflict):
                moves.move_images(modern(), ids, **kw)

    def test_a_marker_with_a_trailing_comment_block_and_blank_lines_inside_a_scene_survive(self):
        ls = modern()
        ls.insert(ls.index("[IMG002]"), "")  # a blank line between two pictures of one scene
        before = nonblank(ls)
        moves.move_images(ls, ["IMG001"], to_end="scene-02")
        self.assertEqual(nonblank(ls), before)
        self.assertEqual(layout(ls)[1:3], [("scene-01", ["IMG002", "IMG003"]), ("scene-02", ["IMG004", "IMG005", "IMG001"])])


class LegacyIds(unittest.TestCase):
    def ids(self, ls):
        return [(i["id"], i["img"], i["vstale"], sorted(i["voice"].items())) for s in story.story_scenes(ls) for b in s["blocks"] for i in b["items"] if i["k"] == "say"]

    def test_old_line_ids_and_scene_level_choices_travel_with_the_picture(self):
        ls = list(LEGACY)
        was = {i["id"]: i for s in story.story_scenes(ls) for b in s["blocks"] for i in b["items"] if i["k"] == "say"}
        self.assertEqual(sorted(was), ["IMG001_1", "IMG001_2", "IMG004_1", "L001"])
        moves.move_images(ls, ["IMG002"], to_end="scene-02")  # the shared block's lines belong to IMG002
        self.assertEqual(layout(ls)[1:], [("scene-01", ["IMG001", "IMG003"]), ("scene-02", ["IMG004", "IMG002"])])
        now = {i["id"]: i for s in story.story_scenes(ls) for b in s["blocks"] for i in b["items"] if i["k"] == "say"}
        self.assertEqual(sorted(now), sorted(was), "no voice changes its name")
        for k in was:
            self.assertEqual(now[k]["img"], was[k]["img"])
            self.assertEqual(now[k]["fa"], was[k]["fa"])
        sc = {s["id"]: s for s in story.story_scenes(ls)}
        self.assertEqual(sc["scene-02"]["voice_pick"]["IMG001_1.fa"], "eleven-v3")  # the choice came along (the old scene-level key is now under the line)
        self.assertEqual(now["IMG001_1"]["vstale"], ["fa"])
        self.assertEqual(now["IMG001_2"]["vstale"], ["fa"])
        self.assertEqual(now["L001"]["vstale"], ["en", "fa"])
        self.assertEqual(sc["scene-01"]["voice_pick"].get("IMG001_1.fa"), None)
        self.assertNotIn("voice-pick: IMG001_1.fa=eleven-v3, IMG001_2.en=default", "\n".join(ls))

    def test_an_image_put_in_the_middle_of_a_shared_block_does_not_rename_its_lines(self):
        ls = list(LEGACY)
        before = {i["id"]: i["fa"] for s in story.story_scenes(ls) for b in s["blocks"] for i in b["items"] if i["k"] == "say"}
        moves.add_image_at(ls, before="IMG001")  # a marker in front of the group would become its name base
        after = {i["id"]: i["fa"] for s in story.story_scenes(ls) for b in s["blocks"] for i in b["items"] if i["k"] == "say"}
        self.assertEqual(before, after)

    def test_the_multiset_of_lines_only_grows_by_the_explicit_ids(self):
        ls = list(LEGACY)
        was = nonblank(ls)
        moves.move_images(ls, ["IMG003"], to_end="scene-02")
        gone = was - nonblank(ls)
        new = nonblank(ls) - was
        self.assertTrue(all(k.startswith("voice-") for k in gone))
        self.assertTrue(all(k.startswith(("id:", "voice")) for k in new))


class SceneMark(unittest.TestCase):
    def test_insert_starts_a_scene_at_that_picture(self):
        ls = modern()
        res = moves.scene_mark(ls, "insert", dict(before="IMG002", title="عمق غار", env="تاریک تر"))
        self.assertEqual(res["scene"], "scene-04")  # the next free number; the order is the file order
        self.assertEqual(layout(ls)[1:4], [("scene-01", ["IMG001"]), ("scene-04", ["IMG002", "IMG003"]), ("scene-02", ["IMG004", "IMG005"])])
        self.assertIn("\n\n=== scene-04 | عمق غار | - ===\nenv: تاریک تر\n[IMG002]", "\n".join(ls))
        self.assertEqual(nonblank(ls) - nonblank(modern()), collections.Counter(["=== scene-04 | عمق غار | - ===", "env: تاریک تر"]))
        self.assertEqual(nonblank(modern()) - nonblank(ls), collections.Counter())

    def test_insert_refuses_scene_00_bad_titles_and_stale_images(self):
        with self.assertRaises(ValueError):
            moves.scene_mark(modern(), "insert", dict(before="IMG000", title="x"))
        with self.assertRaises(ValueError):
            moves.scene_mark(modern(), "insert", dict(before="IMG002", title="a|b"))
        with self.assertRaises(Conflict):
            moves.scene_mark(modern(), "insert", dict(before="IMG777", title="x"))
        with self.assertRaises(ValueError):
            moves.scene_mark(modern(), "nope", {})

    def test_remove_joins_the_pictures_to_the_previous_scene_and_needs_force_for_env(self):
        ls = modern()
        with self.assertRaises(ValueError):
            moves.scene_mark(ls, "remove", dict(scene="scene-02"))  # it has an env line
        self.assertEqual(ls, modern())
        moves.scene_mark(ls, "remove", dict(scene="scene-02", force=True))
        self.assertEqual(layout(ls)[1:], [("scene-01", ["IMG001", "IMG002", "IMG003", "IMG004", "IMG005"]), ("scene-03", ["IMG006"])])
        self.assertEqual(nonblank(modern()) - nonblank(ls), collections.Counter(["=== scene-02 | دریا | 0:10-0:20 ===", "env: ساحل"]))
        self.assertEqual(nonblank(ls) - nonblank(modern()), collections.Counter())
        self.assertNotIn("\n\n\n", "\n".join(ls))
        ls = modern()
        moves.scene_mark(ls, "insert", dict(before="IMG002", title="x"))
        moves.scene_mark(ls, "remove", dict(scene="scene-04"))  # no env / fx / off: no force needed
        self.assertEqual(layout(ls), layout(modern()))

    def test_remove_refuses_the_first_scene_the_thumbnail_scene_and_loose_text(self):
        for sid in ("scene-00", "scene-01"):
            with self.assertRaises(ValueError):
                moves.scene_mark(modern(), "remove", dict(scene=sid, force=True))
        ls = list(LEGACY)
        with self.assertRaises(ValueError):
            moves.scene_mark(ls, "remove", dict(scene="scene-02", force=True))  # an act: line above its first picture
        with self.assertRaises(Conflict):
            moves.scene_mark(modern(), "remove", dict(scene="scene-77"))
        ls = modern()
        with self.assertRaises(Conflict):
            moves.scene_mark(ls, "remove", dict(scene="scene-02", force=True, old_title="عنوان دیگر"))

    def test_remove_off_scene_needs_force_too(self):
        with self.assertRaises(ValueError):
            moves.scene_mark(modern(), "remove", dict(scene="scene-03"))

    def test_remove_keeps_voices_of_a_legacy_scene(self):
        ls = list(LEGACY)
        moves.scene_mark(ls, "insert", dict(before="IMG003", title="تازه"))
        ids = lambda: {i["id"]: (i["vstale"], i["voice"]) for s in story.story_scenes(ls) for b in s["blocks"] for i in b["items"] if i["k"] == "say"}
        now = ids()
        self.assertEqual(sorted(now), ["IMG001_1", "IMG001_2", "IMG004_1", "L001"])
        self.assertEqual(now["IMG001_1"][1], {"fa": "eleven-v3"})
        moves.scene_mark(ls, "remove", dict(scene="scene-03"))
        self.assertEqual(ids(), now)

    def test_edit_title_env_and_fx(self):
        ls = modern()
        moves.scene_mark(ls, "edit", dict(scene="scene-01", title="غار بزرگ", env="روز", fx="برش تند"))
        sc = story.story_scenes(ls)[1]
        self.assertEqual((sc["title"], sc["time"], [e["text"] for e in sc["env"]], sc["fx"]), ("غار بزرگ", "0:00-0:10", ["روز"], "برش تند"))
        moves.scene_mark(ls, "edit", dict(scene="scene-01", env="", fx=""))
        sc = story.story_scenes(ls)[1]
        self.assertEqual((sc["env"], sc["fx"]), ([], ""))
        self.assertEqual(layout(ls), layout(modern()))
        with self.assertRaises(Conflict):
            moves.scene_mark(ls, "edit", dict(scene="scene-01", title="x", old=dict(title="عنوان دیگر")))
        with self.assertRaises(Conflict):
            moves.scene_mark(ls, "edit", dict(scene="scene-77", title="x"))
        with self.assertRaises(ValueError):
            moves.scene_mark(ls, "edit", dict(scene="scene-01", title="  "))


class AddImage(unittest.TestCase):
    def test_after_and_before_a_picture_and_the_end_of_a_scene(self):
        ls = modern()
        a = moves.add_image_at(ls, after="IMG001")
        self.assertEqual(layout(ls)[1][1], ["IMG001", a, "IMG002", "IMG003"])
        b = moves.add_image_at(ls, before="IMG004")
        self.assertEqual(layout(ls)[2][1], [b, "IMG004", "IMG005"])
        c = moves.add_image_at(ls, after="IMG005")
        self.assertEqual(layout(ls)[2][1], [b, "IMG004", "IMG005", c])
        self.assertEqual((a, b, c), ("IMG007", "IMG008", "IMG009"))
        self.assertEqual(block(ls, "IMG001"), block(modern(), "IMG001"), "the new slot goes after everything the picture owns")
        self.assertEqual(nonblank(ls) - nonblank(modern()), collections.Counter(["[IMG007]", "[IMG008]", "[IMG009]"]))
        self.assertNotIn("\n\n\n", "\n".join(ls))

    def test_an_existing_id_is_placed_and_a_second_marker_is_refused(self):
        ls = modern()
        self.assertEqual(moves.add_image_at(ls, before="IMG002", image_id="IMG045"), "IMG045")
        self.assertEqual(layout(ls)[1][1], ["IMG001", "IMG045", "IMG002", "IMG003"])
        with self.assertRaises(Conflict):
            moves.add_image_at(ls, before="IMG002", image_id="IMG045")
        with self.assertRaises(ValueError):
            moves.add_image_at(ls, before="IMG002", image_id="IMG04")
        with self.assertRaises(Conflict):
            moves.add_image_at(ls, after="IMG777")
        self.assertEqual(moves.add_image_at(ls, scene="scene-02", image_id="IMG0451"), "IMG0451")
        self.assertEqual(layout(ls)[2][1][-1], "IMG0451")
        self.assertEqual(edits.next_image_id(ls), 452)  # IMG0451 counts, and is another picture than IMG045

    def test_four_digit_ids(self):
        self.assertTrue(MARKER.match("[IMG1000]"))
        self.assertIsNone(MARKER.match("[IMG10000]"))
        self.assertIsNone(MARKER.match("[IMG99]"))
        ls = modern()
        moves.add_image_at(ls, after="IMG005", image_id="IMG999")
        self.assertEqual(edits.next_image_id(ls), 1000)
        self.assertEqual(moves.add_image_at(ls, after="IMG999"), "IMG1000")
        self.assertEqual(edits.next_image_id(ls), 1001)
        self.assertEqual(moves.add_image_at(ls, after="IMG1000"), "IMG1001")
        self.assertEqual(layout(ls)[2][1][-3:], ["IMG999", "IMG1000", "IMG1001"])
        self.assertEqual(edits.image_range(ls, "IMG1000")[0], "scene-02")
        moves.move_images(ls, ["IMG1000"], before="IMG001")
        self.assertEqual(layout(ls)[1][1][0], "IMG1000")
        self.assertEqual(layout(ls)[2][1][-2:], ["IMG999", "IMG1001"])

    def test_adding_to_scene_00_is_refused(self):
        ls = modern()
        before = "\n".join(ls)
        with self.assertRaises(ValueError):
            moves.add_image_at(ls, scene="scene-00")
        with self.assertRaises(ValueError):
            moves.add_image_at(ls, after="IMG000")
        self.assertEqual("\n".join(ls), before)


class Endpoints(unittest.TestCase):
    """The API functions: a snapshot before each edit, undo gives the very same bytes back, a stale page gets 409 and leaves no snapshot."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.story = os.path.join(self.tmp.name, "story.txt")
        self.old = (history.STORY, history.DIR, history.UNDONE, api.STORY)
        history.STORY = api.STORY = self.story
        history.DIR, history.UNDONE = os.path.join(self.tmp.name, ".kit", "history"), os.path.join(self.tmp.name, ".kit", "undone")
        self.put(MODERN)

    def tearDown(self):
        history.STORY, history.DIR, history.UNDONE, api.STORY = self.old
        self.tmp.cleanup()

    def put(self, text):
        with open(self.story, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def raw(self):
        return open(self.story, "rb").read()

    def call(self, path, d):
        return api.handle(path, d)

    def test_each_one_keeps_a_snapshot_and_undo_restores_byte_for_byte(self):
        orig = self.raw()
        steps = [("/api/move", dict(ids=["IMG001"], after="IMG004")), ("/api/scenemark", dict(op="insert", before="IMG005", title="تازه")),
                 ("/api/scenemark", dict(op="edit", scene="scene-04", title="تازه ۲")), ("/api/scenemark", dict(op="remove", scene="scene-04")),
                 ("/api/addimage", dict(after="IMG004")), ("/api/addimage", dict(scene="scene-01", id="IMG045"))]
        seen = [orig]
        for path, d in steps:
            self.assertTrue(self.call(path, d)["ok"])
            self.assertNotEqual(self.raw(), seen[-1], path)
            seen.append(self.raw())
        self.assertEqual([e["label"] for e in history.entries()], ["move", "scenemark", "scenemark", "scenemark", "addimage", "addimage"])
        for want in reversed(seen[:-1]):
            history.undo()
            self.assertEqual(self.raw(), want)
        self.assertEqual(self.raw(), orig)

    def test_a_no_op_move_and_a_failed_edit_leave_no_snapshot(self):
        self.assertEqual(self.call("/api/move", dict(ids=["IMG002"], before="IMG002"))["moved"], 0)
        for path, d, exc in (("/api/move", dict(ids=["IMG777"], before="IMG001"), Conflict), ("/api/move", dict(ids=["IMG001"]), ValueError),
                             ("/api/scenemark", dict(op="remove", scene="scene-77"), Conflict), ("/api/addimage", dict(scene="scene-77"), ValueError),
                             ("/api/addimage", dict(after="IMG001", before="IMG002"), ValueError), ("/api/addimage", dict(scene="scene-01", id="IMG001"), Conflict),
                             ("/api/addimage", dict(after="IMG001", id="IMG002"), Conflict)):
            with self.assertRaises(exc, msg=(path, d)):
                self.call(path, d)
        self.assertEqual(self.raw(), MODERN.encode("utf-8"))
        self.assertEqual(history.entries(), [])

    def test_the_move_answer_names_the_destination_scene(self):
        r = self.call("/api/move", dict(ids=["IMG002", "IMG003"], to_end_of_scene="scene-02"))
        self.assertEqual((r["moved"], r["scene"]), (2, "scene-02"))
        r = self.call("/api/move", {"ids": ["IMG001"], "before": None, "after": "IMG006"})
        self.assertEqual(r["scene"], "scene-03")
        self.assertEqual(layout(open(self.story, encoding="utf-8").read().split("\n"))[3], ("scene-03", ["IMG006", "IMG001"]))

    def test_the_endpoints_are_structural(self):
        self.assertLessEqual({"/api/move", "/api/scenemark", "/api/addimage"}, api.STRUCTURAL)

    def test_the_old_forms_of_addimage_still_work(self):
        self.assertEqual(self.call("/api/addimage", dict(scene="scene-01"))["id"], "IMG007")
        self.assertIn("[IMG003]\nnote: بدون دیالوگ\n[IMG007]\n\n=== scene-02", self.raw().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
