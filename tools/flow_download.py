# -*- coding: utf-8 -*-
"""Download interception, output naming, duplicate preservation (_alt), and unmatched file isolation.

Part of Phase C Google Flow automation. Intercepts Playwright download events
initiated by clicking download buttons, saving them directly to project folders
(images/scenes/ or images/refs/<KIND>/) according to tools/flowname.py rules.
Uncertain or non-correlated files are safely quarantined into images/_unmatched/
with a manifest.json audit log.
"""
import datetime
import json
import os
import re
import sys

import flowname
from flow_state import replace_file_atomic

DEFAULT_UNMATCHED_DIR = os.path.join("images", "_unmatched")
MANIFEST_FILENAME = "manifest.json"


def resolve_target_directory(stem: str, project_dir: str = ".") -> str:
    """Resolve destination folder: images/refs/<KIND>/ for references, images/scenes/ for scenes."""
    prefix = stem.split("_")[0] if "_" in stem else stem
    if prefix in flowname.REF_KINDS:
        return os.path.abspath(os.path.join(project_dir, "images", "refs", prefix))
    return os.path.abspath(os.path.join(project_dir, "images", "scenes"))


def resolve_non_overwriting_path(target_dir: str, stem: str, ext: str = ".png") -> str:
    """Return a path that never overwrites an existing file, atomically reserving it."""
    if not ext.startswith("."):
        ext = "." + ext
    os.makedirs(target_dir, exist_ok=True)

    idx = 0
    while True:
        cand = flowname.format_alt_name(stem, index=idx, ext=ext)
        dest_path = os.path.join(target_dir, cand)
        try:
            fd = os.open(dest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return dest_path
        except FileExistsError:
            idx += 1


def record_unmatched_file(download_obj, suggested_filename: str, project_dir: str = ".",
                          unmatched_dir: str = None, candidate_attempt_id: str = None,
                          clock=None) -> dict:
    """Quarantine an unmatched download into images/_unmatched/ and append to manifest.json."""
    rel_unmatched = unmatched_dir or DEFAULT_UNMATCHED_DIR
    target_dir = os.path.abspath(os.path.join(project_dir, rel_unmatched))
    os.makedirs(target_dir, exist_ok=True)

    base_name = suggested_filename or "Flow_unmatched.png"
    stem, ext = os.path.splitext(base_name)
    if not ext:
        ext = ".png"

    # Ensure unique filename within unmatched dir atomically
    n = 0
    while True:
        suffix = f"_{n}" if n > 0 else ""
        cand_path = os.path.join(target_dir, f"{stem}{suffix}{ext}")
        try:
            fd = os.open(cand_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            dest_path = cand_path
            break
        except FileExistsError:
            n += 1

    final_filename = os.path.basename(dest_path)

    # Save stream directly into destination
    if hasattr(download_obj, "save_as"):
        download_obj.save_as(dest_path)
    elif hasattr(download_obj, "read"):
        with open(dest_path, "wb") as fh:
            fh.write(download_obj.read())
    elif isinstance(download_obj, (bytes, bytearray)):
        with open(dest_path, "wb") as fh:
            fh.write(download_obj)
    elif isinstance(download_obj, str) and os.path.isfile(download_obj):
        import shutil
        shutil.copy2(download_obj, dest_path)
    else:
        # Create empty placeholder if no payload provided
        with open(dest_path, "wb") as fh:
            fh.write(b"")

    size_bytes = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0

    if clock is None:
        now_dt = datetime.datetime.now(datetime.timezone.utc)
    else:
        val = clock() if callable(clock) else clock
        if isinstance(val, (int, float)):
            now_dt = datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc)
        elif isinstance(val, datetime.datetime):
            now_dt = val if val.tzinfo is not None else val.replace(tzinfo=datetime.timezone.utc)
        elif isinstance(val, str):
            now_dt = datetime.datetime.fromisoformat(val)
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=datetime.timezone.utc)
        else:
            now_dt = datetime.datetime.now(datetime.timezone.utc)

    now_iso = now_dt.isoformat()

    manifest_path = os.path.join(target_dir, MANIFEST_FILENAME)
    manifest_data = []
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
                if isinstance(loaded, list):
                    manifest_data = loaded
        except (OSError, ValueError):
            manifest_data = []

    entry = {
        "filename": final_filename,
        "timestamp": now_iso,
        "size_bytes": size_bytes,
        "candidate_attempt_id": candidate_attempt_id,
    }
    manifest_data.append(entry)

    tmp_path = manifest_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest_data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    replace_file_atomic(tmp_path, manifest_path)

    entry["path"] = dest_path
    entry["rel_path"] = os.path.relpath(dest_path, project_dir).replace("\\", "/")
    return entry


def correlate_download(suggested_filename: str, expected_item: dict) -> bool:
    """Check whether a downloaded file definitively correlates with expected submission context.

    Returns True if correlated, False if uncertain.
    """
    if not suggested_filename or not expected_item:
        return False

    output_name = expected_item.get("output_name", "")
    raw_prompt = expected_item.get("raw_prompt", "")

    expected_stem = flowname.resolve_output_stem(raw_prompt, output_name)
    expected_base = output_name.split("_")[0] if not output_name.startswith("IMG") else (
        re.match(r"(IMG\d{3,4})", output_name).group(1) if re.match(r"(IMG\d{3,4})", output_name) else output_name
    )
    expected_slug = flowname.output_slug(raw_prompt, expected_base)

    parsed = flowname.parse(suggested_filename)
    if parsed:
        file_base = parsed.get("base")
        file_slug = parsed.get("slug")
        # Base must match expected base
        if file_base == expected_base:
            if expected_slug:
                return flowname.slugs_match(file_slug, expected_slug)
            return True
        return False

    # Fallback comparison on raw stems
    file_stem, _ = os.path.splitext(suggested_filename)
    # Strip browser counter ' (1)' if present
    file_stem = re.sub(r"\s\(\d+\)$", "", file_stem).strip()

    if file_stem == expected_stem or file_stem.startswith(expected_stem + "_"):
        return True

    if file_stem == expected_base or file_stem.startswith(expected_base + "_"):
        if expected_slug:
            # Check if expected slug appears in filename
            return expected_slug.lower() in file_stem.lower()
        return True

    return False


def intercept_and_save_download(page, download_trigger_fn, expected_item: dict,
                                project_dir: str = ".", unmatched_dir: str = None,
                                timeout_s: float = 30.0, candidate_attempt_id: str = None,
                                clock=None) -> dict:
    """Intercept download event from trigger and save directly to target or unmatched dir.

    Guarantees:
    - Never uses user's ~/Downloads directory
    - Intercepts real Playwright expect_download event (not <img> preview)
    - If match is definitive: saves to resolved [OUTPUT NAME] using flowname rules
    - If existing file exists: saves with _alt suffix, never overwriting or renaming
    - If uncertain: isolates into images/_unmatched/ with manifest.json entry
    """
    download = None
    if hasattr(page, "expect_download"):
        try:
            with page.expect_download(timeout=int(timeout_s * 1000)) as download_info:
                download_trigger_fn()
            download = download_info.value
        except Exception as e:
            sys.stderr.write(f"Warning: Download event timeout or error: {e}\n")
            return {"status": "error", "error": str(e), "output_name": expected_item.get("output_name")}
    else:
        # Duck-typed or direct fallback
        download = download_trigger_fn()

    if download is None:
        return {"status": "no_download", "output_name": expected_item.get("output_name")}

    suggested_filename = getattr(download, "suggested_filename", "")
    if not suggested_filename:
        suggested_filename = "download.png"

    is_matched = correlate_download(suggested_filename, expected_item)

    if is_matched:
        raw_prompt = expected_item.get("raw_prompt", "")
        output_name = expected_item.get("output_name", "")
        stem = flowname.resolve_output_stem(raw_prompt, output_name)
        ext = os.path.splitext(suggested_filename)[1] or ".png"

        target_dir = resolve_target_directory(stem, project_dir=project_dir)
        dest_path = resolve_non_overwriting_path(target_dir, stem, ext=ext)

        if hasattr(download, "save_as"):
            download.save_as(dest_path)
        elif hasattr(download, "read"):
            with open(dest_path, "wb") as fh:
                fh.write(download.read())
        elif isinstance(download, (bytes, bytearray)):
            with open(dest_path, "wb") as fh:
                fh.write(download)

        rel_dest = os.path.relpath(dest_path, project_dir).replace("\\", "/")
        is_alt = flowname.is_alt_name(os.path.basename(dest_path))

        return {
            "status": "saved",
            "path": dest_path,
            "rel_path": rel_dest,
            "is_alt": is_alt,
            "output_name": output_name,
            "attempt_id": candidate_attempt_id,
        }
    else:
        # Uncertain download: quarantine
        entry = record_unmatched_file(
            download_obj=download,
            suggested_filename=suggested_filename,
            project_dir=project_dir,
            unmatched_dir=unmatched_dir,
            candidate_attempt_id=candidate_attempt_id,
            clock=clock,
        )
        return {
            "status": "unmatched",
            "path": entry.get("path"),
            "rel_path": entry.get("rel_path"),
            "manifest_entry": entry,
            "output_name": expected_item.get("output_name"),
            "attempt_id": candidate_attempt_id,
        }
