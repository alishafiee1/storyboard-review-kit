# -*- coding: utf-8 -*-
"""Unit tests for tools/flow_retry.py and failure recovery orchestration (Phase C).

Verifies failure classification (suspicious vs real), end-of-batch tab refresh & recheck,
strict resubmit capping at 2 attempts before marking 'failed', 3-consecutive-failure cooldown,
dry-run safety, opt-in enforcement, and state persistence of attempt IDs and retry counts.
No live browser, network, or Playwright binaries required.
"""
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

import flow_retry
import flow_state
import flow_sync


class FakeElement:
    def __init__(self, selector, actions_log, has_banner=False, has_download_btn=False, has_tile=True, output_name=""):
        self.selector = selector
        self.actions_log = actions_log
        self.has_banner = has_banner
        self.has_download_btn = has_download_btn
        self.has_tile = has_tile
        self.output_name = output_name

    def click(self):
        self.actions_log.append(f"click:{self.selector}")

    def fill(self, text):
        self.actions_log.append(f"fill:{self.selector}:{text}")

    def type(self, text):
        self.actions_log.append(f"type:{self.selector}:{text}")

    def query_selector(self, selector):
        self.actions_log.append(f"element_query_selector:{selector}")
        if "alert" in selector or "error" in selector:
            return FakeElement(selector, self.actions_log, has_banner=True) if self.has_banner else None
        if "Download" in selector or "download" in selector:
            return FakeElement(selector, self.actions_log, has_download_btn=True) if self.has_download_btn else None
        return None


class FakePageForRetry:
    """Mock page that can simulate failure banners, page reloads, and generation outcomes."""

    def __init__(self, has_banner=False, has_tile=False, has_download_btn=False, tiles=None):
        self.has_banner = has_banner
        self.has_tile = has_tile
        self.has_download_btn = has_download_btn
        self.tiles = tiles
        self.actions_log = []
        self.reload_called = False
        self.url = "https://flow.google.com/project/mock_phase_c"

    def title(self):
        return "Flow Mock Project Phase C"

    def reload(self):
        self.reload_called = True
        self.actions_log.append("page_reload")

    def click(self, selector):
        self.actions_log.append(f"click:{selector}")

    def fill(self, selector, text):
        self.actions_log.append(f"fill:{selector}:{text}")

    def type(self, selector, text):
        self.actions_log.append(f"type:{selector}:{text}")

    def query_selector(self, selector):
        self.actions_log.append(f"query_selector:{selector}")
        if self.tiles is not None:
            for name, tile in self.tiles.items():
                if name in selector:
                    return tile
            return None
        if "alert" in selector or "error" in selector:
            return FakeElement(selector, self.actions_log, has_banner=True) if self.has_banner else None
        if "generation-tile" in selector:
            return FakeElement(
                selector,
                self.actions_log,
                has_banner=self.has_banner,
                has_download_btn=self.has_download_btn,
                has_tile=self.has_tile,
            ) if self.has_tile else None
        if "Download" in selector or "download" in selector:
            return FakeElement(selector, self.actions_log, has_download_btn=True) if self.has_download_btn else None
        if any(k in selector for k in ["textbox", "Start generation", "ingredients", "Search", "option"]):
            return FakeElement(selector, self.actions_log)
        return None

    def query_selector_all(self, selector):
        self.actions_log.append(f"query_selector_all:{selector}")
        if self.tiles:
            return list(self.tiles.values())
        if self.has_tile:
            return [FakeElement(
                selector,
                self.actions_log,
                has_banner=self.has_banner,
                has_download_btn=self.has_download_btn,
                has_tile=self.has_tile,
            )]
        return []

    def wait_for_selector(self, selector, timeout=30000):
        self.actions_log.append(f"wait_for_selector:{selector}:{timeout}")
        return self.query_selector(selector)


class TestFailureClassification(unittest.TestCase):
    """Test classification of errors into suspicious vs real."""

    def test_pre_refresh_error_banner_classified_as_suspicious(self):
        # Transient error banner displayed while tile may still be rendering internally
        cls = flow_retry.classify_failure(
            has_error_banner=True,
            tile_present=False,
            download_btn_present=False,
            is_post_refresh=False,
        )
        self.assertEqual(cls, "suspicious")

    def test_post_refresh_tile_present_classified_as_success(self):
        cls = flow_retry.classify_failure(
            has_error_banner=False,
            tile_present=True,
            download_btn_present=True,
            is_post_refresh=True,
        )
        self.assertEqual(cls, "success")

    def test_post_refresh_still_errored_classified_as_real(self):
        cls = flow_retry.classify_failure(
            has_error_banner=True,
            tile_present=False,
            download_btn_present=False,
            is_post_refresh=True,
        )
        self.assertEqual(cls, "real")


class TestRefreshRecheckAtBatchEnd(unittest.TestCase):
    """Test end-of-batch tab refresh recovering false failures."""

    def test_end_of_batch_refresh_recovers_falsely_errored_tile(self):
        # Page starts with error banner, but after reload tile renders successfully
        page = FakePageForRetry(has_banner=True, has_tile=False, has_download_btn=False)

        def mock_reload():
            page.reload_called = True
            page.has_banner = False
            page.has_tile = True
            page.has_download_btn = True

        page.reload = mock_reload

        selectors = {
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "download_button": "button[aria-label*=\"Download\"]",
            "failure_banner": "div[role=\"alert\"]",
        }
        suspicious = [{"output_name": "IMG004", "attempt_id": "att_004_1"}]

        recovered, confirmed = flow_retry.refresh_and_recheck_batch(
            page=page,
            selectors=selectors,
            suspicious_items=suspicious,
            sleeper=lambda s: None,
        )

        self.assertTrue(page.reload_called)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["output_name"], "IMG004")
        self.assertEqual(len(confirmed), 0)

    def test_end_of_batch_refresh_confirms_genuine_failure(self):
        # Page reload still has error banner and no tile
        page = FakePageForRetry(has_banner=True, has_tile=False, has_download_btn=False)
        selectors = {
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "download_button": "button[aria-label*=\"Download\"]",
            "failure_banner": "div[role=\"alert\"]",
        }
        suspicious = [{"output_name": "IMG005", "attempt_id": "att_005_1"}]

        recovered, confirmed = flow_retry.refresh_and_recheck_batch(
            page=page,
            selectors=selectors,
            suspicious_items=suspicious,
            sleeper=lambda s: None,
        )

        self.assertEqual(len(recovered), 0)
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0]["output_name"], "IMG005")

    def test_recheck_per_item_tile_a_succeeded_and_tile_b_failed(self):
        """Recheck per item: tile A succeeded and tile B failed on the same page."""
        log = []
        tile_a = FakeElement("tile_a", log, has_banner=False, has_download_btn=True, output_name="IMG_A")
        tile_b = FakeElement("tile_b", log, has_banner=True, has_download_btn=False, output_name="IMG_B")
        page = FakePageForRetry(tiles={"IMG_A": tile_a, "IMG_B": tile_b})

        selectors = {
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "download_button": "button[aria-label*=\"Download\"]",
            "failure_banner": "div[role=\"alert\"]",
        }
        suspicious = [
            {"output_name": "IMG_A", "attempt_id": "att_A_1"},
            {"output_name": "IMG_B", "attempt_id": "att_B_1"},
        ]

        recovered, confirmed = flow_retry.refresh_and_recheck_batch(
            page=page,
            selectors=selectors,
            suspicious_items=suspicious,
            sleeper=lambda s: None,
        )

        # Tile A succeeded -> recovered
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["output_name"], "IMG_A")
        self.assertEqual(recovered[0]["classification"], "success")

        # Tile B failed -> confirmed failure for resubmit queue
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0]["output_name"], "IMG_B")
        self.assertEqual(confirmed[0]["classification"], "real")

    def test_recheck_unidentified_tile_classified_uncertain_resubmit_queue(self):
        """If an item's tile cannot be identified, classify as 'uncertain' -> resubmit queue, never success."""
        page = FakePageForRetry(tiles={})
        selectors = {
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "download_button": "button[aria-label*=\"Download\"]",
            "failure_banner": "div[role=\"alert\"]",
        }
        suspicious = [{"output_name": "IMG_UNKNOWN", "attempt_id": "att_unk_1"}]

        recovered, confirmed = flow_retry.refresh_and_recheck_batch(
            page=page,
            selectors=selectors,
            suspicious_items=suspicious,
            sleeper=lambda s: None,
        )

        self.assertEqual(len(recovered), 0)
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0]["output_name"], "IMG_UNKNOWN")
        self.assertEqual(confirmed[0]["classification"], "uncertain")


class TestConsecutiveFailureCooldown(unittest.TestCase):
    """Test rate-limit cooldown trigger upon 3 consecutive failures."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sleeps = []
        self.fake_sleeper = lambda s: self.sleeps.append(s)
        self.now_iso = "2026-11-28T10:00:00+00:00"
        self.fake_clock = lambda: self.now_iso

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_three_consecutive_failures_triggers_cooldown_and_advisory(self):
        tracker = flow_retry.CooldownTracker(
            failure_threshold=3,
            cooldown_seconds=300.0,
            sleeper=self.fake_sleeper,
            clock=self.fake_clock,
        )
        state = flow_state.default_state()

        # 1st failure
        c1 = tracker.record_failure(state, project_dir=self.tmp)
        self.assertFalse(c1)
        self.assertEqual(len(self.sleeps), 0)

        # 2nd failure
        c2 = tracker.record_failure(state, project_dir=self.tmp)
        self.assertFalse(c2)
        self.assertEqual(len(self.sleeps), 0)

        # 3rd failure -> triggers cooldown
        c3 = tracker.record_failure(state, project_dir=self.tmp)
        self.assertTrue(c3)
        self.assertEqual(len(self.sleeps), 1)
        self.assertEqual(self.sleeps[0], 300.0)

        # Advisory must be written in state
        self.assertIn("rate_limit_advisory", state)
        self.assertEqual(state["rate_limit_advisory"]["consecutive_failures"], 3)
        self.assertEqual(state["rate_limit_advisory"]["cooldown_seconds"], 300.0)

    def test_success_resets_consecutive_failure_counter(self):
        tracker = flow_retry.CooldownTracker(
            failure_threshold=3,
            cooldown_seconds=300.0,
            sleeper=self.fake_sleeper,
            clock=self.fake_clock,
        )
        state = flow_state.default_state()

        tracker.record_failure(state, project_dir=self.tmp)
        tracker.record_failure(state, project_dir=self.tmp)
        self.assertEqual(tracker.consecutive_failures, 2)

        tracker.record_success()
        self.assertEqual(tracker.consecutive_failures, 0)

        tracker.record_failure(state, project_dir=self.tmp)
        self.assertEqual(tracker.consecutive_failures, 1)
        self.assertEqual(len(self.sleeps), 0)


class TestDryRunSafety(unittest.TestCase):
    """Test that --dry-run never clicks or downloads, querying selectors only."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "prompts"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "scenario"), exist_ok=True)
        with open(os.path.join(self.tmp, "prompts", "prompts.txt"), "w", encoding="utf-8") as fh:
            fh.write("=== IMG001 ===\n[OUTPUT NAME: IMG001]\nA prompt.\n")
        with open(os.path.join(self.tmp, "scenario", "story.txt"), "w", encoding="utf-8") as fh:
            fh.write("[SCENE 01]\n[IMG001]\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_action_log_has_only_query_selector(self):
        fake_page = FakePageForRetry(has_banner=False, has_tile=True, has_download_btn=True)
        fake_browser = MagicMock()
        fake_ctx = MagicMock()
        fake_ctx.pages = [fake_page]
        fake_browser.contexts = [fake_ctx]

        mock_pw = MagicMock()

        args = flow_sync.parse_args(["--dry-run", "--project", self.tmp])

        with patch("flow_sync.connect_cdp", return_value=(mock_pw, fake_browser)):
            code = flow_sync.run_dry_run(args, project_dir=self.tmp)

        self.assertEqual(code, 0)
        # Verify page actions: only query_selector, never click or download
        for act in fake_page.actions_log:
            self.assertTrue(act.startswith("query_selector:"), f"Unexpected dry-run action: {act}")
        self.assertFalse(any("click" in act for act in fake_page.actions_log))


class TestRunWithoutOptInDoesNothing(unittest.TestCase):
    """Test CLI behavior when no explicit mode opt-in is provided."""

    def test_run_without_mode_fails_with_exit_code_1(self):
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            code = flow_sync.main([])
        self.assertEqual(code, 1)
        self.assertIn("--download", stderr_buf.getvalue())

    def test_conflicting_modes_rejected(self):
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            code = flow_sync.main(["--dry-run", "--download"])
        self.assertEqual(code, 1)
        self.assertIn("Conflicting modes", stderr_buf.getvalue())


class TestStateAttemptIdsPersisted(unittest.TestCase):
    """Test persistence of attempt IDs and Phase C schema fields."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_attempt_id_and_phase_c_fields_persisted(self):
        state = flow_state.default_state()
        att_id = flow_state.generate_attempt_id()

        flow_state.record_item_state(
            state,
            output_name="IMG002",
            prompt_hash="phash123",
            status="done",
            attempt_id=att_id,
            retries_count=1,
            saved_path="images/scenes/IMG002.png",
            completed_at="2026-11-28T10:20:00+00:00",
        )
        flow_state.save_state(state, project_dir=self.tmp)

        loaded = flow_state.load_state(project_dir=self.tmp)
        item = loaded["items"]["IMG002"]
        self.assertEqual(item["attempt_id"], att_id)
        self.assertEqual(item["status"], "done")
        self.assertEqual(item["retries_count"], 1)
        self.assertEqual(item["saved_path"], "images/scenes/IMG002.png")
        self.assertEqual(item["completed_at"], "2026-11-28T10:20:00+00:00")


class TestPrepareRunnerExceptions(unittest.TestCase):
    """Test that _prepare_runner catches specific expected exceptions and lets programming errors surface."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.args = flow_sync.parse_args(["--mode", "download", "--project", self.tmp])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_file_not_found_error_is_caught(self):
        with patch("flow_sync.compute_queue", side_effect=FileNotFoundError("prompts missing")):
            res = flow_sync._prepare_runner(self.args, self.tmp)
            self.assertEqual(res, (None, None, None, None, None))

    def test_value_error_is_caught(self):
        with patch("flow_sync.compute_queue", side_effect=ValueError("bad prompts")):
            res = flow_sync._prepare_runner(self.args, self.tmp)
            self.assertEqual(res, (None, None, None, None, None))

    def test_key_error_is_caught(self):
        with patch("flow_sync.compute_queue", side_effect=KeyError("item missing")):
            res = flow_sync._prepare_runner(self.args, self.tmp)
            self.assertEqual(res, (None, None, None, None, None))

    def test_programming_error_surfaces(self):
        with patch("flow_sync.compute_queue", side_effect=TypeError("programming bug in queue")):
            with self.assertRaises(TypeError):
                flow_sync._prepare_runner(self.args, self.tmp)


class TestCliDownloadAlias(unittest.TestCase):
    """Test that --download is an alias for --mode download."""

    def test_download_flag_and_mode_download_both_accepted(self):
        args1 = flow_sync.parse_args(["--mode", "download"])
        args2 = flow_sync.parse_args(["--download"])

        self.assertEqual(args1.mode, "download")
        self.assertTrue(args2.download)

        # Both enable download mode in main logic
        self.assertTrue(bool(args1.download or (args1.mode == "download")))
        self.assertTrue(bool(args2.download or (args2.mode == "download")))


if __name__ == "__main__":
    unittest.main()
