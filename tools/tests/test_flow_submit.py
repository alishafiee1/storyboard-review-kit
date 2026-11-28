# -*- coding: utf-8 -*-
"""Unit tests for Phase B Flow automation (tools/flow_submit.py, flow_sync.py, flow_state.py).

Verifies prompt segmentation, reference attachment by name, batching, jitter/pause ranges,
daily cap enforcement, event-based waiting, action sequence order, dry-run safety, and
unverified selector reporting.
No live browser, network, or Playwright binaries required.
"""
import datetime
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import flow_state
import flow_submit
import flow_sync


class FakeKeyboard:
    def __init__(self, actions_log):
        self.actions_log = actions_log

    def type(self, text):
        self.actions_log.append(f"keyboard_type:{text}")

    def press(self, key):
        self.actions_log.append(f"keyboard_press:{key}")


class FakeElement:
    def __init__(self, selector, actions_log):
        self.selector = selector
        self.actions_log = actions_log

    def click(self):
        self.actions_log.append(f"click:{self.selector}")

    def fill(self, text):
        self.actions_log.append(f"fill:{self.selector}:{text}")

    def type(self, text):
        self.actions_log.append(f"type:{self.selector}:{text}")


class FakePage:
    def __init__(self, missing_selectors=None, timeout_selectors=None):
        self.actions_log = []
        self.keyboard = FakeKeyboard(self.actions_log)
        self.missing_selectors = set(missing_selectors or [])
        self.timeout_selectors = set(timeout_selectors or [])
        self.url = "https://flow.google.com/project/mock_phase_b"

    def title(self):
        return "Flow Mock Project"

    def click(self, selector):
        if selector in self.missing_selectors:
            raise RuntimeError(f"Element not found to click: {selector}")
        self.actions_log.append(f"click:{selector}")

    def fill(self, selector, text):
        if selector in self.missing_selectors:
            raise RuntimeError(f"Element not found to fill: {selector}")
        self.actions_log.append(f"fill:{selector}:{text}")

    def type(self, selector, text):
        if selector in self.missing_selectors:
            raise RuntimeError(f"Element not found to type: {selector}")
        self.actions_log.append(f"type:{selector}:{text}")

    def query_selector(self, selector):
        self.actions_log.append(f"query_selector:{selector}")
        for m in self.missing_selectors:
            if m in selector:
                return None
        return FakeElement(selector, self.actions_log)

    def wait_for_selector(self, selector, timeout=30000):
        self.actions_log.append(f"wait_for_selector:{selector}:{timeout}")
        for t in self.timeout_selectors:
            if t in selector:
                raise TimeoutError(f"Timed out waiting for {selector}")
        for m in self.missing_selectors:
            if m in selector:
                return None
        return FakeElement(selector, self.actions_log)


class TestPromptSegmentation(unittest.TestCase):
    """Test pure prompt segmentation and reference name extraction."""

    def test_clean_ref_name_normalization(self):
        self.assertEqual(flow_submit.clean_ref_name("CH_NIBBLES"), "CH_NIBBLES")
        self.assertEqual(flow_submit.clean_ref_name("[CH_NIBBLES]"), "CH_NIBBLES")
        self.assertEqual(flow_submit.clean_ref_name("@CH_NIBBLES"), "CH_NIBBLES")
        self.assertEqual(flow_submit.clean_ref_name("CH_MIMO_4eb46d68.jpg"), "CH_MIMO")
        self.assertEqual(flow_submit.clean_ref_name("LOC_CAVE_11112222.png"), "LOC_CAVE")
        self.assertEqual(flow_submit.clean_ref_name(""), "")

    def test_segmenting_without_refs(self):
        prompt = "A serene sunset over snowy mountain peaks."
        segments = flow_submit.segment_prompt(prompt, refs=[])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["type"], "text")
        self.assertEqual(segments[0]["value"], prompt)

    def test_segmenting_with_single_ref_in_text(self):
        prompt = "A cinematic shot of CH_NIBBLES eating a slice of cheese."
        segments = flow_submit.segment_prompt(prompt, refs=["CH_NIBBLES"])
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0], {"type": "text", "value": "A cinematic shot of "})
        self.assertEqual(segments[1], {"type": "ref", "value": "CH_NIBBLES"})
        self.assertEqual(segments[2], {"type": "text", "value": " eating a slice of cheese."})

    def test_segmenting_with_multiple_refs(self):
        prompt = "CH_NIBBLES meeting CH_ALICE inside LOC_CAVE at midnight."
        refs = ["CH_NIBBLES", "CH_ALICE", "LOC_CAVE"]
        segments = flow_submit.segment_prompt(prompt, refs=refs)
        self.assertEqual(len(segments), 6)
        self.assertEqual(segments[0], {"type": "ref", "value": "CH_NIBBLES"})
        self.assertEqual(segments[1], {"type": "text", "value": " meeting "})
        self.assertEqual(segments[2], {"type": "ref", "value": "CH_ALICE"})
        self.assertEqual(segments[3], {"type": "text", "value": " inside "})
        self.assertEqual(segments[4], {"type": "ref", "value": "LOC_CAVE"})
        self.assertEqual(segments[5], {"type": "text", "value": " at midnight."})

    def test_segmenting_with_non_inline_refs(self):
        raw = "[REFS TO ATTACH: STYLE_ANCHOR| LOC_CAVE]\nA dark and eerie subterranean room."
        refs = ["STYLE_ANCHOR", "LOC_CAVE"]
        segments = flow_submit.segment_prompt(raw, refs=refs)
        self.assertEqual(segments[0], {"type": "ref", "value": "STYLE_ANCHOR"})
        self.assertEqual(segments[1], {"type": "ref", "value": "LOC_CAVE"})
        self.assertEqual(segments[2], {"type": "text", "value": "A dark and eerie subterranean room."})

    def test_segmenting_strips_output_name_directive(self):
        raw = "[OUTPUT NAME: IMG045_cave_wall]\n[REFS TO ATTACH: STYLE_ANCHOR]\nCave wall texture."
        segments = flow_submit.segment_prompt(raw, refs=["STYLE_ANCHOR"])
        self.assertEqual(segments[0], {"type": "ref", "value": "STYLE_ANCHOR"})
        self.assertEqual(segments[1], {"type": "text", "value": "Cave wall texture."})
        self.assertNotIn("OUTPUT NAME", "".join(s["value"] for s in segments))

    def test_segmenting_with_bracketed_and_at_tokens(self):
        raw = "A portrait of [CH_NIBBLES] wearing sunglasses and @STYLE_ANCHOR aesthetic."
        segments = flow_submit.segment_prompt(raw, refs=["CH_NIBBLES", "STYLE_ANCHOR"])
        self.assertEqual(segments[0], {"type": "text", "value": "A portrait of "})
        self.assertEqual(segments[1], {"type": "ref", "value": "CH_NIBBLES"})
        self.assertEqual(segments[2], {"type": "text", "value": " wearing sunglasses and "})
        self.assertEqual(segments[3], {"type": "ref", "value": "STYLE_ANCHOR"})
        self.assertEqual(segments[4], {"type": "text", "value": " aesthetic."})


class TestBatchingAndPlanning(unittest.TestCase):
    """Test batch splitting, jitter/pause ranges, and daily cap calculation."""

    def test_batch_splitting_groups_of_ten(self):
        items = list(range(25))
        batches = flow_submit.plan_batches(items, batch_size=10)
        self.assertEqual(len(batches), 3)
        self.assertEqual(len(batches[0]), 10)
        self.assertEqual(len(batches[1]), 10)
        self.assertEqual(len(batches[2]), 5)

    def test_batch_splitting_exact_multiple(self):
        items = list(range(20))
        batches = flow_submit.plan_batches(items, batch_size=10)
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 10)
        self.assertEqual(len(batches[1]), 10)

    def test_jitter_range_respected(self):
        for _ in range(50):
            j = flow_submit.calculate_jitter()
            self.assertGreaterEqual(j, 3.0)
            self.assertLessEqual(j, 8.0)

        fake_rng = MagicMock()
        fake_rng.uniform.return_value = 5.5
        self.assertEqual(flow_submit.calculate_jitter(rng=fake_rng), 5.5)
        fake_rng.uniform.assert_called_once_with(3.0, 8.0)

    def test_pause_range_respected(self):
        for _ in range(50):
            p = flow_submit.calculate_inter_batch_pause()
            self.assertGreaterEqual(p, 30.0)
            self.assertLessEqual(p, 90.0)

        fake_rng = MagicMock()
        fake_rng.uniform.return_value = 60.0
        self.assertEqual(flow_submit.calculate_inter_batch_pause(rng=fake_rng), 60.0)
        fake_rng.uniform.assert_called_once_with(30.0, 90.0)

    def test_daily_cap_detection_and_reset(self):
        state = flow_state.default_state()
        state["daily_submitted_count"] = 50
        state["last_batch_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.assertFalse(flow_submit.is_daily_cap_reached(state, daily_cap=100))
        self.assertTrue(flow_submit.is_daily_cap_reached(state, daily_cap=50))
        self.assertTrue(flow_submit.is_daily_cap_reached(state, daily_cap=40))

        # Check rolling 24-hour expiration reset
        old_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)).isoformat()
        state["last_batch_at"] = old_time
        # Count should reset to 0 after 24h
        self.assertFalse(flow_submit.is_daily_cap_reached(state, daily_cap=50))


class TestPageInteractionAndActionOrder(unittest.TestCase):
    """Test Playwright action sequence, event waits, and error edge cases."""

    def setUp(self):
        self.selectors = {
            "prompt_box": "div[role=\"textbox\"]",
            "submit_button": "button[aria-label=\"Start generation\"]",
            "ingredients_button": "button[aria-label=\"Add ingredients\"]",
            "ingredient_search_input": "input[placeholder*=\"Search\"]",
            "ingredient_result_item": "div[role=\"option\"]",
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "_unverified": ["ingredient_search_input", "ingredient_result_item", "result_tile"]
        }

    def test_action_order_type_search_enter_continue_submit(self):
        page = FakePage()
        item = {
            "output_name": "IMG001",
            "raw_prompt": "A shot of CH_NIBBLES in the garden",
            "refs": ["CH_NIBBLES"],
            "prompt_hash": "h123",
            "attempt_id": "att_001",
        }

        outcome = flow_submit.submit_single_prompt(page, item, self.selectors)
        self.assertEqual(outcome, "submitted")

        # Verify exact sequence of actions:
        # 1. click prompt box
        # 2. type "A shot of "
        # 3. click ingredients button
        # 4. fill ingredient search input with "CH_NIBBLES"
        # 5. press Enter
        # 6. type " in the garden"
        # 7. click submit button
        # 8. wait_for_selector generation tile
        log = page.actions_log
        self.assertIn("click:div[role=\"textbox\"]", log)
        self.assertIn("keyboard_type:A shot of ", log)
        self.assertIn("click:button[aria-label=\"Add ingredients\"]", log)
        self.assertIn("fill:input[placeholder*=\"Search\"]:CH_NIBBLES", log)
        self.assertIn("keyboard_press:Enter", log)
        self.assertIn("keyboard_type: in the garden", log)
        self.assertIn("click:button[aria-label=\"Start generation\"]", log)
        self.assertTrue(any("wait_for_selector:div[data-testid=\"generation-tile\"]" in entry for entry in log))

        # Check relative ordering
        idx_type1 = log.index("keyboard_type:A shot of ")
        idx_btn = log.index("click:button[aria-label=\"Add ingredients\"]")
        idx_search = log.index("fill:input[placeholder*=\"Search\"]:CH_NIBBLES")
        idx_enter = log.index("keyboard_press:Enter")
        idx_type2 = log.index("keyboard_type: in the garden")
        idx_submit = log.index("click:button[aria-label=\"Start generation\"]")

        self.assertLess(idx_type1, idx_btn)
        self.assertLess(idx_btn, idx_search)
        self.assertLess(idx_search, idx_enter)
        self.assertLess(idx_enter, idx_type2)
        self.assertLess(idx_type2, idx_submit)

    def test_never_triggers_file_picker(self):
        page = FakePage()
        item = {
            "output_name": "IMG001",
            "raw_prompt": "A shot of CH_NIBBLES",
            "refs": ["CH_NIBBLES"],
        }
        flow_submit.submit_single_prompt(page, item, self.selectors)
        # Ensure neither file_chooser nor file input was touched
        for entry in page.actions_log:
            self.assertNotIn("file_chooser", entry.lower())
            self.assertNotIn("file-picker", entry.lower())
            self.assertNotIn("input[type=\"file\"]", entry)

    def test_unknown_ref_name_marks_ref_not_found_and_skips_submit(self):
        # Result item is missing from search results
        page = FakePage(missing_selectors=["div[role=\"option\"]"])
        item = {
            "output_name": "IMG002",
            "raw_prompt": "A shot of UNKNOWN_CHARACTER in the garden",
            "refs": ["UNKNOWN_CHARACTER"],
        }
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            outcome = flow_submit.submit_single_prompt(page, item, self.selectors)

        self.assertEqual(outcome, "ref_not_found")
        # Ensure submit was NEVER clicked for broken prompt
        self.assertNotIn("click:button[aria-label=\"Start generation\"]", page.actions_log)
        self.assertIn("not found in ingredients search results", stderr_buf.getvalue())

    def test_event_waits_not_using_fixed_sleeps(self):
        page = FakePage()
        sleeper_mock = MagicMock()
        item = {
            "output_name": "IMG003",
            "raw_prompt": "A prompt without sleep",
            "refs": [],
        }
        outcome = flow_submit.submit_single_prompt(page, item, self.selectors, sleeper=sleeper_mock)
        self.assertEqual(outcome, "submitted")
        # When page.wait_for_selector succeeds, sleeper is NOT called with fixed sleeps
        sleeper_mock.assert_not_called()

    def test_generation_timeout_marks_timed_out_without_crashing(self):
        # generation tile times out
        page = FakePage(timeout_selectors=["div[data-testid=\"generation-tile\"]"])
        item = {
            "output_name": "IMG004",
            "raw_prompt": "Slow generation prompt",
            "refs": [],
        }
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            outcome = flow_submit.submit_single_prompt(page, item, self.selectors)

        self.assertEqual(outcome, "timed_out")
        self.assertIn("Generation wait timed out", stderr_buf.getvalue())


class TestBatchRunnerExecution(unittest.TestCase):
    """Test batch loop execution, jitter/pause invocations, and daily cap halting."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, ".kit"), exist_ok=True)
        self.selectors = {
            "prompt_box": "div[role=\"textbox\"]",
            "submit_button": "button[aria-label=\"Start generation\"]",
            "ingredients_button": "button[aria-label=\"Add ingredients\"]",
            "ingredient_search_input": "input[placeholder*=\"Search\"]",
            "ingredient_result_item": "div[role=\"option\"]",
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "_unverified": ["ingredient_search_input", "ingredient_result_item", "result_tile"]
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_submit_batches_respects_batch_wait_jitter_and_pause(self):
        page = FakePage()
        queue = []
        for i in range(1, 13):
            queue.append({
                "output_name": f"IMG{i:03d}",
                "action": "generate",
                "raw_prompt": f"Prompt {i}",
                "refs": [],
                "prompt_hash": f"hash_{i}",
                "attempt_id": f"att_{i}",
            })

        sleep_calls = []
        def fake_sleeper(seconds):
            sleep_calls.append(seconds)

        fake_rng = MagicMock()
        # Alternate jitter (4.0s) and pause (45.0s)
        def fake_uniform(a, b):
            if a == 3.0:
                return 4.0
            return 45.0
        fake_rng.uniform.side_effect = fake_uniform

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            exit_code = flow_submit.run_submit_batches(
                page=page,
                queue=queue,
                selectors=self.selectors,
                project_dir=self.tmp,
                batch_size=10,
                daily_cap=100,
                rng=fake_rng,
                sleeper=fake_sleeper,
            )

        self.assertEqual(exit_code, 0)
        # 12 items: Batch 1 (10 items), Batch 2 (2 items).
        # Jitter after items 1..9 in Batch 1 = 9 jitters.
        # Inter-batch pause after Batch 1 = 1 pause.
        # Jitter after item 1 in Batch 2 = 1 jitter.
        # Total jitters: 10 calls of 4.0s. Total pauses: 1 call of 45.0s.
        jitters = [s for s in sleep_calls if s == 4.0]
        pauses = [s for s in sleep_calls if s == 45.0]
        self.assertEqual(len(jitters), 10)
        self.assertEqual(len(pauses), 1)

        # Verify state persistence
        state = flow_state.load_state(project_dir=self.tmp)
        self.assertEqual(state["daily_submitted_count"], 12)
        self.assertIn("IMG001", state["items"])
        self.assertEqual(state["items"]["IMG001"]["status"], "submitted")
        self.assertEqual(state["items"]["IMG001"]["batch_id"], 1)
        self.assertIn("submitted_at", state["items"]["IMG001"])
        self.assertEqual(state["items"]["IMG012"]["batch_id"], 2)

    def test_run_submit_batches_with_fake_clock(self):
        page = FakePage()
        fixed_dt = datetime.datetime(2030, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
        fake_clock = MagicMock(return_value=fixed_dt)
        queue = [{
            "output_name": "IMG001",
            "action": "generate",
            "raw_prompt": "Prompt with fake clock",
            "refs": [],
            "prompt_hash": "hash_clock_1",
            "attempt_id": "att_clock_1",
        }]

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            exit_code = flow_submit.run_submit_batches(
                page=page,
                queue=queue,
                selectors=self.selectors,
                project_dir=self.tmp,
                clock=fake_clock,
                sleeper=lambda s: None,
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(fake_clock.called)
        state = flow_state.load_state(project_dir=self.tmp)
        self.assertEqual(state["last_batch_at"], fixed_dt.isoformat())
        self.assertEqual(state["items"]["IMG001"]["submitted_at"], fixed_dt.isoformat())
        self.assertEqual(state["items"]["IMG001"]["updated_at"], fixed_dt.isoformat())
        self.assertEqual(state["last_run"], fixed_dt.isoformat())

    def test_inter_submit_jitter_applied_regardless_of_outcome(self):
        page = FakePage()
        queue = [
            {"output_name": "IMG001", "action": "generate", "raw_prompt": "P1", "refs": []},
            {"output_name": "IMG002", "action": "generate", "raw_prompt": "P2", "refs": []},
            {"output_name": "IMG003", "action": "generate", "raw_prompt": "P3", "refs": []},
        ]
        jitter_calls = []
        fake_rng = MagicMock()
        fake_rng.uniform.return_value = 5.0

        def fake_sleeper(seconds):
            if seconds == 5.0:
                jitter_calls.append(seconds)

        # Item 1: timed_out, Item 2: error, Item 3: submitted
        def mock_submit(p, item, sel, sleeper=None):
            if item["output_name"] == "IMG001":
                return "timed_out"
            if item["output_name"] == "IMG002":
                return "error"
            return "submitted"

        stdout_buf = io.StringIO()
        with patch("flow_submit.submit_single_prompt", side_effect=mock_submit), \
             patch("sys.stdout", stdout_buf):
            exit_code = flow_submit.run_submit_batches(
                page=page,
                queue=queue,
                selectors=self.selectors,
                project_dir=self.tmp,
                batch_size=10,
                rng=fake_rng,
                sleeper=fake_sleeper,
            )

        self.assertEqual(exit_code, 0)
        # Jitter must be applied between items 1->2 and 2->3 regardless of timed_out/error outcome
        self.assertEqual(len(jitter_calls), 2)

    def test_run_submit_batches_stops_at_daily_cap_and_marks_remaining_pending(self):
        page = FakePage()
        queue = []
        for i in range(1, 6):
            queue.append({
                "output_name": f"IMG{i:03d}",
                "action": "generate",
                "raw_prompt": f"Prompt {i}",
                "refs": [],
                "prompt_hash": f"hash_{i}",
                "attempt_id": f"att_{i}",
            })

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            exit_code = flow_submit.run_submit_batches(
                page=page,
                queue=queue,
                selectors=self.selectors,
                project_dir=self.tmp,
                batch_size=10,
                daily_cap=2,  # Cap at 2 items
                sleeper=lambda s: None,
            )

        self.assertEqual(exit_code, 0)
        state = flow_state.load_state(project_dir=self.tmp)
        self.assertEqual(state["daily_submitted_count"], 2)
        self.assertEqual(state["items"]["IMG001"]["status"], "submitted")
        self.assertEqual(state["items"]["IMG002"]["status"], "submitted")
        # Remaining items marked pending
        self.assertEqual(state["items"]["IMG003"]["status"], "pending")
        self.assertEqual(state["items"]["IMG004"]["status"], "pending")
        self.assertEqual(state["items"]["IMG005"]["status"], "pending")


class TestDryRunAndUnverifiedSelectors(unittest.TestCase):
    """Test --dry-run safety and unverified selectors reporting."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "prompts"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "scenario"), exist_ok=True)
        with open(os.path.join(self.tmp, "prompts", "prompts.txt"), "w", encoding="utf-8") as fh:
            fh.write("=== IMG001 ===\nTest prompt\n")
        with open(os.path.join(self.tmp, "scenario", "story.txt"), "w", encoding="utf-8") as fh:
            fh.write("=== scene-01 | Test | 0:00 ===\n[IMG001]\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_still_never_clicks_and_does_not_submit(self):
        fake_page = FakePage()
        # Intercept clicks
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
        self.assertGreater(len(fake_page.actions_log), 0)
        self.assertTrue(all(entry.startswith("query_selector:") for entry in fake_page.actions_log))
        for entry in fake_page.actions_log:
            for forbidden in ("click", "type", "fill", "keyboard", "press"):
                self.assertNotIn(forbidden, entry.lower())
        self.assertIn("Zero generation calls made", stdout_buf.getvalue())

    def test_run_submit_refuses_without_explicit_opt_in(self):
        fake_page = FakePage()
        browser = MagicMock()
        context = MagicMock()
        context.pages = [fake_page]
        browser.contexts = [context]
        pw = MagicMock()

        args = flow_sync.parse_args(["--dry-run", "--project", self.tmp])
        self.assertFalse(args.submit)
        self.assertNotEqual(args.mode, "submit")

        stderr_buf = io.StringIO()
        with patch("flow_sync.connect_cdp", return_value=(pw, browser)) as mock_connect, \
             patch("sys.stderr", stderr_buf):
            exit_code = flow_sync.run_submit(args, self.tmp)

        self.assertNotEqual(exit_code, 0)
        self.assertIn("Explicit submit opt-in required", stderr_buf.getvalue())
        mock_connect.assert_not_called()
        self.assertEqual(len(fake_page.actions_log), 0)

    def test_dry_run_reports_unverified_separately_from_verified(self):
        fake_page = FakePage(missing_selectors=["div[data-testid=\"generation-tile\"]"])
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
        output = stdout_buf.getvalue()
        self.assertIn("Selectors Validation:", output)
        self.assertIn("Unverified Selectors:", output)
        self.assertIn("UNVERIFIED:MISSING", output)
        self.assertIn("result_tile", output)


if __name__ == "__main__":
    unittest.main()
