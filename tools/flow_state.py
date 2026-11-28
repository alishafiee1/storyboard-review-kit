# -*- coding: utf-8 -*-
"""State tracking, atomic persistence, attempt ID generation, and timing logs for Flow sync."""
import contextlib
import datetime
import hashlib
import json
import os
import re
import sys
import time
import uuid

DEFAULT_STATE_REL = os.path.join(".kit", "flow-state.json")
DEFAULT_TIMING_REL = os.path.join(".kit", "flow-timing.log")
SCHEMA_VERSION = 2


def generate_attempt_id() -> str:
    """Monotonic attempt ID combining millisecond timestamp and random suffix."""
    millis = int(time.time() * 1000)
    rand_suffix = uuid.uuid4().hex[:6]
    return f"att_{millis}_{rand_suffix}"


def compute_prompt_hash(text: str) -> str:
    """Stable SHA-256 hash of prompt text.

    Normalizes CRLF line breaks and strips any leading [REFS TO ATTACH: ...] line
    so that only the English prompt text itself is hashed.
    """
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and re.match(r"^\s*\[REFS TO ATTACH:[^\]]*\]\s*$", lines[0]):
        lines = lines[1:]
    clean = "\n".join(lines).strip()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def extract_prompt_text(text: str) -> str:
    """Extract English prompt body without reference attachment directive."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and re.match(r"^\s*\[REFS TO ATTACH:[^\]]*\]\s*$", lines[0]):
        lines = lines[1:]
    return "\n".join(lines).strip()


def replace_file_atomic(tmp_path: str, target_path: str):
    """Atomic file replacement with retry for Windows file locks."""
    for _ in range(40):
        try:
            return os.replace(tmp_path, target_path)
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp_path, target_path)


def resolve_state_path(path: str = None, project_dir: str = None) -> str:
    if path:
        return os.path.abspath(path)
    base = project_dir or "."
    return os.path.abspath(os.path.join(base, DEFAULT_STATE_REL))


def resolve_timing_path(path: str = None, project_dir: str = None) -> str:
    if path:
        return os.path.abspath(path)
    base = project_dir or "."
    return os.path.abspath(os.path.join(base, DEFAULT_TIMING_REL))


def default_state() -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "last_run": None,
        "daily_submitted_count": 0,
        "last_batch_at": None,
        "items": {}
    }


def get_daily_submitted_count(state: dict, now: datetime.datetime = None) -> int:
    """Return submitted count within rolling 24-hour window, resetting if >24h elapsed."""
    last_batch_at = state.get("last_batch_at")
    if not last_batch_at:
        return state.get("daily_submitted_count", 0)

    current_time = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        dt = datetime.datetime.fromisoformat(last_batch_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        if (current_time - dt).total_seconds() > 24 * 3600:
            return 0
    except Exception:
        pass
    return state.get("daily_submitted_count", 0)


def increment_daily_counter(state: dict, count: int = 1, now_iso: str = None, now: datetime.datetime = None) -> int:
    """Increment daily submitted count and update last_batch_at."""
    if now is None and now_iso:
        try:
            now = datetime.datetime.fromisoformat(now_iso)
        except Exception:
            pass
    curr = get_daily_submitted_count(state, now=now)
    new_count = curr + count
    state["daily_submitted_count"] = new_count
    if now_iso:
        state["last_batch_at"] = now_iso
    return new_count


def load_state(path: str = None, project_dir: str = None) -> dict:
    """Load .kit/flow-state.json schema version 2. Returns fresh state if missing or invalid."""
    target = resolve_state_path(path, project_dir)
    if not os.path.isfile(target):
        return default_state()
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return default_state()
        if data.get("schemaVersion") != SCHEMA_VERSION:
            data["schemaVersion"] = SCHEMA_VERSION
        if not isinstance(data.get("items"), dict):
            data["items"] = {}
        data.setdefault("daily_submitted_count", 0)
        data.setdefault("last_batch_at", None)
        return data
    except (OSError, ValueError):
        return default_state()


def save_state(state: dict, path: str = None, project_dir: str = None):
    """Atomically save state to .kit/flow-state.json."""
    target = resolve_state_path(path, project_dir)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp_path = target + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    replace_file_atomic(tmp_path, target)


def record_item_state(state: dict, output_name: str, prompt_hash: str, status: str,
                      attempt_id: str = None, refs: list = None,
                      batch_id: int = None, submitted_at: str = None,
                      now_iso: str = None, retries_count: int = None,
                      saved_path: str = None, completed_at: str = None) -> dict:
    """Update or insert a queue item record in state."""
    items = state.setdefault("items", {})
    existing = items.get(output_name, {})
    att_id = attempt_id or existing.get("attempt_id") or generate_attempt_id()
    if now_iso is None:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "output_name": output_name,
        "prompt_hash": prompt_hash,
        "attempt_id": att_id,
        "status": status,
        "updated_at": now_iso
    }
    if refs is not None:
        record["refs"] = list(refs)
    elif "refs" in existing:
        record["refs"] = existing["refs"]

    if batch_id is not None:
        record["batch_id"] = batch_id
    elif "batch_id" in existing:
        record["batch_id"] = existing["batch_id"]

    if submitted_at is not None:
        record["submitted_at"] = submitted_at
    elif "submitted_at" in existing:
        record["submitted_at"] = existing["submitted_at"]

    if retries_count is not None:
        record["retries_count"] = retries_count
    elif "retries_count" in existing:
        record["retries_count"] = existing["retries_count"]

    if saved_path is not None:
        record["saved_path"] = saved_path
    elif "saved_path" in existing:
        record["saved_path"] = existing["saved_path"]

    if completed_at is not None:
        record["completed_at"] = completed_at
    elif "completed_at" in existing:
        record["completed_at"] = existing["completed_at"]

    items[output_name] = record
    state["last_run"] = now_iso
    return record


def log_timing_entry(step_name: str, elapsed_ms: int, outcome: str = "ok",
                     log_path: str = None, project_dir: str = None, verbose: bool = False):
    """Write one timing record to flow-timing.log."""
    target = resolve_timing_path(log_path, project_dir)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = f"{now_iso}\t{elapsed_ms}ms\t{step_name}\t{outcome}\n"
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(line)
    if verbose:
        sys.stdout.write(f"[{elapsed_ms:>4}ms] {step_name}: {outcome}\n")


@contextlib.contextmanager
def time_step(step_name: str, log_path: str = None, project_dir: str = None, verbose: bool = False):
    """Context manager measuring execution time and logging step completion."""
    t0 = time.perf_counter()
    outcome = "ok"
    try:
        yield
    except Exception as e:
        outcome = f"error: {type(e).__name__}: {e}"
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        log_timing_entry(step_name, elapsed_ms, outcome=outcome, log_path=log_path,
                         project_dir=project_dir, verbose=verbose)
