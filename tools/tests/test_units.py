# -*- coding: utf-8 -*-
"""Fast unit tests of the pure logic (no browser, no server, no network, no files of the real project are touched).
Run:  python -m unittest discover -s tools/tests -p "test_*.py"
The browser tests (python tools/tests/run.py) cover the page; these cover the text editing rules in milliseconds."""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import edits, lineedits, media, pack, premiere_check, promptedits, story  # noqa: E402
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
        lineedits.edit_line(ls, "scene-01", it["ln"], it["fa"], "متن تازه", "edit")
        self.assertTrue(any(l.startswith("say: راوی | متن تازه") for l in ls))
        self.assertIn("fa", scene(ls, "scene-01")["voice_stale"])

    def test_edit_refuses_when_text_changed_outside(self):
        ls = lines()
        sc = scene(ls, "scene-01")
        it = next(i for b in sc["blocks"] for i in b["items"] if i["k"] == "say")
        with self.assertRaises(Conflict):
            lineedits.edit_line(ls, "scene-01", it["ln"], "something else", "x", "edit")


class Prompts(unittest.TestCase):
    PROMPTS = ["=== IMG001 ===", "[REFS TO ATTACH: A| B]", "Prompt one.", "", "=== IMG002 ===", "Prompt two.", ""]

    def test_refs_line_is_replaced_added_removed(self):
        ls = list(self.PROMPTS)
        self.assertTrue(promptedits.set_prompt_refs(ls, "IMG001", ["A"]))
        self.assertEqual(ls[1], "[REFS TO ATTACH: A]")
        self.assertFalse(promptedits.set_prompt_refs(ls, "IMG001", ["A"]))
        self.assertTrue(promptedits.set_prompt_refs(ls, "IMG002", ["B", "A"]))
        self.assertEqual(ls[5], "[REFS TO ATTACH: B| A]")
        self.assertTrue(promptedits.set_prompt_refs(ls, "IMG001", []))
        self.assertEqual(ls[:3], ["=== IMG001 ===", "Prompt one.", ""])
        self.assertEqual(story.parse_prompts(ls)["IMG002"]["refs"], ["B", "A"])

    def test_new_prompt_is_created(self):
        ls = list(self.PROMPTS)
        self.assertTrue(promptedits.set_prompt_refs(ls, "IMG009", ["A"]))
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


class OldImports(unittest.TestCase):
    def test_serve_still_exports_what_older_project_scripts_import(self):
        import serve
        for name in ("ROOT", "STORY", "spoken_lines", "audio_path", "clean_spoken", "story_scenes", "archive_dir", "archive_move",
                     "pick_made", "variant_tag", "parse_speakers", "read_lines"):
            self.assertTrue(hasattr(serve, name), name)


class PageModules(unittest.TestCase):
    """The page is ES modules: main.js is the entry and every file says what it needs with import. These checks catch the usual slips
    (importing a name nobody exports, a file the page never reaches, a name declared twice) without opening a browser."""
    UI = os.path.join(os.path.dirname(HERE), "ui")

    def read(self, f):
        with open(os.path.join(self.UI, f), encoding="utf-8") as fh:
            return fh.read()

    def files(self):
        return sorted(f for f in os.listdir(self.UI) if f.endswith(".js"))

    def exports(self, f):
        """Names exported by a file: `export function a`, `export const a = 1, b = 2`, ... (declarators after a comma count too)."""
        import re
        text = self.read(f)
        out = set(re.findall(r"^export (?:async )?(?:function|class)\s+([A-Za-z_$][\w$]*)", text, re.M))
        for m in re.finditer(r"^export (?:const|let|var)\s+", text, re.M):
            i, depth, start = m.end(), 0, m.end()
            parts = []
            while i < len(text):  # brackets only (quotes and regex literals are ignored on purpose: they are balanced in this code base)
                c = text[i]
                if c in "([{":
                    depth += 1
                elif c in ")]}":
                    depth -= 1
                elif c == "," and depth == 0:
                    parts.append(text[start:i])
                    start = i + 1
                elif c == ";" and depth == 0:
                    parts.append(text[start:i])
                    break
                i += 1
            for part in parts:
                n = re.match(r"\s*([A-Za-z_$][\w$]*)", part)
                if n:
                    out.add(n.group(1))
        return out

    def imports(self, f):
        import re
        out = []
        for names, src in re.findall(r"^import \{([^}]*)\} from '\./([\w.]+)';", self.read(f), re.M):
            out.append(([n.strip() for n in names.split(",") if n.strip()], src))
        out += [([], src) for src in re.findall(r"^import '\./([\w.]+)';", self.read(f), re.M)]
        return out

    def test_every_import_is_exported_by_its_file(self):
        for f in self.files():
            for names, src in self.imports(f):
                self.assertIn(src, self.files(), "%s imports a file that does not exist: %s" % (f, src))
                for n in names:
                    self.assertIn(n, self.exports(src), "%s imports %s from %s, which does not export it" % (f, n, src))

    def test_every_file_is_reached_from_main(self):
        seen, todo = set(), ["main.js"]
        while todo:
            f = todo.pop()
            if f not in seen:
                seen.add(f)
                todo += [src for _, src in self.imports(f)]
        self.assertEqual(sorted(seen), self.files())

    def test_the_page_loads_only_main(self):
        import re
        html = open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "review.html"), encoding="utf-8").read()
        self.assertEqual(re.findall(r'<script[^>]*src="([^"]+)"', html), ["tools/ui/main.js"])
        self.assertIn('type="module"', html)

    def test_no_name_is_exported_twice(self):
        seen = {}
        for f in self.files():
            for n in self.exports(f):
                self.assertNotIn(n, seen, "%s is exported by both %s and %s" % (n, seen.get(n), f))
                seen[n] = f

    def test_files_stay_small(self):
        for f in self.files():
            self.assertLess(len(self.read(f).split("\n")), 700, f + " is getting too big: split it")


if __name__ == "__main__":
    unittest.main()
