# -*- coding: utf-8 -*-
"""Unit tests for tools/flow_download.py and flowname formatting (Phase C).

Verifies output naming via flowname rules, non-overwriting guarantees,
_alt duplicate preservation, unmatched isolation with manifest.json,
and download event interception without touching ~/Downloads.
No live browser, network, or Playwright binaries required.
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import flow_download
import flowname


class FakeDownload:
    """Mock Playwright Download object."""

    def __init__(self, suggested_filename="Flow_output.png", data=b"png_image_binary_data"):
        self.suggested_filename = suggested_filename
        self.data = data
        self.saved_to = None

    def save_as(self, path):
        self.saved_to = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(self.data)


class FakePageWithDownload:
    """Mock Playwright page supporting expect_download context manager."""

    def __init__(self, download_obj):
        self.download_obj = download_obj
        self.actions_log = []

    def expect_download(self, timeout=30000):
        self.actions_log.append(f"expect_download:{timeout}")
        page_ref = self

        class _ExpectDownloadContext:
            def __init__(self, dl):
                self.value = dl

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        return _ExpectDownloadContext(self.download_obj)


class TestFlowNameHelpers(unittest.TestCase):
    """Test flowname output stem resolution and _alt formatting."""

    def test_resolve_output_stem_with_directive(self):
        prompt = "[OUTPUT NAME: IMG045_cave_wall]\n[REFS TO ATTACH: STYLE_ANCHOR]\nCave interior."
        stem = flowname.resolve_output_stem(prompt, "IMG045")
        self.assertEqual(stem, "IMG045_cave_wall")

    def test_resolve_output_stem_without_directive_falls_back_to_base(self):
        prompt = "Simple outdoor landscape."
        stem = flowname.resolve_output_stem(prompt, "IMG010")
        self.assertEqual(stem, "IMG010")

    def test_format_alt_name_indices(self):
        self.assertEqual(flowname.format_alt_name("IMG005", index=0), "IMG005.png")
        self.assertEqual(flowname.format_alt_name("IMG005", index=1), "IMG005_alt.png")
        self.assertEqual(flowname.format_alt_name("IMG005", index=2), "IMG005_alt2.png")
        self.assertEqual(flowname.format_alt_name("IMG005", index=3, ext=".jpg"), "IMG005_alt3.jpg")

    def test_is_alt_name_detection(self):
        self.assertFalse(flowname.is_alt_name("IMG005.png"))
        self.assertFalse(flowname.is_alt_name("IMG005_exterior.png"))
        self.assertTrue(flowname.is_alt_name("IMG005_alt.png"))
        self.assertTrue(flowname.is_alt_name("IMG005_alt2.png"))
        self.assertTrue(flowname.is_alt_name("IMG005_exterior_alt.png"))
        self.assertTrue(flowname.is_alt_name("IMG005_exterior_alt99.jpg"))


class TestTargetDirectoryResolution(unittest.TestCase):
    """Test directory destinations for scenes vs references."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scene_targets_images_scenes(self):
        target = flow_download.resolve_target_directory("IMG001", project_dir=self.tmp)
        expected = os.path.join(self.tmp, "images", "scenes")
        self.assertEqual(target, expected)

    def test_reference_targets_images_refs_kind(self):
        target_ch = flow_download.resolve_target_directory("CH_MIMO", project_dir=self.tmp)
        self.assertEqual(target_ch, os.path.join(self.tmp, "images", "refs", "CH"))

        target_loc = flow_download.resolve_target_directory("LOC_CAVE_take1", project_dir=self.tmp)
        self.assertEqual(target_loc, os.path.join(self.tmp, "images", "refs", "LOC"))

        target_style = flow_download.resolve_target_directory("STYLE_ANCHOR", project_dir=self.tmp)
        self.assertEqual(target_style, os.path.join(self.tmp, "images", "refs", "STYLE"))


class TestNonOverwritingAndAltPreservation(unittest.TestCase):
    """Test duplicate preservation via _alt suffixes without overwriting or renaming."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.scenes_dir = os.path.join(self.tmp, "images", "scenes")
        os.makedirs(self.scenes_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_initial_download_saved_without_suffix(self):
        path = flow_download.resolve_non_overwriting_path(self.scenes_dir, "IMG002", ext=".png")
        self.assertEqual(os.path.basename(path), "IMG002.png")

    def test_second_arrival_gets_alt_suffix_and_never_overwrites(self):
        orig_file = os.path.join(self.scenes_dir, "IMG002.png")
        with open(orig_file, "wb") as fh:
            fh.write(b"original_content")

        path2 = flow_download.resolve_non_overwriting_path(self.scenes_dir, "IMG002", ext=".png")
        self.assertEqual(os.path.basename(path2), "IMG002_alt.png")

        # Save duplicate
        with open(path2, "wb") as fh:
            fh.write(b"duplicate_content")

        # Original must remain untouched byte-for-byte
        with open(orig_file, "rb") as fh:
            self.assertEqual(fh.read(), b"original_content")

    def test_third_arrival_gets_alt2_suffix(self):
        with open(os.path.join(self.scenes_dir, "IMG002.png"), "wb") as fh:
            fh.write(b"v1")
        with open(os.path.join(self.scenes_dir, "IMG002_alt.png"), "wb") as fh:
            fh.write(b"v2")

        path3 = flow_download.resolve_non_overwriting_path(self.scenes_dir, "IMG002", ext=".png")
        self.assertEqual(os.path.basename(path3), "IMG002_alt2.png")

    def test_two_saves_to_the_same_name_never_overwrite(self):
        # Two saves targeting the exact same stem never overwrite
        p1 = flow_download.resolve_non_overwriting_path(self.scenes_dir, "IMG010", ext=".png")
        with open(p1, "wb") as fh:
            fh.write(b"data_one")

        p2 = flow_download.resolve_non_overwriting_path(self.scenes_dir, "IMG010", ext=".png")
        with open(p2, "wb") as fh:
            fh.write(b"data_two")

        self.assertNotEqual(p1, p2)
        self.assertEqual(os.path.basename(p1), "IMG010.png")
        self.assertEqual(os.path.basename(p2), "IMG010_alt.png")
        with open(p1, "rb") as fh:
            self.assertEqual(fh.read(), b"data_one")
        with open(p2, "rb") as fh:
            self.assertEqual(fh.read(), b"data_two")

        # Also verify concurrent reservations via threads never collide or overwrite
        from concurrent.futures import ThreadPoolExecutor

        def reserve_and_write(val):
            p = flow_download.resolve_non_overwriting_path(self.scenes_dir, "CONCURRENT_IMG", ext=".png")
            with open(p, "wb") as fh:
                fh.write(val)
            return p

        with ThreadPoolExecutor(max_workers=8) as ex:
            paths = list(ex.map(reserve_and_write, [f"c_{i}".encode("utf-8") for i in range(8)]))

        self.assertEqual(len(paths), 8)
        self.assertEqual(len(set(paths)), 8)  # all unique paths
        for p in paths:
            self.assertTrue(os.path.isfile(p))
            self.assertTrue(os.path.getsize(p) > 0)


class TestUnmatchedManifestIsolation(unittest.TestCase):
    """Test routing uncertain files to images/_unmatched/ with manifest.json."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unmatched_directory_created_automatically_on_first_unmatched_file(self):
        unmatched_dir = os.path.join(self.tmp, "images", "_unmatched")
        self.assertFalse(os.path.exists(unmatched_dir))

        dl = FakeDownload(suggested_filename="Flow_random_999.png", data=b"unmatched_bytes")
        entry = flow_download.record_unmatched_file(
            download_obj=dl,
            suggested_filename="Flow_random_999.png",
            project_dir=self.tmp,
            candidate_attempt_id="att_test_1",
            clock=lambda: datetime.datetime(2026, 11, 28, 10, 20, 5, tzinfo=datetime.timezone.utc),
        )

        self.assertTrue(os.path.isdir(unmatched_dir))
        self.assertEqual(entry["filename"], "Flow_random_999.png")
        self.assertEqual(entry["size_bytes"], len(b"unmatched_bytes"))
        self.assertEqual(entry["candidate_attempt_id"], "att_test_1")
        self.assertEqual(entry["timestamp"], "2026-11-28T10:20:05+00:00")

        # Verify manifest.json schema
        manifest_path = os.path.join(unmatched_dir, "manifest.json")
        self.assertTrue(os.path.isfile(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertIsInstance(manifest, list)
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["filename"], "Flow_random_999.png")
        self.assertEqual(manifest[0]["size_bytes"], len(b"unmatched_bytes"))
        self.assertEqual(manifest[0]["candidate_attempt_id"], "att_test_1")

    def test_multiple_unmatched_files_appended_to_manifest(self):
        for i in (1, 2):
            dl = FakeDownload(suggested_filename=f"Flow_odd_{i}.png", data=b"bytes")
            flow_download.record_unmatched_file(
                download_obj=dl,
                suggested_filename=f"Flow_odd_{i}.png",
                project_dir=self.tmp,
                candidate_attempt_id=f"att_{i}",
                clock=lambda: datetime.datetime(2026, 11, 28, 10, 0, 0, tzinfo=datetime.timezone.utc),
            )

        manifest_path = os.path.join(self.tmp, "images", "_unmatched", "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertEqual(len(manifest), 2)
        self.assertEqual(manifest[0]["filename"], "Flow_odd_1.png")
        self.assertEqual(manifest[1]["filename"], "Flow_odd_2.png")


class TestDownloadCorrelation(unittest.TestCase):
    """Test correlation logic distinguishing definitive matches from uncertain ones."""

    def test_correlate_matches_matching_base_and_slug(self):
        item = {
            "output_name": "IMG002",
            "raw_prompt": "[OUTPUT NAME: IMG002_exterior]\nExterior shot.",
        }
        self.assertTrue(flow_download.correlate_download("IMG002_exterior.png", item))
        self.assertTrue(flow_download.correlate_download("IMG002_exterior_edfa6fe0.png", item))
        self.assertTrue(flow_download.correlate_download("IMG002_exterior (1).png", item))

    def test_correlate_rejects_different_base(self):
        item = {
            "output_name": "IMG002",
            "raw_prompt": "[OUTPUT NAME: IMG002_exterior]\nExterior shot.",
        }
        self.assertFalse(flow_download.correlate_download("IMG009_forest.png", item))
        self.assertFalse(flow_download.correlate_download("CH_MIMO.png", item))

    def test_correlate_rejects_mismatched_slug(self):
        item = {
            "output_name": "IMG002",
            "raw_prompt": "[OUTPUT NAME: IMG002_exterior]\nExterior shot.",
        }
        self.assertFalse(flow_download.correlate_download("IMG002_interior_kitchen.png", item))


class TestInterceptAndSaveIntegration(unittest.TestCase):
    """Test full intercept_and_save_download workflow with fake download triggers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_intercept_saves_matched_file_directly_to_project_images(self):
        dl = FakeDownload(suggested_filename="IMG003_forest.png", data=b"forest_data")
        page = FakePageWithDownload(dl)
        item = {
            "output_name": "IMG003",
            "raw_prompt": "[OUTPUT NAME: IMG003_forest]\nA lush pine forest.",
        }

        def trigger():
            pass

        res = flow_download.intercept_and_save_download(
            page=page,
            download_trigger_fn=trigger,
            expected_item=item,
            project_dir=self.tmp,
            candidate_attempt_id="att_003_1",
        )

        self.assertEqual(res["status"], "saved")
        self.assertIn("images/scenes/IMG003_forest.png", res["rel_path"])
        self.assertTrue(os.path.isfile(res["path"]))
        with open(res["path"], "rb") as fh:
            self.assertEqual(fh.read(), b"forest_data")

    def test_intercept_routes_uncertain_download_to_unmatched_dir(self):
        dl = FakeDownload(suggested_filename="Random_unknown_image.png", data=b"uncertain_bytes")
        page = FakePageWithDownload(dl)
        item = {
            "output_name": "IMG004",
            "raw_prompt": "[OUTPUT NAME: IMG004_dusk]\nA dusk scene.",
        }

        def trigger():
            pass

        res = flow_download.intercept_and_save_download(
            page=page,
            download_trigger_fn=trigger,
            expected_item=item,
            project_dir=self.tmp,
            candidate_attempt_id="att_004_1",
        )

        self.assertEqual(res["status"], "unmatched")
        self.assertIn("_unmatched", res["path"])
        self.assertTrue(os.path.isfile(res["path"]))

        # Check manifest recorded
        manifest_file = os.path.join(self.tmp, "images", "_unmatched", "manifest.json")
        self.assertTrue(os.path.isfile(manifest_file))
        with open(manifest_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data[0]["candidate_attempt_id"], "att_004_1")


if __name__ == "__main__":
    unittest.main()
