# -*- coding: utf-8 -*-
"""Unit tests of v2.4 tools/settings.py: the key goes to .env only (other lines stay, the key is never sent back), the Downloads folder and the
watcher switch go to kit-config.json (other keys stay). Everything runs in a throw-away folder."""
import json, os, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import flowname  # noqa: E402
import settings  # noqa: E402

KEY = "sk-or-v1-abcdef1234567890"


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srk-set-")
        self.patches = [mock.patch.object(settings, "ROOT", self.tmp), mock.patch.object(settings, "ENV", os.path.join(self.tmp, ".env")),
                        mock.patch.object(settings, "CFG", os.path.join(self.tmp, "kit-config.json")), mock.patch.object(flowname, "ROOT", self.tmp), mock.patch.object(settings.voices, "ROOT", self.tmp),
                        mock.patch.dict(os.environ, {"STORYBOARD_NO_WATCH": ""}, clear=False)]
        for p in self.patches:
            p.start()
        os.environ.pop("OPENROUTER_API_KEY", None)
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def read(self, n):
        return open(os.path.join(self.tmp, n), encoding="utf-8").read()

    def test_key_is_written_to_env_keeping_other_lines_and_never_returned(self):
        open(os.path.join(self.tmp, ".env"), "w").write("OTHER=1\nOPENROUTER_API_KEY=old-old-old\n")
        r = settings.save({"key": "  " + KEY + " "})
        self.assertEqual(self.read(".env").splitlines(), ["OTHER=1", "OPENROUTER_API_KEY=" + KEY])
        self.assertTrue(r["key_set"])
        self.assertEqual(r["key_source"], ".env")
        self.assertNotIn(KEY, json.dumps(r))
        self.assertNotIn(KEY, json.dumps(settings.get()))

    def test_bad_keys_are_refused_and_change_nothing(self):
        for bad in ("", "short", "has space inside-key", "line\nbreak-key-1234"):
            with self.assertRaises(ValueError):
                settings.save({"key": bad})
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".env")))
        self.assertFalse(settings.get()["key_set"])

    def test_environment_key_wins_and_a_note_says_so(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "from-the-environment-1"}):
            r = settings.save({"key": KEY})
            self.assertEqual(r["key_source"], "env")
            self.assertTrue(r["note"])

    def test_config_keeps_other_keys_and_validates_the_folder(self):
        open(os.path.join(self.tmp, "kit-config.json"), "w").write(json.dumps({"name_pattern": "x", "match_slug": False}))
        dl = os.path.join(self.tmp, "dl")
        with self.assertRaises(ValueError):
            settings.save({"downloads": dl})
        os.makedirs(dl)
        r = settings.save({"downloads": dl, "watch_downloads": False})
        cfg = json.loads(self.read("kit-config.json"))
        self.assertEqual(cfg, {"name_pattern": "x", "match_slug": False, "downloads": dl, "watch_downloads": False})
        self.assertFalse(r["watch"])
        self.assertEqual(r["downloads_custom"], dl)
        settings.save({"downloads": "", "watch_downloads": True})  # empty = back to the default folder
        cfg = json.loads(self.read("kit-config.json"))
        self.assertNotIn("downloads", cfg)
        self.assertTrue(settings.watch_enabled())

    def test_watcher_default_on_off_switch_and_test_guard(self):
        self.assertTrue(settings.watch_enabled())  # on by default
        settings.save({"watch_downloads": False})
        self.assertFalse(settings.watch_enabled())
        with self.assertRaises(ValueError):
            settings.save({"watch_downloads": "yes"})
        os.remove(os.path.join(self.tmp, "kit-config.json"))
        with mock.patch.dict(os.environ, {"STORYBOARD_NO_WATCH": "1"}):
            self.assertFalse(settings.watch_enabled())  # the tests' guard
            settings.save({"watch_downloads": True})
            self.assertTrue(settings.watch_enabled())  # an explicit true still wins

    def test_test_key_without_a_key_does_not_call_out(self):
        with mock.patch.object(settings.voices, "_get") as g:
            self.assertFalse(settings.test_key()["ok"])
            g.assert_not_called()
        settings.save({"key": KEY})
        with mock.patch.object(settings.voices, "_get", return_value={"data": {"limit_remaining": 4.256}}):
            r = settings.test_key()
        self.assertTrue(r["ok"])
        self.assertNotIn(KEY, json.dumps(r))


class ToneTests(unittest.TestCase):
    """add_tone / remove_tone of voices/voice-config.json (a throw-away config)."""

    def setUp(self):
        import voices
        self.voices = voices
        self.tmp = tempfile.mkdtemp(prefix="srk-tone-")
        for name, val in (("CONFIG", os.path.join(self.tmp, "voice-config.json")), ("CATALOG", os.path.join(self.tmp, "catalog.txt"))):
            p = mock.patch.object(voices, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_add_checks_the_name_and_the_tag_and_refuses_a_twin(self):
        v = self.voices
        tid = v.add_tone("  غمگین ", "[sad]")
        t = next(x for x in v.load_config()["tones"] if x["id"] == tid)
        self.assertEqual((t["fa"], t["tag"]), ("غمگین", "[sad]"))
        self.assertEqual(v.tone_tags("غمگین")[0], ["[sad]"])
        for bad in (("غمگین", "[sad]"), ("آهسته", ""), ("", "[x]"), ("a|b", ""), ("x" * 31, ""), ("خوب", "sad"), ("خوب", "[bad tag!]")):
            with self.assertRaises(ValueError, msg=str(bad)):
                v.add_tone(*bad)
        self.assertEqual(v.add_tone("ساده", ""), "c2")  # a tone with no tag is fine (it sends nothing)

    def test_remove_drops_only_that_tone(self):
        v = self.voices
        tid = v.add_tone("غمگین", "[sad]")
        before = len(v.load_config()["tones"])
        v.remove_tone(tid)
        self.assertEqual(len(v.load_config()["tones"]), before - 1)
        self.assertFalse(v.tone_tags("غمگین")[1])  # no longer known
        with self.assertRaises(ValueError):
            v.remove_tone(tid)


if __name__ == "__main__":
    unittest.main()


class NewProjectInAnAssistantFolder(unittest.TestCase):
    """`update.py --new .` must work in a folder where the AI assistant already made .git or .claude, but not in a folder with real files."""

    def fake_fetch(self):
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("kit-main/ENGINE.txt", "review.html\n")
            z.writestr("kit-main/VERSION", "9.9.9\n")
            z.writestr("kit-main/review.html", "<html></html>")
            z.writestr("kit-main/starter/CLAUDE.md", "# x\n")
        return zipfile.ZipFile(io.BytesIO(buf.getvalue())), "kit-main/"

    def test_git_and_claude_folders_do_not_block_it_but_other_files_do(self):
        import update
        d = tempfile.mkdtemp(prefix="srk-new-")
        os.makedirs(os.path.join(d, ".git"))
        os.makedirs(os.path.join(d, ".claude"))
        with mock.patch.object(update, "fetch", self.fake_fetch):
            update.new_project(d)
            self.assertTrue(os.path.exists(os.path.join(d, "review.html")) and os.path.exists(os.path.join(d, "CLAUDE.md")))
            with self.assertRaises(SystemExit):
                update.new_project(d)  # now it holds files
