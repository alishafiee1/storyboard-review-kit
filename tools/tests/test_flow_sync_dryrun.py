# -*- coding: utf-8 -*-
"""Unit tests for tools/flow_sync.py and tools/flow_state.py (Phase A).

No live browser, network, or Playwright binaries required.
Mocks CDP and Playwright objects to verify dry-run safety and edge cases.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure tools/ is on sys.path
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import kitcore
import flow_state
import flow_sync


class TestLazyImport(unittest.TestCase):
    """Verify flow_sync and flow_state import without playwright installed."""

    def test_imports_succeed_when_playwright_is_blocked(self):
        cmd = [
            sys.executable,
            "-c",
            "import sys; sys.modules['playwright']=None; sys.modules['playwright.sync_api']=None; sys.path.insert(0,'tools'); import flow_sync, flow_state",
        ]
        res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Import failed with stderr: {res.stderr}")

    def test_connect_cdp_fails_gracefully_when_playwright_missing(self):
        with patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
            stderr_buf = io.StringIO()
            with patch("sys.stderr", stderr_buf):
                pw, browser = flow_sync.connect_cdp("http://127.0.0.1:9222")
            self.assertIsNone(pw)
            self.assertIsNone(browser)
            self.assertIn("Playwright is not installed", stderr_buf.getvalue())


class TestFlowSelectors(unittest.TestCase):
    """Verify tools/flow_selectors.json data integrity and loader behavior."""

    def test_flow_selectors_json_is_valid_and_has_required_keys(self):
        sel_path = os.path.join(TOOLS_DIR, "flow_selectors.json")
        self.assertTrue(os.path.isfile(sel_path), f"Missing {sel_path}")
        with open(sel_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("version", data)
        self.assertIn("flow_url_pattern", data)
        self.assertIn("prompt_box", data)
        self.assertIn("submit_button", data)
        self.assertIn("ingredients_button", data)
        self.assertIn("ingredient_search_input", data)
        self.assertIn("Add ingredients to the prompt box", data["ingredients_button"])

    def test_load_selectors_falls_back_on_malformed_json(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            bad_json_path = os.path.join(tmp_dir, "bad_selectors.json")
            with open(bad_json_path, "w", encoding="utf-8") as fh:
                fh.write("{ bad json: ")
            stderr_buf = io.StringIO()
            with patch("sys.stderr", stderr_buf):
                selectors = flow_sync.load_selectors(path=bad_json_path)
            self.assertEqual(selectors["prompt_box"], flow_sync.BUILTIN_SELECTORS["prompt_box"])
            self.assertIn("Warning", stderr_buf.getvalue())
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestFlowState(unittest.TestCase):
    """Verify state tracking, schema version 2, atomic saves, and timing logs."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_state_initializes_schema_v2(self):
        state = flow_state.load_state(project_dir=self.tmp)
        self.assertEqual(state["schemaVersion"], 2)
        self.assertIsNone(state["last_run"])
        self.assertEqual(state["items"], {})

    def test_attempt_id_monotonic_and_unique(self):
        id1 = flow_state.generate_attempt_id()
        id2 = flow_state.generate_attempt_id()
        self.assertTrue(id1.startswith("att_"))
        self.assertTrue(id2.startswith("att_"))
        self.assertNotEqual(id1, id2)

    def test_state_atomic_save_and_reload(self):
        state = flow_state.default_state()
        att_id = flow_state.generate_attempt_id()
        flow_state.record_item_state(
            state,
            output_name="STYLE_ANCHOR",
            prompt_hash="hash123",
            status="dry_run_verified",
            attempt_id=att_id,
            refs=["CH_ALI"]
        )
        flow_state.save_state(state, project_dir=self.tmp)

        state_path = os.path.join(self.tmp, ".kit", "flow-state.json")
        self.assertTrue(os.path.isfile(state_path))
        self.assertFalse(os.path.isfile(state_path + ".tmp"))

        loaded = flow_state.load_state(project_dir=self.tmp)
        self.assertEqual(loaded["schemaVersion"], 2)
        self.assertIn("STYLE_ANCHOR", loaded["items"])
        item = loaded["items"]["STYLE_ANCHOR"]
        self.assertEqual(item["output_name"], "STYLE_ANCHOR")
        self.assertEqual(item["prompt_hash"], "hash123")
        self.assertEqual(item["attempt_id"], att_id)
        self.assertEqual(item["status"], "dry_run_verified")
        self.assertEqual(item["refs"], ["CH_ALI"])
        self.assertIsNotNone(loaded["last_run"])

    def test_timing_log_records_steps(self):
        with flow_state.time_step("test_step", project_dir=self.tmp):
            pass

        log_path = os.path.join(self.tmp, ".kit", "flow-timing.log")
        self.assertTrue(os.path.isfile(log_path))
        with open(log_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("test_step", lines[0])
        self.assertIn("ok", lines[0])


class TestHashStability(unittest.TestCase):
    """Verify prompt SHA-256 hash stability and normalization."""

    def test_prompt_hash_stability_across_line_endings(self):
        text_lf = "cinematic lighting, warm atmosphere\nsecond line"
        text_crlf = "cinematic lighting, warm atmosphere\r\nsecond line"
        h1 = flow_state.compute_prompt_hash(text_lf)
        h2 = flow_state.compute_prompt_hash(text_crlf)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_prompt_hash_strips_refs_directive(self):
        raw = "[REFS TO ATTACH: STYLE_ANCHOR| CH_ALI]\nCinematic portrait of Ali"
        stripped = "Cinematic portrait of Ali"
        self.assertEqual(flow_state.compute_prompt_hash(raw), flow_state.compute_prompt_hash(stripped))

    def test_prompt_hash_changes_on_content_change(self):
        h1 = flow_state.compute_prompt_hash("photo of a cat")
        h2 = flow_state.compute_prompt_hash("photo of a dog")
        self.assertNotEqual(h1, h2)


class TestQueueCalculation(unittest.TestCase):
    """Verify queue parsing, ordering, and skip/generate rules (R5)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "prompts"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "scenario"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "images", "scenes", "b01"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "images", "refs", "STYLE"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, ".kit"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_prompts(self, content):
        with open(os.path.join(self.tmp, "prompts", "prompts.txt"), "w", encoding="utf-8") as fh:
            fh.write(content)

    def _write_story(self, content):
        with open(os.path.join(self.tmp, "scenario", "story.txt"), "w", encoding="utf-8") as fh:
            fh.write(content)

    def test_queue_ordering_references_first_then_scenes(self):
        # Prompts in mixed order: IMG001, then STYLE_ANCHOR, then IMG002
        prompts = (
            "=== IMG001 ===\n[REFS TO ATTACH: STYLE_ANCHOR]\nScene 1 prompt\n\n"
            "=== STYLE_ANCHOR ===\nStyle prompt\n\n"
            "=== IMG002 ===\nScene 2 prompt\n"
        )
        self._write_prompts(prompts)
        self._write_story("=== scene-01 | Test | 0:00 ===\n[IMG001]\n[IMG002]\n")

        queue, summary = flow_sync.compute_queue(self.tmp)
        names = [item["output_name"] for item in queue]
        self.assertEqual(names, ["STYLE_ANCHOR", "IMG001", "IMG002"])
        self.assertEqual(summary["total"], 3)

    def test_skip_rule_existing_image_and_matching_hash_and_not_stale(self):
        self._write_prompts("=== IMG001 ===\nScene 1 prompt\n")
        self._write_story("=== scene-01 | Test | 0:00 ===\n[IMG001]\n")
        # Existing image file
        img_path = os.path.join(self.tmp, "images", "scenes", "b01", "IMG001_scene_12345678.jpg")
        with open(img_path, "wb") as fh:
            fh.write(b"fake image bytes")

        # Matching state
        h = flow_state.compute_prompt_hash("Scene 1 prompt")
        state = flow_state.default_state()
        flow_state.record_item_state(state, "IMG001", h, "dry_run_verified")
        flow_state.save_state(state, project_dir=self.tmp)

        queue, summary = flow_sync.compute_queue(self.tmp)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["action"], "skip")
        self.assertEqual(queue[0]["reason"], "existing_and_unchanged")
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["queued"], 0)

    def test_generate_rule_image_missing(self):
        self._write_prompts("=== IMG002 ===\nScene 2 prompt\n")
        self._write_story("=== scene-01 | Test | 0:00 ===\n[IMG002]\n")

        queue, summary = flow_sync.compute_queue(self.tmp)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["action"], "generate")
        self.assertEqual(queue[0]["reason"], "image_missing")
        self.assertEqual(summary["queued"], 1)

    def test_generate_rule_image_stale_flag(self):
        self._write_prompts("=== IMG001 ===\nScene 1 prompt\n")
        self._write_story("=== scene-01 | Test | 0:00 ===\n[IMG001]\nimage-stale: yes\n")
        img_path = os.path.join(self.tmp, "images", "scenes", "b01", "IMG001_scene_12345678.jpg")
        with open(img_path, "wb") as fh:
            fh.write(b"fake image bytes")

        h = flow_state.compute_prompt_hash("Scene 1 prompt")
        state = flow_state.default_state()
        flow_state.record_item_state(state, "IMG001", h, "dry_run_verified")
        flow_state.save_state(state, project_dir=self.tmp)

        queue, summary = flow_sync.compute_queue(self.tmp)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["action"], "generate")
        self.assertEqual(queue[0]["reason"], "image_stale")

    def test_skip_rule_approved_pick_preserved_even_if_marked_stale(self):
        # An item with an approved pick in story.txt and an existing image is skipped unless its prompt hash changed
        self._write_prompts("=== IMG001 ===\nScene 1 prompt\n")
        self._write_story("=== scene-01 | Test | 0:00 ===\n[IMG001]\npick: 12345678\nimage-stale: yes\n")
        img_path = os.path.join(self.tmp, "images", "scenes", "b01", "IMG001_scene_12345678.jpg")
        with open(img_path, "wb") as fh:
            fh.write(b"fake image bytes")

        h = flow_state.compute_prompt_hash("Scene 1 prompt")
        state = flow_state.default_state()
        flow_state.record_item_state(state, "IMG001", h, "dry_run_verified")
        flow_state.save_state(state, project_dir=self.tmp)

        queue, summary = flow_sync.compute_queue(self.tmp)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["action"], "skip")
        self.assertEqual(queue[0]["reason"], "approved_pick")

    def test_generate_rule_approved_pick_regenerates_when_prompt_hash_changed(self):
        self._write_prompts("=== IMG001 ===\nNew modified prompt text\n")
        self._write_story("=== scene-01 | Test | 0:00 ===\n[IMG001]\npick: 12345678\n")
        img_path = os.path.join(self.tmp, "images", "scenes", "b01", "IMG001_scene_12345678.jpg")
        with open(img_path, "wb") as fh:
            fh.write(b"fake image bytes")

        old_h = flow_state.compute_prompt_hash("Old prompt text")
        state = flow_state.default_state()
        flow_state.record_item_state(state, "IMG001", old_h, "dry_run_verified")
        flow_state.save_state(state, project_dir=self.tmp)

        queue, summary = flow_sync.compute_queue(self.tmp)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["action"], "generate")
        self.assertEqual(queue[0]["reason"], "prompt_hash_changed")

    def test_filter_only_single_item(self):
        prompts = "=== IMG001 ===\nPrompt 1\n\n=== IMG002 ===\nPrompt 2\n"
        self._write_prompts(prompts)
        self._write_story("=== scene-01 | Test | 0:00 ===\n[IMG001]\n[IMG002]\n")

        queue, summary = flow_sync.compute_queue(self.tmp, only_name="IMG002")
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["output_name"], "IMG002")
        self.assertEqual(summary["total"], 1)

    def test_scene_item_regex_matches_img_and_not_reference(self):
        scene_re = kitcore.BOOK_RULES["story"]["item_re"]
        self.assertTrue(scene_re.match("IMG001"))
        self.assertTrue(scene_re.match("IMG045"))
        self.assertTrue(scene_re.match("IMG1000"))
        self.assertFalse(scene_re.match("STYLE_ANCHOR"))
        self.assertFalse(scene_re.match("CH_ALI"))
        self.assertFalse(scene_re.match("REF_01"))


class TestDryRunBrowserFakes(unittest.TestCase):
    """Verify CDP dry-run execution, selector validation, and zero generation calls."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "prompts"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "scenario"), exist_ok=True)
        with open(os.path.join(self.tmp, "prompts", "prompts.txt"), "w", encoding="utf-8") as fh:
            fh.write("=== IMG001 ===\nSample prompt\n")
        with open(os.path.join(self.tmp, "scenario", "story.txt"), "w", encoding="utf-8") as fh:
            fh.write("=== scene-01 | Test | 0:00 ===\n[IMG001]\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create_fake_page(self, url="https://flow.google.com/project/abc", title="Flow - Test",
                          missing_selectors=None):
        missing = set(missing_selectors or [])
        page = MagicMock()
        page.url = url
        page.title.return_value = title

        def fake_query_selector(selector):
            if selector in missing or any(m in selector for m in missing):
                return None
            el = MagicMock()
            el.click = MagicMock(side_effect=AssertionError("FAIL: click() was called in dry-run!"))
            return el

        page.query_selector.side_effect = fake_query_selector
        page.click = MagicMock(side_effect=AssertionError("FAIL: page.click() was called in dry-run!"))
        return page

    def test_find_flow_tab_matches_flow_url(self):
        page1 = MagicMock()
        page1.url = "https://www.google.com"
        page2 = MagicMock()
        page2.url = "https://flow.google.com/project/123"

        browser = MagicMock()
        context = MagicMock()
        context.pages = [page1, page2]
        browser.contexts = [context]

        found = flow_sync.find_flow_tab(browser, flow_sync.BUILTIN_SELECTORS)
        self.assertIs(found, page2)

    def test_find_flow_tab_warns_on_google_login(self):
        page1 = MagicMock()
        page1.url = "https://accounts.google.com/signin/v2/identifier"

        browser = MagicMock()
        context = MagicMock()
        context.pages = [page1]
        browser.contexts = [context]

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            found = flow_sync.find_flow_tab(browser, flow_sync.BUILTIN_SELECTORS)
        self.assertIsNone(found)
        self.assertIn("Flow login required; navigate to project page", stderr_buf.getvalue())

    def test_find_flow_tab_lists_open_tabs_when_no_match(self):
        page1 = MagicMock()
        page1.url = "https://news.ycombinator.com"
        page1.title.return_value = "Hacker News"

        browser = MagicMock()
        context = MagicMock()
        context.pages = [page1]
        browser.contexts = [context]

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            found = flow_sync.find_flow_tab(browser, flow_sync.BUILTIN_SELECTORS)
        self.assertIsNone(found)
        self.assertIn("No active Flow tab found", stderr_buf.getvalue())
        self.assertIn("Hacker News", stderr_buf.getvalue())

    def test_dry_run_never_calls_click_and_verifies_state(self):
        fake_page = self._create_fake_page()
        browser = MagicMock()
        context = MagicMock()
        context.pages = [fake_page]
        browser.contexts = [context]
        pw = MagicMock()

        args = flow_sync.parse_args(["--dry-run", "--project", self.tmp])

        stdout_buf = io.StringIO()
        with patch("flow_sync.connect_cdp", return_value=(pw, browser)), \
             patch("sys.stdout", stdout_buf):
            exit_code = flow_sync.run_dry_run(args, self.tmp)

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_page.click.call_count, 0)
        output = stdout_buf.getvalue()
        self.assertIn("Dry-run completed successfully", output)
        self.assertIn("Zero generation calls made", output)

        # Check state was updated to dry_run_verified
        state = flow_state.load_state(project_dir=self.tmp)
        self.assertIn("IMG001", state["items"])
        self.assertEqual(state["items"]["IMG001"]["status"], "dry_run_verified")

    def test_dry_run_exits_1_when_required_selector_missing(self):
        # submit_button missing
        fake_page = self._create_fake_page(missing_selectors=["Start generation"])
        browser = MagicMock()
        context = MagicMock()
        context.pages = [fake_page]
        browser.contexts = [context]
        pw = MagicMock()

        args = flow_sync.parse_args(["--dry-run", "--project", self.tmp])

        stderr_buf = io.StringIO()
        with patch("flow_sync.connect_cdp", return_value=(pw, browser)), \
             patch("sys.stderr", stderr_buf):
            exit_code = flow_sync.run_dry_run(args, self.tmp)

        self.assertEqual(exit_code, 1)
        self.assertIn("MISSING", stderr_buf.getvalue())

    def test_cli_error_when_no_chrome(self):
        args = flow_sync.parse_args(["--dry-run", "--project", self.tmp])
        stderr_buf = io.StringIO()
        with patch("flow_sync.connect_cdp", return_value=(None, None)), \
             patch("sys.stderr", stderr_buf):
            exit_code = flow_sync.run_dry_run(args, self.tmp)
        self.assertEqual(exit_code, 1)

    def test_cli_requires_dry_run_flag(self):
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            code = flow_sync.main(["--project", self.tmp])
        self.assertEqual(code, 1)
        self.assertIn("Phase A supports only --dry-run", stderr_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
