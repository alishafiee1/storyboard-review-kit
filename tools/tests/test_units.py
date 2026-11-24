# -*- coding: utf-8 -*-
"""Fast unit tests of the pure logic (no browser, no server, no network, no files of the real project are touched).
Run:  python -m unittest discover -s tools/tests -p "test_*.py"
The browser tests (python tools/tests/run.py) cover the page; these cover the text editing rules in milliseconds."""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import edits, media, pack, premiere_check, story  # noqa: E402
from kitcore import Conflict  # noqa: E402

FIXTURE = open(os.path.join(HERE, "fixture", "story.txt"), encoding="utf-8").read().split("\n")


def lines():
    return list(FIXTURE)


def scene(ls, sid):
    return next(s for s in story.story_scenes(ls) if s["id"] == sid)


class Parsing(unittest.TestCase):
    def test_scenes_and_images(self):
        sc = story.story_scenes(lines())
        self.assertEqual([s["id"] for s in sc], ["scene-00", "scene-01", "scene-02"])
        self.assertEqual([i["id"] for b in sc[1]["blocks"] for i in b["images"]], ["IMG001", "IMG002"])
        self.assertIn("fa", sc[1]["voice_stale"])

    def test_dialogue_and_translation(self):
        items = [i for b in scene(lines(), "scene-01")["blocks"] for i in b["items"] if i["k"] == "say"]
        self.assertEqual(items[0]["sp"], "راوی")
        self.assertTrue(items[0]["en"].startswith("This is Ali"))
        self.assertEqual(items[1]["tone"], "با تعجب")

    def test_speakers(self):
        sp = story.parse_speakers(lines())
        self.assertEqual([s["name"] for s in sp], ["راوی", "علی", "تست"])
        self.assertEqual(sp[2]["voice"], "aura-2-thalia-en")

    def test_clean_helpers(self):
        self.assertEqual(story.clean_name("  علی   رضا "), "علی رضا")
        with self.assertRaises(ValueError):
            story.clean_name("a|b")


class SceneEdits(unittest.TestCase):
    def test_set_aside_and_back_is_lossless(self):
        ls = lines()
        edits.set_scene_off(ls, "scene-02", True)
        self.assertTrue(scene(ls, "scene-02")["off"])
        self.assertIn("و روز تمام شد.", "\n".join(ls))
        edits.set_scene_off(ls, "scene-02", False)
        self.assertEqual(ls, FIXTURE)

    def test_move_scene_swaps_blocks_only(self):
        ls = lines()
        edits.move_scene(ls, "scene-02", -1)
        self.assertEqual([s["id"] for s in story.story_scenes(ls)], ["scene-00", "scene-02", "scene-01"])
        self.assertEqual(sorted(l for l in ls if l.strip()), sorted(l for l in FIXTURE if l.strip()))
        edits.move_scene(ls, "scene-02", 1)
        self.assertEqual("\n".join(ls).strip(), "\n".join(FIXTURE).strip())
        with self.assertRaises(ValueError):
            edits.move_scene(lines(), "scene-01", -1)  # the thumbnail stays first

    def test_add_scene_after_a_scene(self):
        ls = lines()
        sid = edits.add_scene(ls, "scene-01", "تازه", 2)
        ids = [s["id"] for s in story.story_scenes(ls)]
        self.assertEqual(sid, ids[2])
        self.assertEqual(ids.index(sid), ids.index("scene-01") + 1)
        with self.assertRaises(ValueError):
            edits.add_scene(ls, "scene-01", "a|b", 1)
        with self.assertRaises(ValueError):
            edits.add_scene(ls, "scene-01", "x", 99)

    def test_voice_pick_set_and_clear(self):
        ls = lines()
        edits.set_voice_picks(ls, "scene-01", {"IMG001_1.fa": "eleven-v3"})
        self.assertEqual(scene(ls, "scene-01")["voice_pick"], {"IMG001_1.fa": "eleven-v3"})
        edits.set_voice_picks(ls, "scene-01", {"IMG001_1.fa": ""})
        self.assertEqual(scene(ls, "scene-01")["voice_pick"], {})


class LineEdits(unittest.TestCase):
    def test_edit_keeps_the_key(self):
        ls = lines()
        sc = scene(ls, "scene-01")
        it = next(i for b in sc["blocks"] for i in b["items"] if i["k"] == "say")
        edits.edit_line(ls, "scene-01", it["ln"], it["fa"], "متن تازه", "edit")
        self.assertTrue(any(l.startswith("say: راوی | متن تازه") for l in ls))
        self.assertIn("fa", scene(ls, "scene-01")["voice_stale"])

    def test_edit_refuses_when_text_changed_outside(self):
        ls = lines()
        sc = scene(ls, "scene-01")
        it = next(i for b in sc["blocks"] for i in b["items"] if i["k"] == "say")
        with self.assertRaises(Conflict):
            edits.edit_line(ls, "scene-01", it["ln"], "something else", "x", "edit")


class Prompts(unittest.TestCase):
    PROMPTS = ["=== IMG001 ===", "[REFS TO ATTACH: A| B]", "Prompt one.", "", "=== IMG002 ===", "Prompt two.", ""]

    def test_refs_line_is_replaced_added_removed(self):
        ls = list(self.PROMPTS)
        self.assertTrue(edits.set_prompt_refs(ls, "IMG001", ["A"]))
        self.assertEqual(ls[1], "[REFS TO ATTACH: A]")
        self.assertFalse(edits.set_prompt_refs(ls, "IMG001", ["A"]))
        self.assertTrue(edits.set_prompt_refs(ls, "IMG002", ["B", "A"]))
        self.assertEqual(ls[5], "[REFS TO ATTACH: B| A]")
        self.assertTrue(edits.set_prompt_refs(ls, "IMG001", []))
        self.assertEqual(ls[:3], ["=== IMG001 ===", "Prompt one.", ""])
        self.assertEqual(story.parse_prompts(ls)["IMG002"]["refs"], ["B", "A"])

    def test_new_prompt_is_created(self):
        ls = list(self.PROMPTS)
        self.assertTrue(edits.set_prompt_refs(ls, "IMG009", ["A"]))
        self.assertEqual(story.parse_prompts(ls)["IMG009"]["refs"], ["A"])


class Media(unittest.TestCase):
    def test_variant_tag(self):
        self.assertEqual(media.variant_tag("elevenlabs/eleven-v4-turbo"), "eleven-v4-turbo")
        self.assertEqual(media.variant_tag("x-ai/grok-voice-tts-1.0"), "grok-voice-tts-1-0")

    def test_image_state_prefers_the_pick(self):
        scan = dict(versions=[dict(name="a.png", src="images/scenes/a.png"), dict(name="b.png", src="images/scenes/b.png")])
        newest = media.image_state(dict(pick="", status=""), scan)
        self.assertEqual((newest["src"], newest["picked"], newest["status"]), ("images/scenes/b.png", "", ""))
        chosen = media.image_state(dict(pick="a.png", status=""), scan)
        self.assertEqual((chosen["src"], chosen["status"]), ("images/scenes/a.png", "ok"))


class Handoff(unittest.TestCase):
    def test_pack_skips_heavy_and_private_files(self):
        for rel in (".env", "videos/final/EP01_FA_renders/x.mp4", "videos/final/EP01_FA_preview.mp4", "images/archive/a.png",
                    "audio/fa/archive/a.mp3", "videos/clips/c.mp4", "audio/_tests/t.mp3"):
            self.assertTrue(pack.skip(rel), rel)
        for rel in ("scenario/story.txt", "images/scenes/IMG001.png", "premiere/media/overlays/a.mov", "audio/fa/IMG001_1.mp3"):
            self.assertFalse(pack.skip(rel), rel)
        self.assertFalse(pack.skip("videos/clips/c.mp4", clips=True))

    def test_premiere_paths(self):
        self.assertTrue(premiere_check.is_absolute("file://localhost/D%3a/x.png"))
        self.assertTrue(premiere_check.is_absolute("D:\\x\\y.png"))
        self.assertFalse(premiere_check.is_absolute("../images/a.png"))
        base = os.path.join(os.sep, "proj", "premiere")
        self.assertEqual(premiere_check.resolve("../images/a%20b.png", base), os.path.normpath(os.path.join(base, "..", "images", "a b.png")))


class PageScripts(unittest.TestCase):
    """The page scripts share one global scope (no modules), so two files must never declare the same top-level name,
    and review.html must load them in an order where a file only needs names from files that load before it or are used later at run time."""
    UI = os.path.join(os.path.dirname(HERE), "ui")

    def declared(self):
        import re
        out = {}
        for f in sorted(os.listdir(self.UI)):
            if f.endswith(".js"):
                for line in open(os.path.join(self.UI, f), encoding="utf-8"):
                    m = re.match(r"(?:async )?function\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)", line)
                    if m:
                        out.setdefault(m.group(1) or m.group(2), []).append(f)
        return out

    def test_no_name_is_declared_twice(self):
        dup = {k: v for k, v in self.declared().items() if len(v) > 1}
        self.assertEqual(dup, {}, "declared in more than one file (they would overwrite each other)")

    def test_every_script_file_is_loaded_by_the_page(self):
        import re
        html = open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "review.html"), encoding="utf-8").read()
        loaded = re.findall(r'src="tools/ui/([^"]+\.js)"', html)
        self.assertEqual(sorted(loaded), sorted(f for f in os.listdir(self.UI) if f.endswith(".js")))


if __name__ == "__main__":
    unittest.main()
