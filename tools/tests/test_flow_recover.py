# -*- coding: utf-8 -*-
"""Unit tests for tools/flow_recover.py (resubmit queue and download recovery).

Verifies strict resubmission capping at max 2 retries before marking 'failed',
resumed retry count tracking from state, and Phase C download execution.
No live browser, network, or Playwright binaries required.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
for d in (TOOLS_DIR, TESTS_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import flow_recover
import flow_retry
import flow_state
from test_flow_retry import FakePageForRetry


class TestResubmitQueueAndCap(unittest.TestCase):
    """Test resubmission capping at max 2 retries before marking 'failed'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resubmit_capped_at_2_then_status_marked_failed(self):
        state = flow_state.default_state()
        queue = [{
            "output_name": "IMG006",
            "action": "generate",
            "raw_prompt": "Scene 6.",
            "prompt_hash": "hash006",
            "attempt_id": "att_006_orig",
            "refs": [],
        }]

        # Always-failing page
        page = FakePageForRetry(has_banner=True, has_tile=False, has_download_btn=False)
        selectors = {
            "prompt_box": "div[role=\"textbox\"]",
            "submit_button": "button[aria-label=\"Start generation\"]",
            "ingredients_button": "button[aria-label=\"Add ingredients\"]",
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "download_button": "button[aria-label*=\"Download\"]",
            "failure_banner": "div[role=\"alert\"]",
            "_unverified": ["result_tile", "download_button", "failure_banner"],
        }

        # Mock submit_single_prompt to return timed_out and sleeper to no-op
        with patch("flow_submit.submit_single_prompt", return_value="timed_out"):
            code = flow_recover.run_download_phase(
                page=page,
                queue=queue,
                selectors=selectors,
                project_dir=self.tmp,
                batch_size=10,
                max_retries=2,
                cooldown_seconds=300.0,
                sleeper=lambda s: None,
                state=state,
            )

        self.assertEqual(code, 0)
        item_state = state["items"].get("IMG006")
        self.assertIsNotNone(item_state)
        # Must be marked failed after 2 resubmits
        self.assertEqual(item_state["status"], "failed")
        self.assertEqual(item_state["retries_count"], 2)

    def test_fresh_item_exactly_2_resubmit_submissions_then_failed(self):
        """Fresh item -> exactly 2 resubmit submissions then status 'failed'."""
        state = flow_state.default_state()
        resubmit_queue = flow_retry.ResubmitQueue(max_retries=2, state=state)
        item = {
            "output_name": "IMG_FRESH",
            "raw_prompt": "Prompt fresh.",
            "prompt_hash": "hash_fresh",
            "attempt_id": "att_orig",
            "refs": [],
        }
        # First queue entry initialises retries_count to 0 in state
        resubmit_queue.add_failure(item, state=state)
        self.assertIn("IMG_FRESH", state["items"])
        self.assertEqual(state["items"]["IMG_FRESH"]["retries_count"], 0)

        page = FakePageForRetry(has_banner=True, has_tile=False, has_download_btn=False)
        selectors = {
            "prompt_box": "div[role=\"textbox\"]",
            "submit_button": "button[aria-label=\"Start generation\"]",
            "ingredients_button": "button[aria-label=\"Add ingredients\"]",
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "download_button": "button[aria-label*=\"Download\"]",
            "failure_banner": "div[role=\"alert\"]",
        }

        submission_calls = []

        def mock_submit(p, itm, sel, sleeper=None):
            submission_calls.append(dict(itm))
            return "timed_out"

        with patch("flow_submit.submit_single_prompt", side_effect=mock_submit):
            flow_recover.process_resubmit_queue(
                page=page,
                resubmit_queue=resubmit_queue,
                selectors=selectors,
                project_dir=self.tmp,
                state=state,
                max_retries=2,
                sleeper=lambda s: None,
            )

        # Exactly 2 resubmit submissions performed
        self.assertEqual(len(submission_calls), 2)
        self.assertEqual(submission_calls[0]["retries_count"], 1)
        self.assertEqual(submission_calls[1]["retries_count"], 2)

        # Marked failed in state with retries_count=2
        item_state = state["items"]["IMG_FRESH"]
        self.assertEqual(item_state["status"], "failed")
        self.assertEqual(item_state["retries_count"], 2)

    def test_resumed_item_with_retries_count_1_gets_exactly_1(self):
        """Resumed with retries_count=1 -> exactly 1 resubmit submission then status 'failed'."""
        state = flow_state.default_state()
        state["items"]["IMG_RESUMED"] = {
            "output_name": "IMG_RESUMED",
            "prompt_hash": "hash_resumed",
            "status": "pending",
            "retries_count": 1,
            "attempt_id": "att_prev",
        }
        resubmit_queue = flow_retry.ResubmitQueue(max_retries=2, state=state)
        item = {
            "output_name": "IMG_RESUMED",
            "raw_prompt": "Prompt resumed.",
            "prompt_hash": "hash_resumed",
            "attempt_id": "att_prev",
            "refs": [],
        }
        # First queue entry honours existing retries_count=1 from state
        resubmit_queue.add_failure(item, state=state)
        self.assertEqual(resubmit_queue.queue[0]["retries_count"], 1)

        page = FakePageForRetry(has_banner=True, has_tile=False, has_download_btn=False)
        selectors = {
            "prompt_box": "div[role=\"textbox\"]",
            "submit_button": "button[aria-label=\"Start generation\"]",
            "ingredients_button": "button[aria-label=\"Add ingredients\"]",
            "result_tile": "div[data-testid=\"generation-tile\"]",
            "download_button": "button[aria-label*=\"Download\"]",
            "failure_banner": "div[role=\"alert\"]",
        }

        submission_calls = []

        def mock_submit(p, itm, sel, sleeper=None):
            submission_calls.append(dict(itm))
            return "timed_out"

        with patch("flow_submit.submit_single_prompt", side_effect=mock_submit):
            flow_recover.process_resubmit_queue(
                page=page,
                resubmit_queue=resubmit_queue,
                selectors=selectors,
                project_dir=self.tmp,
                state=state,
                max_retries=2,
                sleeper=lambda s: None,
            )

        # Resumed item with retries_count=1 gets exactly 1 resubmit submission
        self.assertEqual(len(submission_calls), 1)
        self.assertEqual(submission_calls[0]["retries_count"], 2)

        # Marked failed in state
        item_state = state["items"]["IMG_RESUMED"]
        self.assertEqual(item_state["status"], "failed")
        self.assertEqual(item_state["retries_count"], 2)


if __name__ == "__main__":
    unittest.main()
