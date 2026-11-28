# -*- coding: utf-8 -*-
"""Flow automation HTTP API handlers and separate background job state.

Implements /api/flow/* endpoints:
  - POST /api/flow/launch-chrome: Spawns or detects Chrome with remote debugging.
  - POST /api/flow/start: Starts Flow generation background job.
  - POST /api/flow/pause: Requests job pause.
  - POST /api/flow/resume: Resumes paused job and reloads flow_selectors.json.
  - POST /api/flow/resend: Re-dispatches a single failed item.
  - GET  /api/flow/status (and /api/flow/job): Live progress metrics and failed items.
"""
import copy
import datetime
import os
import threading
import time

import flow_heal
import flow_launch
import flow_state
from kitcore import ROOT

FLOW_LOCK = threading.Lock()
RESEND_QUEUE = []

# Separate Flow job state (never interferes with TTS voice jobs)
FLOW_JOB = {
    "state": "idle",  # idle, running, paused, done, failed
    "chrome_connected": False,
    "active_batch": 0,
    "total_batches": 0,
    "done": 0,
    "total": 0,
    "percent": 0,
    "progress_text": "آماده برای ساخت",
    "step_elapsed": 0.0,
    "current_step": "",
    "current_item": "",
    "failed_items": [],
    "self_heal": None,  # dict with diagnostic info when paused by self-heal
    "error": None,
    "started_at": None,
}

_WORKER_THREAD = None


def _mutate_failed_items(output_name: str, add_entry: dict = None):
    """Safely mutate FLOW_JOB['failed_items'] strictly under FLOW_LOCK."""
    with FLOW_LOCK:
        remaining = [x for x in FLOW_JOB["failed_items"] if x.get("output_name") != output_name]
        if add_entry is not None:
            remaining.append(add_entry)
        FLOW_JOB["failed_items"] = remaining


def _worker_sleep(duration: float, root: str):
    """Sleep helper for worker that checks pause state and reloads selectors."""
    t_end = time.time() + duration
    while time.time() < t_end:
        if flow_heal.is_pause_requested():
            flow_heal.request_pause()
            _update_job(state="paused", progress_text="توقف موقت کار")
            flow_heal.wait_if_paused()
            flow_heal.reload_selectors(project_dir=root)
            _update_job(state="running", self_heal=None)
        time.sleep(min(0.2, max(0.01, t_end - time.time())))


def get_flow_status(project_dir: str = None) -> dict:
    """Return live metrics and status of Flow background job."""
    root = project_dir or ROOT
    with FLOW_LOCK:
        st = copy.deepcopy(FLOW_JOB)

    # Check live Chrome port 9222 connection
    st["chrome_connected"] = flow_launch.is_port_open()

    # If idle or not running, enrich failed items from flow-state.json if available
    if st["state"] in ("idle", "done", "failed") and not st["failed_items"]:
        try:
            persisted = flow_state.load_state(project_dir=root)
            failed = []
            for name, it in persisted.get("items", {}).items():
                if it.get("status") in ("failed", "timed_out", "error", "ref_not_found"):
                    failed.append({
                        "output_name": name,
                        "error": it.get("status"),
                        "reason": it.get("status"),
                        "attempt_id": it.get("attempt_id", ""),
                    })
            if failed:
                st["failed_items"] = failed
        except Exception:
            pass

    return st


def _update_job(**kwargs):
    """Safely update in-memory FLOW_JOB state."""
    with FLOW_LOCK:
        FLOW_JOB.update(kwargs)


def _flow_background_worker(mode: str, project_dir: str, only_item: str = None):
    """Background worker for Flow automation with pause/resume and self-heal hooks."""
    import flow_sync

    root = project_dir or ROOT
    t0 = time.time()
    _update_job(
        state="running",
        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        error=None,
        self_heal=None,
    )

    try:
        # Load selectors
        selectors = flow_heal.reload_selectors(project_dir=root)

        # Compute queue
        queue, summary = flow_sync.compute_queue(root, only_name=only_item)
        items_to_gen = [it for it in queue if it.get("action") == "generate"]

        if not items_to_gen:
            _update_job(
                state="done",
                done=summary["total"],
                total=summary["total"],
                percent=100,
                progress_text="تمامی تصاویر از قبل موجود هستند.",
            )
            return

        batch_size = 10
        total_items = len(items_to_gen)
        num_batches = max(1, (total_items + batch_size - 1) // batch_size)

        _update_job(
            total=total_items,
            done=0,
            percent=0,
            total_batches=num_batches,
            active_batch=1,
            progress_text=f"Batch 1/{num_batches} | 0/{total_items} images generated (0%)",
        )

        # Connect to Chrome
        cdp_url = flow_sync.DEFAULT_CDP_URL
        pw, browser = flow_sync.connect_cdp(cdp_url)
        if not browser:
            _update_job(
                state="failed",
                error="امکان اتصال به کروم در پورت ۹۲۲۲ فراهم نشد. لطفاً کروم را با دکمهٔ باز کردن کروم اجرا کنید.",
            )
            return

        try:
            page = flow_sync.find_flow_tab(browser, selectors)
            if not page:
                _update_job(
                    state="failed",
                    error="زبانهٔ فعال پروژه Flow در مرورگر پیدا نشد. لطفاً به صفحهٔ پروژه وارد شوید.",
                )
                return

            # Verify selectors loop (Requirement 1)
            while True:
                all_ok, sel_results = flow_sync.verify_selectors(page, selectors)
                if all_ok:
                    break
                missing_key = next((k for k, v in sel_results.items() if not v.get("found")), "prompt_box")
                failing_sel = selectors.get(missing_key, "")
                first_item = items_to_gen[0]["output_name"] if items_to_gen else ""
                att_id = items_to_gen[0].get("attempt_id", "") if items_to_gen else ""

                diag_dir, _ = flow_heal.dump_diagnostic_bundle(
                    page=page,
                    step_name="verify_selectors",
                    selector_key=missing_key,
                    attempted_selector=failing_sel,
                    output_name=first_item,
                    attempt_id=att_id,
                    project_dir=root,
                )

                flow_heal.request_pause()
                _update_job(
                    state="paused",
                    self_heal={
                        "paused": True,
                        "timestamp": os.path.basename(diag_dir),
                        "diagnostic_dir": os.path.relpath(diag_dir, root).replace("\\", "/"),
                        "step": "verify_selectors",
                        "selector_key": missing_key,
                        "attempted_selector": failing_sel,
                    },
                    progress_text=f"متوقف در خودترمیمی: انتخابگر {missing_key} پیدا نشد.",
                )

                # Wait for resume
                flow_heal.wait_if_paused()
                selectors = flow_heal.reload_selectors(project_dir=root)
                _update_job(state="running", self_heal=None)

            # Persist per-item initial state to .kit/flow-state.json (Requirement 2)
            state = flow_state.load_state(project_dir=root)
            for it in items_to_gen:
                if it["output_name"] not in state.get("items", {}):
                    flow_state.record_item_state(
                        state,
                        output_name=it["output_name"],
                        prompt_hash=it.get("prompt_hash", ""),
                        status="pending",
                        attempt_id=it.get("attempt_id", ""),
                        refs=it.get("refs", []),
                    )
            flow_state.save_state(state, project_dir=root)

            # Process batches / download
            generated_count = 0

            if mode == "download":
                import flow_recover
                _update_job(progress_text=f"در حال دانلود و پردازش {total_items} تصویر...")
                flow_recover.run_download_phase(
                    page=page,
                    queue=items_to_gen,
                    selectors=selectors,
                    project_dir=root,
                    batch_size=batch_size,
                    sleeper=lambda s: _worker_sleep(s, root),
                    state=state,
                )
            else:
                import flow_submit
                batches = flow_submit.plan_batches(items_to_gen, batch_size=batch_size)

                for b_idx, batch in enumerate(batches, start=1):
                    # Pause check at start of batch
                    if flow_heal.is_pause_requested():
                        flow_heal.request_pause()
                        _update_job(state="paused", progress_text=f"متوقف‌شده در بستهٔ {b_idx}/{num_batches}")
                        flow_heal.wait_if_paused()
                        selectors = flow_heal.reload_selectors(project_dir=root)
                        _update_job(state="running", self_heal=None)

                    _update_job(
                        active_batch=b_idx,
                        current_step=f"batch_{b_idx}",
                    )

                    for it in batch:
                        # Pause check before each item
                        if flow_heal.is_pause_requested():
                            flow_heal.request_pause()
                            _update_job(state="paused", current_item=it["output_name"], progress_text="توقف موقت کار")
                            flow_heal.wait_if_paused()
                            selectors = flow_heal.reload_selectors(project_dir=root)
                            _update_job(state="running", self_heal=None)

                        _update_job(current_item=it["output_name"], step_elapsed=round(time.time() - t0, 1))

                        while True:
                            outcome = flow_submit.submit_single_prompt(page, it, selectors)
                            if outcome == "error":
                                diag_dir, _ = flow_heal.dump_diagnostic_bundle(
                                    page=page,
                                    step_name="submit_single_prompt",
                                    selector_key="prompt_box",
                                    attempted_selector=selectors.get("prompt_box", ""),
                                    output_name=it["output_name"],
                                    attempt_id=it.get("attempt_id", ""),
                                    project_dir=root,
                                )
                                flow_heal.request_pause()
                                _update_job(
                                    state="paused",
                                    self_heal={
                                        "paused": True,
                                        "timestamp": os.path.basename(diag_dir),
                                        "diagnostic_dir": os.path.relpath(diag_dir, root).replace("\\", "/"),
                                        "step": "submit_single_prompt",
                                        "selector_key": "prompt_box",
                                        "attempted_selector": selectors.get("prompt_box", ""),
                                    },
                                    progress_text="متوقف در خودترمیمی: خطا در ارسال پرامپت.",
                                )
                                flow_heal.wait_if_paused()
                                selectors = flow_heal.reload_selectors(project_dir=root)
                                _update_job(state="running", self_heal=None)
                                continue
                            break

                        if outcome == "submitted":
                            generated_count += 1
                            pct = int(generated_count * 100 / total_items)
                            _update_job(
                                done=generated_count,
                                percent=pct,
                                progress_text=f"Batch {b_idx}/{num_batches} | {generated_count}/{total_items} images generated ({pct}%)",
                            )
                            flow_state.record_item_state(
                                state,
                                output_name=it["output_name"],
                                prompt_hash=it.get("prompt_hash", ""),
                                status="submitted",
                                attempt_id=it.get("attempt_id", ""),
                                refs=it.get("refs", []),
                            )
                        else:
                            _mutate_failed_items(it["output_name"], add_entry={
                                "output_name": it["output_name"],
                                "error": outcome,
                                "reason": f"شکست در ارسال: {outcome}",
                                "attempt_id": it.get("attempt_id", ""),
                            })
                            flow_state.record_item_state(
                                state,
                                output_name=it["output_name"],
                                prompt_hash=it.get("prompt_hash", ""),
                                status=outcome,
                                attempt_id=it.get("attempt_id", ""),
                                refs=it.get("refs", []),
                            )
                        flow_state.save_state(state, project_dir=root)

            # Process explicit resend queue items (Requirement 4)
            while True:
                with FLOW_LOCK:
                    if not RESEND_QUEUE:
                        break
                    resend_name = RESEND_QUEUE.pop(0)

                r_queue, _ = flow_sync.compute_queue(root, only_name=resend_name)
                r_gen = [x for x in r_queue if x.get("action") == "generate"]
                if r_gen:
                    r_it = r_gen[0]
                    if mode == "download":
                        import flow_recover
                        flow_recover.run_download_phase(
                            page=page,
                            queue=r_gen,
                            selectors=selectors,
                            project_dir=root,
                            batch_size=1,
                            sleeper=lambda s: _worker_sleep(s, root),
                            state=state,
                        )
                    else:
                        import flow_submit
                        r_outcome = flow_submit.submit_single_prompt(page, r_it, selectors)
                        if r_outcome == "submitted":
                            generated_count += 1
                            flow_state.record_item_state(
                                state,
                                output_name=r_it["output_name"],
                                prompt_hash=r_it.get("prompt_hash", ""),
                                status="submitted",
                                attempt_id=r_it.get("attempt_id", ""),
                                refs=r_it.get("refs", []),
                            )
                        else:
                            _mutate_failed_items(r_it["output_name"], add_entry={
                                "output_name": r_it["output_name"],
                                "error": r_outcome,
                                "reason": f"شکست در ارسال مجدد: {r_outcome}",
                                "attempt_id": r_it.get("attempt_id", ""),
                            })
                            flow_state.record_item_state(
                                state,
                                output_name=r_it["output_name"],
                                prompt_hash=r_it.get("prompt_hash", ""),
                                status=r_outcome,
                                attempt_id=r_it.get("attempt_id", ""),
                                refs=r_it.get("refs", []),
                            )
                        flow_state.save_state(state, project_dir=root)

            # Update final state from flow-state.json
            persisted = flow_state.load_state(project_dir=root)
            persisted_items = persisted.get("items", {})
            done_cnt = sum(1 for it in persisted_items.values() if it.get("status") in ("done", "submitted"))
            failed_from_st = []
            for nm, it in persisted_items.items():
                if it.get("status") in ("failed", "timed_out", "error", "ref_not_found"):
                    failed_from_st.append({
                        "output_name": nm,
                        "error": it.get("status"),
                        "reason": it.get("status"),
                        "attempt_id": it.get("attempt_id", ""),
                    })
            if failed_from_st:
                with FLOW_LOCK:
                    FLOW_JOB["failed_items"] = failed_from_st

            _update_job(
                state="done",
                done=done_cnt,
                percent=100,
                progress_text=f"پایان: {done_cnt} از {total_items} تصویر انجام شد.",
            )

        finally:
            flow_sync._cleanup_browser(pw, browser)

    except Exception as e:
        _update_job(
            state="failed",
            error=str(e),
            progress_text=f"خطا در اجرا: {e}",
        )


def start_flow_job(payload: dict = None, project_dir: str = None) -> dict:
    """Start Flow generation in background."""
    global _WORKER_THREAD
    root = project_dir or ROOT
    mode = (payload or {}).get("mode", "download")
    only = (payload or {}).get("only") or (payload or {}).get("output_name")

    with FLOW_LOCK:
        if FLOW_JOB["state"] in ("running", "paused"):
            raise ValueError("یک فرآیند ساخت Flow در حال حاضر در حال اجرا یا متوقف است.")
        if not only:
            FLOW_JOB["failed_items"] = []
            RESEND_QUEUE.clear()
        FLOW_JOB["state"] = "running"

    flow_heal.request_resume()
    _WORKER_THREAD = threading.Thread(
        target=_flow_background_worker,
        args=(mode, root, only),
        daemon=True,
    )
    _WORKER_THREAD.start()

    return {"ok": True, "state": "running", "mode": mode}


def pause_flow_job() -> dict:
    """Request active job pause."""
    flow_heal.request_pause()
    _update_job(state="paused")
    return {"ok": True, "state": "paused"}


def resume_flow_job(project_dir: str = None) -> dict:
    """Resume paused job and reload selectors."""
    with FLOW_LOCK:
        if FLOW_JOB["state"] != "paused":
            raise ValueError("تنها کارهای متوقف‌شده قابل ادامه دادن هستند.")

    root = project_dir or ROOT
    flow_heal.reload_selectors(project_dir=root)
    flow_heal.request_resume()
    _update_job(state="running", self_heal=None)
    return {"ok": True, "state": "running"}


def resend_flow_item(payload: dict, project_dir: str = None) -> dict:
    """Re-dispatch a specific failed item without restarting entire queue."""
    name = (payload or {}).get("output_name") or (payload or {}).get("item")
    if not name:
        raise ValueError("نام تصویر (output_name) مشخص نشده است.")

    root = project_dir or ROOT

    # Mutate FLOW_JOB["failed_items"] strictly under FLOW_LOCK
    with FLOW_LOCK:
        FLOW_JOB["failed_items"] = [x for x in FLOW_JOB["failed_items"] if x.get("output_name") != name]
        is_idle = FLOW_JOB["state"] in ("idle", "done", "failed")
        if not is_idle:
            if name not in RESEND_QUEUE:
                RESEND_QUEUE.append(name)

    # Re-queue / reset status in flow-state.json
    try:
        st = flow_state.load_state(project_dir=root)
        if name in st.get("items", {}):
            st["items"][name]["status"] = "pending"
            flow_state.save_state(st, project_dir=root)
    except Exception:
        pass

    # If job is idle or failed, start a single-item run
    if is_idle:
        return start_flow_job({"output_name": name, "mode": "download"}, project_dir=root)

    return {"ok": True, "output_name": name, "status": "queued"}


def handle_get(path: str, project_dir: str = None) -> dict:
    """Route GET /api/flow/* requests."""
    p = path.split("?")[0]
    if p in ("/api/flow/status", "/api/flow/job"):
        return get_flow_status(project_dir=project_dir)
    return {"error": "not found"}


def handle_post(path: str, payload: dict, project_dir: str = None) -> dict:
    """Route POST /api/flow/* requests."""
    p = path.split("?")[0]
    root = project_dir or ROOT
    if p == "/api/flow/launch-chrome":
        return flow_launch.launch_chrome(project_dir=root)
    if p == "/api/flow/start":
        return start_flow_job(payload, project_dir=root)
    if p == "/api/flow/pause":
        return pause_flow_job()
    if p == "/api/flow/resume":
        return resume_flow_job(project_dir=root)
    if p == "/api/flow/resend":
        return resend_flow_item(payload, project_dir=root)
    raise ValueError(f"Unknown endpoint: {path}")
