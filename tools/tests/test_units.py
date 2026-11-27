# -*- coding: utf-8 -*-
"""Fast unit tests of the pure logic (no browser, no server, no network, no files of the real project are touched).
Run:  python -m unittest discover -s tools/tests -p "test_*.py"
The browser tests (python tools/tests/run.py) cover the page; these cover the text editing rules in milliseconds."""
import os, sys, unittest
from unittest import mock

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
        scan = dict(versions=[dict(name="a.png", src="images/scenes/a.png", id="a.png", files=["images/scenes/a.png"]),
                              dict(name="b.png", src="images/scenes/b.png", id="b.png", files=["images/scenes/b.png"])])
        newest = media.image_state(dict(id="IMG001", pick="", status=""), scan)
        self.assertEqual((newest["src"], newest["picked"], newest["status"]), ("images/scenes/b.png", "", ""))
        chosen = media.image_state(dict(id="IMG001", pick="a.png", status=""), scan)
        self.assertEqual((chosen["src"], chosen["status"]), ("images/scenes/a.png", "ok"))


class Handoff(unittest.TestCase):
    def test_pack_skips_heavy_and_private_files(self):
        for rel in (".env", "videos/final/EP01_FA_renders/x.mp4", "videos/final/EP01_FA_preview.mp4", "images/archive/a.png",
                    "audio/fa/archive/a.mp3", "videos/clips/c.mp4", "audio/_tests/t.mp3"):
            self.assertTrue(pack.skip(rel), rel)
        for rel in ("scenario/story.txt", "images/scenes/IMG001.png", "premiere/media/overlays/a.mov", "audio/fa/IMG001_1.mp3"):
            self.assertFalse(pack.skip(rel), rel)
        self.assertFalse(pack.skip("videos/clips/c.mp4", clips=True))

    def test_pack_keeps_only_the_chosen_premiere_package(self):
        pkg = "videos/final/EP02_FA_premiere_package"
        others = ["premiere", "videos/final/EP01_FA_premiere_package", pkg]
        with mock.patch.object(pack, "package_dirs", return_value=others):
            for rel in ("old_export_premiere.xml", "premiere/EP01_FA_premiere.xml", "videos/final/EP01_FA_premiere_package/x.xml",
                        "videos/final/EP01_FA_premiere_package/media/a.mov", "premiere/media/b.mov"):
                self.assertTrue(pack.skip(rel, pkg=pkg), rel)
            for rel in (pkg + "/EP02_FA_premiere.xml", pkg + "/media/a.mov", "scenario/story.txt", "images/scenes/IMG001.png", "audio/fa/IMG001-1.mp3"):
                self.assertFalse(pack.skip(rel, pkg=pkg), rel)
        self.assertFalse(pack.skip("old_export_premiere.xml"))  # no package folder found: the old rule (every XML stays)

    def test_pack_help_does_not_build_a_zip(self):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "pack.py"), "--help"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--list", r.stdout)
        self.assertIn("--package", r.stdout)

    def test_premiere_paths(self):
        self.assertTrue(premiere_check.is_absolute("file://localhost/D%3a/x.png"))
        self.assertTrue(premiere_check.is_absolute("D:\\x\\y.png"))
        self.assertFalse(premiere_check.is_absolute("../images/a.png"))
        base = os.path.join(os.sep, "proj", "premiere")
        self.assertEqual(premiere_check.resolve("../images/a%20b.png", base), os.path.normpath(os.path.join(base, "..", "images", "a b.png")))


class StableLineIds(unittest.TestCase):
    """A dialogue line keeps its id (and so its voice files) when other lines are added, deleted or move."""

    def ids(self, ls, sid="scene-01"):
        return [i["id"] for b in scene(ls, sid)["blocks"] for i in b["items"] if i["k"] == "say"]

    def first_say_ln(self, ls, sid="scene-01"):
        return next(i["ln"] for b in scene(ls, sid)["blocks"] for i in b["items"] if i["k"] == "say")

    def test_explicit_id_wins_over_position(self):
        ls = lines()
        ls.insert(FIXTURE.index("say: راوی | این علیه. صبح‌ها بدون قهوه آدم نیست.") + 1, "id: L042")
        self.assertEqual(self.ids(ls)[:2], ["L042", "IMG001_2"])

    def test_old_files_without_ids_still_read_as_before(self):
        self.assertEqual(self.ids(lines()), ["IMG001_1", "IMG001_2", "IMG002_1"])

    def test_adding_a_line_in_the_middle_keeps_every_old_id(self):
        ls = lines()
        before = self.ids(ls)
        lineedits.add_line(ls, "scene-01", self.first_say_ln(ls), "say", "راوی", "یک خط تازه")
        after = self.ids(ls)
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual([i for i in after if i in before], before)  # nobody was renamed
        self.assertEqual(after[1], "IMG001-1")  # the new one sits second and is named after its picture (the first free k of IMG001)
        self.assertIn("id: IMG001-1", ls)

    def test_deleting_a_line_keeps_the_ids_of_the_others(self):
        ls = lines()
        first = next(i for b in scene(ls, "scene-01")["blocks"] for i in b["items"] if i["k"] == "say")
        lineedits.delete_line(ls, "scene-01", first["ln"], first["fa"])
        self.assertEqual(self.ids(ls), ["IMG001_2", "IMG002_1"])  # IMG001_2 did not become IMG001_1
        self.assertNotIn("id: IMG001_1", ls)

    def test_new_translation_goes_after_the_id_line(self):
        ls = lines()
        lineedits.add_line(ls, "scene-01", self.first_say_ln(ls), "say", "راوی", "بدون ترجمه")
        new = next(i for b in scene(ls, "scene-01")["blocks"] for i in b["items"] if i["k"] == "say" and i["fa"] == "بدون ترجمه")
        lineedits.edit_line(ls, "scene-01", new["ln"], "", "no translation", "add_en")
        again = next(i for b in scene(ls, "scene-01")["blocks"] for i in b["items"] if i["k"] == "say" and i["fa"] == "بدون ترجمه")
        self.assertEqual(again["en"], "no translation")
        start = story.scene_span(ls, "scene-01")[0]  # ln counts from the scene header
        self.assertTrue(ls[start + again["ln"] + 1].startswith("id:") and ls[start + again["ln"] + 2].startswith("en:"))

    def test_an_id_line_nobody_owns_is_reported(self):
        ls = lines()
        ls.insert(FIXTURE.index("env: غروب، کنار دریا.") + 1, "id: L001")
        self.assertTrue(any("id: L001" in w["text"] for w in scene(ls, "scene-02")["warnings"]))

    def test_next_id_skips_numbers_already_used(self):
        self.assertEqual(lineedits.next_line_id(["id: L003", "voice-pick: L007.fa=x"]), "L008")

    def test_moving_line_within_picture_preserves_chunk_and_id(self):
        ls = lines()
        say1_idx = next(i for i, l in enumerate(ls) if "این علیه" in l)
        ls.insert(say1_idx + 1, "id: IMG001-custom")
        ls.insert(say1_idx + 2, "voice: fa=take1")
        ls.insert(say1_idx + 3, "voice-stale: fa")
        ls.insert(say1_idx + 4, "format-issue: مشکل لحن")
        say2_idx = next(i for i, l in enumerate(ls) if "این دیگه از کجا" in l)
        lineedits.move_line(ls, say1_idx, after=say2_idx)
        say_idx = next(i for i, l in enumerate(ls) if "این علیه" in l)
        self.assertEqual(ls[say_idx + 1].strip(), "id: IMG001-custom")
        self.assertEqual(ls[say_idx + 2].strip(), "voice: fa=take1")
        self.assertEqual(ls[say_idx + 3].strip(), "voice-stale: fa")
        self.assertEqual(ls[say_idx + 4].strip(), "format-issue: مشکل لحن")
        self.assertEqual(ls[say_idx + 5].strip(), "en: This is Ali. He is not a person before coffee.")

    def test_moving_line_to_neighboring_picture_and_onto_image(self):
        ls = lines()
        lineedits.move_line(ls, {"image": "IMG001", "index": 4}, to_image="IMG002")
        sc = scene(ls, "scene-01")
        b2_items = sc["blocks"][1]["items"]
        self.assertTrue(any("این علیه" in it["fa"] for it in b2_items))
        moved_it = next(it for it in b2_items if "این علیه" in it["fa"])
        self.assertEqual(moved_it["id"], "IMG001_1")

    def test_moving_line_refuses_invalid_targets(self):
        ls = lines()
        with self.assertRaises(ValueError):
            lineedits.move_line(ls, {"image": "IMG001", "index": 3}, to_image="IMG003")
        with self.assertRaises(ValueError):
            lineedits.move_line(ls, {"image": "IMG001", "index": 3}, to_image="IMG000")
        with self.assertRaises(ValueError):
            lineedits.move_line(ls, {"image": "IMG001", "index": 3}, before={"image": "IMG001", "index": 3})


class OldFormatHint(unittest.TestCase):
    def check(self, story, audio=()):
        import tempfile, update
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "story.txt"), "w", encoding="utf-8").write(story)
            os.makedirs(os.path.join(d, "audio", "fa"))
            for n in audio:
                open(os.path.join(d, "audio", "fa", n), "wb").close()
            return update.old_format_reasons(d)

    def test_current_project_gets_no_hint(self):
        self.assertEqual(self.check("=== scene-01 | a | - ===\n[IMG001]\nsay: x | y\nid: IMG001-1\nvoice-stale: fa\n", ["IMG001-1.mp3"]), [])

    def test_old_forms_are_named(self):
        r = self.check("=== scene-01 | a | - ===\nvoice-stale: fa\n[IMG001]\nsay: x | y\n", ["IMG001_1.mp3"])
        self.assertEqual(len(r), 3, r)


class GitIgnoreRules(unittest.TestCase):
    def test_starter_gitignore_matches_the_updater_and_keeps_pictures_and_voices(self):
        import update
        starter = open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "starter", ".gitignore"), encoding="utf-8").read().splitlines()
        self.assertEqual([l for l in starter if l and not l.startswith("#")], update.IGNORE)
        self.assertIn(update.MARK, starter)
        for kept in ("audio/", "images/", "audio", "images"):
            self.assertNotIn(kept, update.IGNORE)

    def test_updater_adds_the_rules_once_and_never_again(self):
        import tempfile, update
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".gitignore")
            open(p, "w", encoding="utf-8").write("node_modules/\n")
            update.ensure_ignore(d)
            first = open(p, encoding="utf-8").read()
            self.assertIn("videos/", first)
            self.assertTrue(first.startswith("node_modules/"))
            open(p, "w", encoding="utf-8").write(first.replace("videos/\n", ""))  # the project removes a line
            update.ensure_ignore(d)
            self.assertNotIn("videos/", open(p, encoding="utf-8").read().splitlines())


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


class SketchbookShell(unittest.TestCase):
    """Rules of the v2.0 look that need no browser: offline font, icons that exist, no emoji in the chrome, the theme tokens."""
    KIT = os.path.dirname(os.path.dirname(HERE))
    UI = os.path.join(KIT, "tools", "ui")

    def text(self, *parts):
        with open(os.path.join(self.KIT, *parts), encoding="utf-8") as fh:
            return fh.read()

    def test_the_font_is_bundled_with_its_license_and_shipped(self):
        files = [l.strip() for l in self.text("ENGINE.txt").splitlines() if l.strip() and not l.startswith("#")]
        css = self.text("tools", "ui", "css", "base.css")
        import re
        urls = re.findall(r'url\("\.\./(fonts/[^"]+)"\)', css)
        self.assertGreaterEqual(len(urls), 3)
        for u in urls:
            self.assertIn("tools/ui/" + u, files, u + " is not in ENGINE.txt")
            with open(os.path.join(self.UI, *u.split("/")), "rb") as fh:
                self.assertEqual(fh.read(4), b"wOF2", u + " is not a woff2 file")
        self.assertIn("tools/ui/fonts/OFL.txt", files)
        self.assertIn("SIL OPEN FONT LICENSE", self.text("tools", "ui", "fonts", "OFL.txt").upper())
        self.assertNotIn("googleapis", css + self.text("review.html"), "the page must work offline: no web fonts from the internet")

    def test_every_icon_that_is_asked_for_exists(self):
        import re
        icons = set(re.findall(r"^  (\w+): '", self.text("tools", "ui", "icons.js"), re.M))
        self.assertGreaterEqual(len(icons), 20)
        asked = set(re.findall(r'data-ic="(\w+)"', self.text("review.html")))
        for f in os.listdir(self.UI):
            if f.endswith(".js"):
                asked |= set(re.findall(r"\bic\('(\w+)'", self.text("tools", "ui", f)))
        self.assertFalse(asked - icons, "icons used but not drawn: %s" % sorted(asked - icons))

    def test_icons_are_fine_lines(self):
        src = self.text("tools", "ui", "icons.js")
        self.assertIn('stroke-width="1.5"', src)
        self.assertIn('stroke="currentColor"', src)
        self.assertIn('fill="none"', src)

    def test_no_emoji_in_the_page_chrome(self):
        import re
        emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u23E9-\u23FA]")
        for rel in [("review.html",)] + [("tools", "ui", f) for f in sorted(os.listdir(self.UI)) if f.endswith(".js")]:
            text = self.text(*rel)
            for n, line in enumerate(text.split("\n"), 1):
                if line.lstrip().startswith(("/*", "//", "*")):
                    continue
                self.assertIsNone(emoji.search(re.sub(r"title=\"[^\"]*\"", "", line)), "%s:%d has an emoji or pictograph: %s" % ("/".join(rel), n, line.strip()[:80]))

    def test_theme_tokens_follow_the_spec(self):
        import re
        css = self.text("tools", "ui", "css", "base.css")
        for token, value in (("--paper", "#F3EEE4"), ("--ink", "#2A2723"), ("--line", "#C9BFAE"), ("--accent", "#B55A42"), ("--approve", "#5E7356"),
                             ("--wash-olive", "#D5DBC8"), ("--overlay", "rgba(42,39,35,.28)")):
            self.assertRegex(css, r"%s:\s*%s" % (token, re.escape(value)))
        self.assertIn("'Vazirmatn'", css)

    def test_the_shell_has_no_text_tabs_and_has_the_drawer(self):
        html = self.text("review.html")
        for gone in ("tabR", "tabF", "tabS", 'id="filter"', 'id="speed"', 'id="jump"', 'id="fab"', 'id="pSpeed"'):
            self.assertNotIn(gone, html)
        for need in ('id="menuBtn"', 'id="drawer"', 'id="nav"', 'id="lang"', 'dir="rtl"'):
            self.assertIn(need, html)

    def test_speeds_list_shared_and_no_drawer_speed_panel(self):
        js = self.text("tools", "ui", "player.js")
        self.assertIn("export const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];", js)
        drawer_js = self.text("tools", "ui", "drawer.js")
        self.assertNotIn("paintSpeed", drawer_js)
        self.assertNotIn("data-speed", drawer_js)
        self.assertNotIn("#pSpeed", drawer_js)
        self.assertNotIn("SPEEDS", drawer_js)


if __name__ == "__main__":
    unittest.main()
