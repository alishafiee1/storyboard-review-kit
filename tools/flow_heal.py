# -*- coding: utf-8 -*-
"""Self-healing diagnostics, pause/resume signaling, and safe patch contract.

When a DOM or selector interaction fails, execution pauses and exports
a sanitized diagnostic bundle into .kit/flow-errors/<timestamp>/:
  - step.json: metadata with failing step, selector key, attempt ID, timestamp
  - screenshot.png: viewport snapshot
  - dom.html: sanitized DOM snippet

External agents or operators may update ONLY tools/flow_selectors.json.
Modifying Python source is strictly forbidden. Resuming reloads selectors
and retries the failing step.
"""
import datetime
import json
import os
import re
import struct
import threading
import time
import zlib

_PAUSE_EVENT = threading.Event()
_RESUME_EVENT = threading.Event()
_RESUME_EVENT.set()  # Initially running

# Cooldown and repeat failure tracker
_LAST_FAILURE = {
    "step": None,
    "selector_key": None,
    "selectors_mtime": None,
    "timestamp_str": None,
    "diag_dir": None,
    "last_time": 0.0,
}
_MAX_DIAG_FOLDERS = 10
_DIAG_COOLDOWN_SECONDS = 60.0


def request_pause():
    """Request active flow job to pause."""
    _PAUSE_EVENT.set()
    _RESUME_EVENT.clear()


def request_resume():
    """Signal paused flow job to resume."""
    _PAUSE_EVENT.clear()
    _RESUME_EVENT.set()


def is_pause_requested() -> bool:
    """Check if pause was requested."""
    return _PAUSE_EVENT.is_set()


def is_running() -> bool:
    """Check if execution is unpaused."""
    return _RESUME_EVENT.is_set()


def wait_if_paused(on_wait=None, timeout: float = None) -> bool:
    """Wait if pause was requested until resumed."""
    if _PAUSE_EVENT.is_set():
        if on_wait:
            on_wait()
        return _RESUME_EVENT.wait(timeout=timeout)
    return True


def sanitize_content(text: str) -> str:
    """Strip cookies, auth headers, and session tokens from exported diagnostics."""
    if not text:
        return ""
    s = str(text)
    # Strip meta http-equiv Set-Cookie
    s = re.sub(r"(?i)<meta\s+[^>]*http-equiv=[\"']?set-cookie[\"']?[^>]*>", "<meta http-equiv=\"[REDACTED]\" content=\"[REDACTED]\">", s)
    # Strip HTTP headers and meta tags
    s = re.sub(r"(?i)\bset-cookie\s*:\s*[^\r\n;\"]*", "Set-Cookie: [REDACTED]", s)
    s = re.sub(r"(?i)\bauthorization\s*:\s*[^\r\n]+", "Authorization: [REDACTED]", s)
    s = re.sub(r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.\+/=]+", "Bearer [REDACTED]", s)
    # Strip cookie assignments, JSON, & expressions
    s = re.sub(r"(?i)([\"']?cookie[\"']?\s*[:=]\s*[\"'])[^\"']*([\"'])", r"\1[REDACTED]\2", s)
    s = re.sub(r"(?i)\bcookie\s*=\s*['\"][^'\"]*['\"]", "cookie=\"[REDACTED]\"", s)
    s = re.sub(r"(?i)\bcookie\s*:\s*[^\r\n;]+", "cookie: [REDACTED]", s)
    s = re.sub(r"(?i)\bdocument\.cookie\s*=\s*[^;\n]+", "document.cookie = \"[REDACTED]\"", s)
    # Strip access_token, id_token, refresh_token, session identifiers
    s = re.sub(r"(?i)([\"']?(?:access_token|id_token|refresh_token|session_?id|session_?token|auth_?token)[\"']?\s*[:=]\s*[\"']?)[a-zA-Z0-9_\-\.\+/=]+([\"']?)", r"\1[REDACTED]\2", s)
    # Strip eyJ… JWT-like strings
    s = re.sub(r"\beyJ[a-zA-Z0-9_\-\.]{15,}", "[REDACTED]", s)
    return s


def _dummy_png_bytes() -> bytes:
    """Generate minimal valid 16x9 PNG bytes for fallback screenshots."""
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * 16 for _ in range(9))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 9, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def resolve_selectors_path(project_dir: str = None, path: str = None) -> str:
    """Resolve flow_selectors.json path with candidate order matching flow_sync.load_selectors."""
    if project_dir and (project_dir.endswith(".json") or os.path.isfile(project_dir)) and not path:
        path = project_dir
        project_dir = None

    candidate_paths = []
    if path:
        candidate_paths.append(os.path.abspath(path))
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_paths.append(os.path.join(tools_dir, "flow_selectors.json"))
    if project_dir:
        candidate_paths.append(os.path.join(os.path.abspath(project_dir), "tools", "flow_selectors.json"))

    for p in candidate_paths:
        if os.path.isfile(p):
            return p
    return candidate_paths[0] if path else candidate_paths[1]


def get_selectors_mtime(project_dir: str = None, path: str = None) -> float:
    """Get modification time of flow_selectors.json."""
    p = resolve_selectors_path(project_dir=project_dir, path=path)
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


def reload_selectors(path: str = None, project_dir: str = None) -> dict:
    """Reload tools/flow_selectors.json, merging built-ins so missing keys are not dropped."""
    import flow_sync
    res = dict(flow_sync.BUILTIN_SELECTORS)
    target = resolve_selectors_path(project_dir=project_dir, path=path)
    if os.path.isfile(target):
        try:
            with open(target, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    res.update(data)
                    return res
        except Exception:
            pass
    return res


def patch_selectors(new_selectors: dict, target_path: str = None, project_dir: str = None) -> str:
    """Safely patch tools/flow_selectors.json.

    Rule R6: Modifying Python source code during self-healing is strictly forbidden.
    """
    if not isinstance(new_selectors, dict):
        raise TypeError("new_selectors must be a dictionary")

    dest = target_path or resolve_selectors_path(project_dir)
    norm = os.path.normpath(dest)

    # Hard invariant: NEVER write to .py files
    if norm.endswith(".py"):
        raise ValueError("Modifying Python source code during self-healing is strictly forbidden.")

    if not norm.endswith("flow_selectors.json"):
        raise ValueError("Self-healing may only patch flow_selectors.json.")

    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    tmp_path = dest + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(new_selectors, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp_path, dest)
    return dest


def _prune_old_diagnostic_folders(errors_dir: str, keep: int = _MAX_DIAG_FOLDERS):
    """Enforce cap on diagnostic folders to prevent unbounded disk usage."""
    if not os.path.isdir(errors_dir):
        return
    try:
        entries = [
            os.path.join(errors_dir, d)
            for d in os.listdir(errors_dir)
            if os.path.isdir(os.path.join(errors_dir, d))
        ]
        entries.sort()
        while len(entries) > keep:
            oldest = entries.pop(0)
            try:
                import shutil
                shutil.rmtree(oldest, ignore_errors=True)
            except Exception:
                pass
    except Exception:
        pass


def dump_diagnostic_bundle(
    page,
    step_name: str,
    selector_key: str,
    attempted_selector: str,
    output_name: str,
    attempt_id: str,
    project_dir: str = None,
    now: datetime.datetime = None,
) -> tuple:
    """Export self-healing diagnostic snapshot into .kit/flow-errors/<timestamp>/.

    Returns (diag_dir, was_created_new_bool).
    Enforces cooldown and cap so repeated failures without fix do not spawn
    infinite directories.
    """
    root = os.path.abspath(project_dir or ".")
    errors_dir = os.path.join(root, ".kit", "flow-errors")
    os.makedirs(errors_dir, exist_ok=True)

    curr_mtime = get_selectors_mtime(project_dir)
    curr_time = time.time()

    # Check repeated failure rule:
    # Dedupe on unchanged (step, selector_key, selectors_mtime) with no time-based expiry.
    if (
        _LAST_FAILURE["step"] == step_name
        and _LAST_FAILURE["selector_key"] == selector_key
        and _LAST_FAILURE["selectors_mtime"] == curr_mtime
        and _LAST_FAILURE["diag_dir"]
        and os.path.isdir(_LAST_FAILURE["diag_dir"])
    ):
        return _LAST_FAILURE["diag_dir"], False

    dt = now or datetime.datetime.now(datetime.timezone.utc)
    ts_folder = dt.strftime("%Y%m%dT%H%M%S")
    ts_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    diag_dir = os.path.join(errors_dir, ts_folder)
    if os.path.exists(diag_dir):
        suffix = 1
        while os.path.exists(f"{diag_dir}_{suffix}"):
            suffix += 1
        diag_dir = f"{diag_dir}_{suffix}"
    os.makedirs(diag_dir, exist_ok=True)

    # 1. step.json
    step_data = {
        "timestamp": ts_iso,
        "step": sanitize_content(step_name),
        "selector_key": sanitize_content(selector_key),
        "attempted_selector": sanitize_content(attempted_selector),
        "item_output_name": sanitize_content(output_name),
        "attempt_id": sanitize_content(attempt_id),
    }
    step_json_path = os.path.join(diag_dir, "step.json")
    with open(step_json_path, "w", encoding="utf-8") as fh:
        json.dump(step_data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # 2. screenshot.png
    screenshot_path = os.path.join(diag_dir, "screenshot.png")
    screenshot_saved = False
    if page is not None and hasattr(page, "screenshot"):
        try:
            res = page.screenshot(path=screenshot_path)
            if isinstance(res, (bytes, bytearray)) and not os.path.isfile(screenshot_path):
                with open(screenshot_path, "wb") as sfh:
                    sfh.write(res)
            screenshot_saved = os.path.isfile(screenshot_path) and os.path.getsize(screenshot_path) > 0
        except Exception:
            screenshot_saved = False

    if not screenshot_saved:
        with open(screenshot_path, "wb") as sfh:
            sfh.write(_dummy_png_bytes())

    # 3. dom.html
    dom_content = ""
    if page is not None:
        try:
            if hasattr(page, "content") and callable(page.content):
                dom_content = page.content()
            elif hasattr(page, "evaluate") and callable(page.evaluate):
                dom_content = page.evaluate("document.documentElement.outerHTML")
        except Exception as e:
            dom_content = f"<!-- Error getting DOM: {e} -->"

    if not dom_content:
        dom_content = "<!-- DOM unavailable -->"

    sanitized_dom = sanitize_content(dom_content)
    dom_path = os.path.join(diag_dir, "dom.html")
    with open(dom_path, "w", encoding="utf-8") as fh:
        fh.write(sanitized_dom)

    # Prune oldest if over cap
    _prune_old_diagnostic_folders(errors_dir, keep=_MAX_DIAG_FOLDERS)

    # Update tracker
    _LAST_FAILURE["step"] = step_name
    _LAST_FAILURE["selector_key"] = selector_key
    _LAST_FAILURE["selectors_mtime"] = curr_mtime
    _LAST_FAILURE["timestamp_str"] = ts_folder
    _LAST_FAILURE["diag_dir"] = diag_dir
    _LAST_FAILURE["last_time"] = curr_time

    return diag_dir, True
