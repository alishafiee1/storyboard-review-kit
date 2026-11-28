# -*- coding: utf-8 -*-
"""Integration unit tests for Flow worker self-healing retry, download mode, and serve routing."""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import flow_api
import flow_heal
import flow_recover
import flow_state
import flow_sync
import serve


class FakePlaywrightPage:
    """Mock Playwright page that simulates selector failures and DOM inspection."""

    def __init__(self, content_html="<html><body><div role='textbox'>Mock Box</div></body></html>"):
        self._content = content_html

    def content(self):
        return self._content

    def screenshot(self, path=None):
        png = b"\x89PNG\r\n\x1a\nfake"
        if path:
            with open(path, "wb") as fh:
                fh.write(png)
        return png


def _setup_test_project(proj_dir: str):
    """Create minimal valid project files for flow automation."""
    os.makedirs(os.path.join(proj_dir, "scenario"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "prompts"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "images", "scenes", "b01"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "tools"), exist_ok=True)

    with open(os.path.join(proj_dir, "scenario", "story.txt"), "w", encoding="utf-8") as fh:
        fh.write("=== scene-01 | Test | 0:00 ===\n[IMG001]\n")
    with open(os.path.join(proj_dir, "scenario", "reference.txt"), "w", encoding="utf-8") as fh:
        fh.write("#refs\n")
    with open(os.path.join(proj_dir, "prompts", "prompts.txt"), "w", encoding="utf-8") as fh:
        fh.write("=== IMG001 ===\nA test scene prompt\n")


class TestFlowWorkerAndRouting(unittest.TestCase):
    """Test worker self-heal loop retry, download mode state persistence, and HTTP 404 routing."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srk-worker-test-")
        _setup_test_project(self.tmp)
        flow_api.FLOW_JOB.update(
            state="idle",
            done=0,
            total=0,
            percent=0,
            failed_items=[],
            self_heal=None,
            error=None,
        )
        flow_api.RESEND_QUEUE.clear()
        flow_heal.request_resume()

    def tearDown(self):
        flow_heal.request_resume()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_worker_fake_page_selector_failure_pause_and_resume_retry(self):
        """Worker pauses on broken selector; upon patch and resume, it retries verify and completes."""
        fake_page = FakePlaywrightPage()
        tools_sel = os.path.join(self.tmp, "tools", "flow_selectors.json")
        with open(tools_sel, "w", encoding="utf-8") as fh:
            json.dump({"prompt_box": "broken_selector_v1"}, fh)

        verify_call_count = [0]
        repaired = [False]

        def fake_verify_selectors(page, selectors):
            verify_call_count[0] += 1
            if not repaired[0]:
                return False, {"prompt_box": {"found": False, "selector": selectors.get("prompt_box", "")}}
            return True, {"prompt_box": {"found": True, "selector": selectors.get("prompt_box", "")}}

        fake_browser = mock.MagicMock()

        with mock.patch("flow_sync.connect_cdp", return_value=(mock.MagicMock(), fake_browser)), \
             mock.patch("flow_sync.find_flow_tab", return_value=fake_page), \
             mock.patch("flow_sync.verify_selectors", side_effect=fake_verify_selectors), \
             mock.patch("flow_submit.submit_single_prompt", return_value="submitted"), \
             mock.patch("flow_sync._cleanup_browser"):

            worker_th = threading.Thread(
                target=flow_api._flow_background_worker,
                args=("submit", self.tmp),
                daemon=True,
            )
            worker_th.start()

            # Wait for self-healing pause
            for _ in range(50):
                time.sleep(0.05)
                if flow_heal.is_pause_requested() and flow_api.FLOW_JOB["state"] == "paused":
                    break

            self.assertEqual(flow_api.FLOW_JOB["state"], "paused")
            self.assertIsNotNone(flow_api.FLOW_JOB["self_heal"])
            self.assertEqual(flow_api.FLOW_JOB["self_heal"]["step"], "verify_selectors")
            self.assertEqual(flow_api.FLOW_JOB["self_heal"]["selector_key"], "prompt_box")

            diag_path = os.path.join(self.tmp, flow_api.FLOW_JOB["self_heal"]["diagnostic_dir"])
            self.assertTrue(os.path.isdir(diag_path))

            # Patch selector with working value and flag repaired
            repaired[0] = True
            with open(tools_sel, "w", encoding="utf-8") as fh:
                json.dump({"prompt_box": "repaired_selector_v2"}, fh)

            # Resume job
            r_resume = flow_api.resume_flow_job(project_dir=self.tmp)
            self.assertTrue(r_resume.get("ok"))

            # Worker should retry verify_selectors, find repaired selector, and finish
            worker_th.join(timeout=5.0)
            self.assertFalse(worker_th.is_alive())
            self.assertEqual(flow_api.FLOW_JOB["state"], "done")
            self.assertGreaterEqual(verify_call_count[0], 2)

    def test_worker_download_mode_persists_state_and_calls_download_phase(self):
        """When mode == 'download', worker writes flow-state.json and calls run_download_phase."""
        fake_page = FakePlaywrightPage()
        fake_browser = mock.MagicMock()
        download_phase_called = []

        def fake_download_phase(**kwargs):
            download_phase_called.append(kwargs)
            return 0

        with mock.patch("flow_sync.connect_cdp", return_value=(mock.MagicMock(), fake_browser)), \
             mock.patch("flow_sync.find_flow_tab", return_value=fake_page), \
             mock.patch("flow_sync.verify_selectors", return_value=(True, {})), \
             mock.patch("flow_recover.run_download_phase", side_effect=fake_download_phase), \
             mock.patch("flow_sync._cleanup_browser"):

            flow_api._flow_background_worker(mode="download", project_dir=self.tmp)

            # Assert .kit/flow-state.json was persisted
            state_file = os.path.join(self.tmp, ".kit", "flow-state.json")
            self.assertTrue(os.path.isfile(state_file))
            with open(state_file, "r", encoding="utf-8") as fh:
                state_data = json.load(fh)
            self.assertIn("items", state_data)
            self.assertIn("IMG001", state_data["items"])

            # Assert run_download_phase was invoked
            self.assertEqual(len(download_phase_called), 1)
            self.assertEqual(download_phase_called[0]["project_dir"], self.tmp)

    def test_serve_routing_unknown_flow_endpoint_returns_404(self):
        """Unknown GET /api/flow/* must return HTTP 404, valid returns HTTP 200."""
        recorded_responses = []

        handler = serve.H.__new__(serve.H)
        handler.headers = {}

        def mock_json(code, obj):
            recorded_responses.append((code, obj))

        handler._json = mock_json

        # 1. Unknown GET /api/flow/nonexistent -> 404
        handler.path = "/api/flow/nonexistent"
        handler.do_GET()
        self.assertEqual(len(recorded_responses), 1)
        self.assertEqual(recorded_responses[0][0], 404)
        self.assertEqual(recorded_responses[0][1], {"error": "not found"})

        # 2. Known GET /api/flow/status -> 200
        handler.path = "/api/flow/status"
        handler.do_GET()
        self.assertEqual(len(recorded_responses), 2)
        self.assertEqual(recorded_responses[1][0], 200)
        self.assertIn("state", recorded_responses[1][1])


if __name__ == "__main__":
    unittest.main()
