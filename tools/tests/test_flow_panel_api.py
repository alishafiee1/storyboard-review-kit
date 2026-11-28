# -*- coding: utf-8 -*-
"""Unit tests for Phase D: Flow UI Panel API, Chrome launch, and Self-Healing diagnostics."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

# Ensure tools/ is on sys.path
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import flow_api
import flow_heal
import flow_launch


class FakePage:
    """Mock Playwright page for self-healing tests."""

    def __init__(self, content_html="<html><body><div>Mock Flow DOM</div></body></html>", screenshot_bytes=b"\x89PNG\r\n\x1a\nfake"):
        self._content = content_html
        self._screenshot = screenshot_bytes

    def content(self):
        return self._content

    def screenshot(self, path=None):
        if path:
            with open(path, "wb") as fh:
                fh.write(self._screenshot)
        return self._screenshot


class TestChromeLaunch(unittest.TestCase):
    """Test Chrome launch logic, defaults, overrides, fallbacks, and port checking."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srk-launch-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_launch_chrome_defaults(self):
        spawned_cmd = []

        def fake_spawner(cmd):
            spawned_cmd.append(cmd)

        res = flow_launch.launch_chrome(
            port_checker=lambda port: False,
            spawner=fake_spawner,
            file_checker=lambda p: p == flow_launch.DEFAULT_CHROME_EXE,
            project_dir=self.tmp,
            env={},
        )

        self.assertTrue(res.get("ok"))
        self.assertTrue(res.get("spawned"))
        self.assertEqual(res.get("exe"), flow_launch.DEFAULT_CHROME_EXE)
        self.assertEqual(res.get("profile"), flow_launch.DEFAULT_PROFILE_DIR)
        self.assertEqual(len(spawned_cmd), 1)
        self.assertIn("--remote-debugging-port=9222", spawned_cmd[0])
        self.assertIn(f"--user-data-dir={flow_launch.DEFAULT_PROFILE_DIR}", spawned_cmd[0])

    def test_launch_chrome_env_overrides(self):
        custom_exe = r"D:\Tools\Chrome\custom_chrome.exe"
        custom_prof = r"D:\Profiles\my-flow-profile"
        spawned_cmd = []

        env = {
            "FLOW_CHROME_PATH": custom_exe,
            "FLOW_CHROME_PROFILE": custom_prof,
        }

        res = flow_launch.launch_chrome(
            port_checker=lambda port: False,
            spawner=lambda cmd: spawned_cmd.append(cmd),
            file_checker=lambda p: True,
            project_dir=self.tmp,
            env=env,
        )

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("exe"), custom_exe)
        self.assertEqual(res.get("profile"), custom_prof)
        self.assertIn(f"--user-data-dir={custom_prof}", spawned_cmd[0])

    def test_launch_chrome_config_overrides(self):
        cfg_exe = r"C:\Configured\Chrome\chrome.exe"
        cfg_prof = r"C:\Configured\Profile"
        cfg_path = os.path.join(self.tmp, "kit-config.json")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump({"flow_chrome_path": cfg_exe, "flow_chrome_profile": cfg_prof}, fh)

        spawned_cmd = []
        res = flow_launch.launch_chrome(
            port_checker=lambda port: False,
            spawner=lambda cmd: spawned_cmd.append(cmd),
            file_checker=lambda p: True,
            project_dir=self.tmp,
            env={},
        )

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("exe"), cfg_exe)
        self.assertEqual(res.get("profile"), cfg_prof)

    def test_launch_chrome_env_wins_over_config(self):
        cfg_path = os.path.join(self.tmp, "kit-config.json")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump({
                "flow_chrome_path": r"C:\Config\chrome.exe",
                "flow_chrome_profile": r"C:\Config\profile",
            }, fh)

        env = {
            "FLOW_CHROME_PATH": r"C:\Env\chrome.exe",
            "FLOW_CHROME_PROFILE": r"C:\Env\profile",
        }

        res = flow_launch.launch_chrome(
            port_checker=lambda port: False,
            spawner=lambda cmd: None,
            file_checker=lambda p: True,
            project_dir=self.tmp,
            env=env,
        )

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("exe"), r"C:\Env\chrome.exe")
        self.assertEqual(res.get("profile"), r"C:\Env\profile")

    def test_launch_chrome_skip_spawn_when_port_9222_open(self):
        spawner_called = []
        res = flow_launch.launch_chrome(
            port_checker=lambda port: True,
            spawner=lambda cmd: spawner_called.append(cmd),
            project_dir=self.tmp,
            env={},
        )

        self.assertTrue(res.get("ok"))
        self.assertTrue(res.get("already_connected"))
        self.assertEqual(len(spawner_called), 0)

    def test_launch_chrome_fallbacks_in_order(self):
        checked_order = []
        fallback_target = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

        def mock_checker(path):
            checked_order.append(path)
            return path == fallback_target

        res = flow_launch.launch_chrome(
            port_checker=lambda port: False,
            spawner=lambda cmd: None,
            file_checker=mock_checker,
            project_dir=self.tmp,
            env={},
        )

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("exe"), fallback_target)
        self.assertIn(flow_launch.DEFAULT_CHROME_EXE, checked_order)

    def test_launch_chrome_missing_exe_returns_clear_error(self):
        spawner_called = []
        res = flow_launch.launch_chrome(
            port_checker=lambda port: False,
            spawner=lambda cmd: spawner_called.append(cmd),
            file_checker=lambda path: False,
            project_dir=self.tmp,
            env={},
        )

        self.assertFalse(res.get("ok"))
        self.assertIn("error", res)
        self.assertEqual(len(spawner_called), 0)


class TestFlowApiEndpoints(unittest.TestCase):
    """Test /api/flow/* HTTP handlers and background job management."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srk-api-test-")
        flow_api.FLOW_JOB.update(
            state="idle",
            done=0,
            total=0,
            percent=0,
            failed_items=[],
            self_heal=None,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_endpoint_returns_metrics(self):
        status = flow_api.handle_get("/api/flow/status", project_dir=self.tmp)
        self.assertIn("state", status)
        self.assertIn("chrome_connected", status)
        self.assertIn("percent", status)
        self.assertIn("failed_items", status)

    def test_start_pause_resume_endpoints(self):
        with mock.patch.object(flow_api, "_WORKER_THREAD", None):
            with mock.patch("threading.Thread.start"):
                # Fresh start clears failed items and resend queue
                flow_api.FLOW_JOB["failed_items"] = [{"output_name": "OLD"}]
                flow_api.RESEND_QUEUE.append("OLD")

                r_start = flow_api.handle_post("/api/flow/start", {"mode": "download"}, project_dir=self.tmp)
                self.assertTrue(r_start.get("ok"))
                self.assertEqual(r_start.get("state"), "running")
                self.assertEqual(flow_api.FLOW_JOB["failed_items"], [])
                self.assertEqual(flow_api.RESEND_QUEUE, [])

                # Cannot start while running
                with self.assertRaises(ValueError):
                    flow_api.handle_post("/api/flow/start", {"mode": "download"}, project_dir=self.tmp)

                # Pause job
                r_pause = flow_api.handle_post("/api/flow/pause", {}, project_dir=self.tmp)
                self.assertTrue(r_pause.get("ok"))
                self.assertEqual(r_pause.get("state"), "paused")
                self.assertTrue(flow_heal.is_pause_requested())

                # Cannot start while paused
                with self.assertRaises(ValueError):
                    flow_api.handle_post("/api/flow/start", {"mode": "download"}, project_dir=self.tmp)

                # Resume job
                r_resume = flow_api.handle_post("/api/flow/resume", {}, project_dir=self.tmp)
                self.assertTrue(r_resume.get("ok"))
                self.assertEqual(r_resume.get("state"), "running")
                self.assertFalse(flow_heal.is_pause_requested())

                # Resume when running/idle/done/failed is rejected
                for st in ("running", "idle", "done", "failed"):
                    flow_api.FLOW_JOB["state"] = st
                    with self.assertRaises(ValueError):
                        flow_api.handle_post("/api/flow/resume", {}, project_dir=self.tmp)

    def test_resend_endpoint_single_item(self):
        flow_api.FLOW_JOB["failed_items"] = [
            {"output_name": "IMG009", "error": "timed_out"}
        ]

        with mock.patch.object(flow_api, "start_flow_job", return_value={"ok": True, "state": "running"}):
            res = flow_api.handle_post("/api/flow/resend", {"output_name": "IMG009"}, project_dir=self.tmp)
            self.assertTrue(res.get("ok"))
            failed_remaining = [x["output_name"] for x in flow_api.FLOW_JOB["failed_items"]]
            self.assertNotIn("IMG009", failed_remaining)

        # Resend during running job is queued in RESEND_QUEUE
        flow_api.FLOW_JOB["state"] = "running"
        flow_api.RESEND_QUEUE.clear()
        res_queued = flow_api.handle_post("/api/flow/resend", {"output_name": "IMG010"}, project_dir=self.tmp)
        self.assertTrue(res_queued.get("ok"))
        self.assertEqual(res_queued.get("status"), "queued")
        self.assertIn("IMG010", flow_api.RESEND_QUEUE)

    def test_resume_reloads_selectors(self):
        flow_api.FLOW_JOB["state"] = "paused"
        with mock.patch("flow_heal.reload_selectors", wraps=flow_heal.reload_selectors) as spy_reload:
            res = flow_api.handle_post("/api/flow/resume", {}, project_dir=self.tmp)
            self.assertTrue(res.get("ok"))
            spy_reload.assert_called_once_with(project_dir=self.tmp)


class TestSelfHealingDiagnostics(unittest.TestCase):
    """Test self-healing diagnostic bundle schema, sanitization, cap, and safe patching."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srk-heal-test-")
        flow_heal._LAST_FAILURE.update({
            "step": None,
            "selector_key": None,
            "selectors_mtime": None,
            "timestamp_str": None,
            "diag_dir": None,
            "last_time": 0.0,
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_diagnostic_bundle_schema_and_files(self):
        fake_page = FakePage()
        diag_dir, created = flow_heal.dump_diagnostic_bundle(
            page=fake_page,
            step_name="open_ingredients",
            selector_key="ingredients_button",
            attempted_selector="button[aria-label=\"Add ingredients\"]",
            output_name="IMG007",
            attempt_id="att_007_1",
            project_dir=self.tmp,
        )

        self.assertTrue(created)
        self.assertTrue(os.path.isdir(diag_dir))

        # Check files exist
        step_json = os.path.join(diag_dir, "step.json")
        screenshot = os.path.join(diag_dir, "screenshot.png")
        dom_html = os.path.join(diag_dir, "dom.html")

        self.assertTrue(os.path.isfile(step_json))
        self.assertTrue(os.path.isfile(screenshot))
        self.assertTrue(os.path.isfile(dom_html))

        # Check step.json schema
        with open(step_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        expected_keys = {
            "timestamp",
            "step",
            "selector_key",
            "attempted_selector",
            "item_output_name",
            "attempt_id",
        }
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertEqual(data["step"], "open_ingredients")
        self.assertEqual(data["selector_key"], "ingredients_button")
        self.assertEqual(data["item_output_name"], "IMG007")

    def test_diagnostic_sanitization_strips_cookies_and_auth(self):
        sensitive_dom = """
        <html>
          <head>
            <meta http-equiv="Set-Cookie" content="session_id=SECRET123; Path=/">
          </head>
          <body>
            <div>Authorization: Bearer my-secret-auth-token-xyz</div>
            <script>
              document.cookie = "auth_tok=ABC987";
              let cookie = 'secret_cookie_value';
              let auth = {"cookie": "json_cookie_secret", "access_token": "acc_secret_123", "id_token": "id_secret_456", "refresh_token": "ref_secret_789"};
              let token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc_secret_sig";
            </script>
          </body>
        </html>
        """
        page = FakePage(content_html=sensitive_dom)
        diag_dir, _ = flow_heal.dump_diagnostic_bundle(
            page=page,
            step_name="auth_check",
            selector_key="auth_key",
            attempted_selector="div",
            output_name="IMG008",
            attempt_id="att_008_1",
            project_dir=self.tmp,
        )

        with open(os.path.join(diag_dir, "dom.html"), "r", encoding="utf-8") as fh:
            dumped_dom = fh.read()

        self.assertNotIn("SECRET123", dumped_dom)
        self.assertNotIn("my-secret-auth-token-xyz", dumped_dom)
        self.assertNotIn("ABC987", dumped_dom)
        self.assertNotIn("secret_cookie_value", dumped_dom)
        self.assertNotIn("json_cookie_secret", dumped_dom)
        self.assertNotIn("acc_secret_123", dumped_dom)
        self.assertNotIn("id_secret_456", dumped_dom)
        self.assertNotIn("ref_secret_789", dumped_dom)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", dumped_dom)
        self.assertIn("[REDACTED]", dumped_dom)

    def test_diagnostic_cooldown_and_cap_on_repeated_failure(self):
        page = FakePage()
        # First failure creates folder
        diag_1, created_1 = flow_heal.dump_diagnostic_bundle(
            page=page,
            step_name="step_a",
            selector_key="key_a",
            attempted_selector="btn",
            output_name="IMG001",
            attempt_id="att_1",
            project_dir=self.tmp,
        )
        self.assertTrue(created_1)

        # Repeated failure with NO selector changes reuses folder, even after cooldown seconds
        flow_heal._LAST_FAILURE["last_time"] -= 300.0
        diag_2, created_2 = flow_heal.dump_diagnostic_bundle(
            page=page,
            step_name="step_a",
            selector_key="key_a",
            attempted_selector="btn",
            output_name="IMG001",
            attempt_id="att_1",
            project_dir=self.tmp,
        )
        self.assertFalse(created_2)
        self.assertEqual(diag_1, diag_2)

    def test_two_dumps_in_same_second_get_distinct_dirs(self):
        import datetime
        page = FakePage()
        fixed_dt = datetime.datetime(2026, 11, 28, 10, 0, 0, tzinfo=datetime.timezone.utc)
        d1, c1 = flow_heal.dump_diagnostic_bundle(
            page=page,
            step_name="step_1",
            selector_key="key_1",
            attempted_selector="sel1",
            output_name="IMG001",
            attempt_id="att_1",
            project_dir=self.tmp,
            now=fixed_dt,
        )
        d2, c2 = flow_heal.dump_diagnostic_bundle(
            page=page,
            step_name="step_2",
            selector_key="key_2",
            attempted_selector="sel2",
            output_name="IMG002",
            attempt_id="att_2",
            project_dir=self.tmp,
            now=fixed_dt,
        )
        self.assertTrue(c1)
        self.assertTrue(c2)
        self.assertNotEqual(d1, d2)
        self.assertTrue(os.path.basename(d2).endswith("_1"))
        self.assertTrue(os.path.isdir(d1))
        self.assertTrue(os.path.isdir(d2))

    def test_partial_json_and_path_order_matching_load_selectors(self):
        import flow_sync
        partial_file = os.path.join(self.tmp, "flow_selectors.json")
        with open(partial_file, "w", encoding="utf-8") as fh:
            json.dump({"prompt_box": "custom_prompt_box"}, fh)

        loaded = flow_heal.reload_selectors(path=partial_file)
        self.assertEqual(loaded["prompt_box"], "custom_prompt_box")
        self.assertEqual(loaded["submit_button"], flow_sync.BUILTIN_SELECTORS["submit_button"])

        resolved = flow_heal.resolve_selectors_path(path=partial_file)
        self.assertEqual(resolved, os.path.abspath(partial_file))

    def test_prune_old_diagnostic_folders(self):
        errors_dir = os.path.join(self.tmp, ".kit", "flow-errors")
        os.makedirs(errors_dir, exist_ok=True)
        created_dirs = []
        for i in range(12):
            d = os.path.join(errors_dir, f"20261128T1000{i:02d}")
            os.makedirs(d, exist_ok=True)
            created_dirs.append(d)

        flow_heal._prune_old_diagnostic_folders(errors_dir, keep=10)
        remaining = sorted(os.listdir(errors_dir))
        self.assertEqual(len(remaining), 10)
        self.assertNotIn(os.path.basename(created_dirs[0]), remaining)
        self.assertNotIn(os.path.basename(created_dirs[1]), remaining)
        self.assertIn(os.path.basename(created_dirs[2]), remaining)

    def test_self_heal_patch_contract_rejects_py_files(self):
        # Patching flow_selectors.json is allowed
        selectors_file = os.path.join(self.tmp, "flow_selectors.json")
        res = flow_heal.patch_selectors({"prompt_box": "new_box"}, target_path=selectors_file)
        self.assertTrue(os.path.isfile(res))

        # Modifying python source is STRICTLY forbidden (R6)
        py_file = os.path.join(self.tmp, "flow_sync.py")
        with self.assertRaises(ValueError):
            flow_heal.patch_selectors({"prompt_box": "hack"}, target_path=py_file)

    def test_existing_images_never_touched(self):
        images_dir = os.path.join(self.tmp, "images", "scenes")
        os.makedirs(images_dir, exist_ok=True)
        img_path = os.path.join(images_dir, "IMG001_original.png")
        orig_content = b"\x89PNG\r\n\x1a\norig"
        with open(img_path, "wb") as fh:
            fh.write(orig_content)

        # Trigger diagnostics and API actions
        fake_page = FakePage()
        flow_heal.dump_diagnostic_bundle(
            page=fake_page,
            step_name="test_step",
            selector_key="test_sel",
            attempted_selector="sel",
            output_name="IMG001",
            attempt_id="att_1",
            project_dir=self.tmp,
        )
        flow_api.handle_post("/api/flow/pause", {}, project_dir=self.tmp)
        flow_api.handle_post("/api/flow/resume", {}, project_dir=self.tmp)

        # Assert original image file is untouched and unchanged
        self.assertTrue(os.path.isfile(img_path))
        with open(img_path, "rb") as fh:
            self.assertEqual(fh.read(), orig_content)


if __name__ == "__main__":
    unittest.main()
