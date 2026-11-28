# -*- coding: utf-8 -*-
"""Process resubmit queue and execute download phase for Flow automation.

Part of Phase C Google Flow automation. Extracted from flow_retry to keep
file sizes below the 600-line hard cap. Handles end-of-run resubmit queue
processing and full Phase C download phase orchestration.
"""
import datetime
import sys
import time

import flow_download
import flow_state
import flow_submit
from flow_retry import (
    DEFAULT_COOLDOWN_SECONDS,
    MAX_RESUBMIT_ATTEMPTS,
    CooldownTracker,
    ResubmitQueue,
    is_error_banner_present,
    refresh_and_recheck_batch,
    trigger_download_from_page,
)


def process_resubmit_queue(page, resubmit_queue: ResubmitQueue, selectors: dict,
                           project_dir: str = ".", state: dict = None,
                           max_retries: int = MAX_RESUBMIT_ATTEMPTS,
                           unmatched_dir: str = None,
                           cooldown_tracker=None, sleeper=None, clock=None) -> list:
    """Execute end-of-run resubmit queue with strict cap (max 2 resubmits per item).

    Guarantees:
    - An item gets AT MOST max_retries (2) resubmits in total.
    - Tracked by retries_count field in state.
    - Initialised on first queue entry and honoured when resumed from state.
    - Over-cap items are marked 'failed' in state without further submissions.
    """
    sleep_fn = sleeper or time.sleep
    now_fn = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))
    resolved_state = state if state is not None else getattr(resubmit_queue, "state", None)

    sys.stdout.write(f"\n============================================================\n")
    sys.stdout.write(f"Executing End-of-Run Resubmit Queue ({len(resubmit_queue.queue)} item(s))\n")
    sys.stdout.write(f"============================================================\n")

    processed = []

    while not resubmit_queue.is_empty():
        import flow_heal
        if flow_heal.is_pause_requested():
            flow_heal.wait_if_paused()
            selectors = flow_heal.reload_selectors(project_dir=project_dir)
        retry_item = resubmit_queue.queue.pop(0)
        rname = retry_item["output_name"]

        # Honour retries_count from state if available
        current_retries = retry_item.get("retries_count", 0)
        if resolved_state and "items" in resolved_state and rname in resolved_state["items"]:
            st_retries = resolved_state["items"][rname].get("retries_count")
            if st_retries is not None:
                current_retries = max(current_retries, st_retries)
        retry_item["retries_count"] = current_retries

        if current_retries >= max_retries:
            sys.stdout.write(f"Item '{rname}' reached max retries ({max_retries}). Marking 'failed'.\n")
            if cooldown_tracker and hasattr(cooldown_tracker, "_resolve_iso"):
                now_iso = cooldown_tracker._resolve_iso()
            else:
                raw_now = now_fn() if callable(now_fn) else now_fn
                now_iso = raw_now.isoformat() if hasattr(raw_now, "isoformat") else str(raw_now)

            if resolved_state is not None:
                flow_state.record_item_state(
                    resolved_state,
                    output_name=rname,
                    prompt_hash=retry_item.get("prompt_hash", ""),
                    status="failed",
                    attempt_id=retry_item.get("attempt_id"),
                    refs=retry_item.get("refs", []),
                    now_iso=now_iso,
                    retries_count=current_retries,
                )
                if project_dir:
                    flow_state.save_state(resolved_state, project_dir=project_dir)
            processed.append({"output_name": rname, "status": "failed", "retries_count": current_retries})
            continue

        # Item receives a resubmission attempt
        new_retries = current_retries + 1
        retry_item["retries_count"] = new_retries
        new_att_id = flow_state.generate_attempt_id()
        retry_item["attempt_id"] = new_att_id

        if resolved_state is not None:
            if cooldown_tracker and hasattr(cooldown_tracker, "_resolve_iso"):
                now_iso = cooldown_tracker._resolve_iso()
            else:
                raw_now = now_fn() if callable(now_fn) else now_fn
                now_iso = raw_now.isoformat() if hasattr(raw_now, "isoformat") else str(raw_now)
            flow_state.record_item_state(
                resolved_state,
                output_name=rname,
                prompt_hash=retry_item.get("prompt_hash", ""),
                status="pending",
                attempt_id=new_att_id,
                refs=retry_item.get("refs", []),
                now_iso=now_iso,
                retries_count=new_retries,
            )
            if project_dir:
                flow_state.save_state(resolved_state, project_dir=project_dir)

        sys.stdout.write(f"Resubmitting '{rname}' (Attempt {new_retries}/{max_retries}, {new_att_id})...\n")
        outcome = flow_submit.submit_single_prompt(page, retry_item, selectors, sleeper=sleep_fn)
        has_error = is_error_banner_present(page, selectors)

        if outcome == "submitted" and not has_error:
            def trigger_fn():
                trigger_download_from_page(page, selectors)

            res = flow_download.intercept_and_save_download(
                page=page,
                download_trigger_fn=trigger_fn,
                expected_item=retry_item,
                project_dir=project_dir,
                unmatched_dir=unmatched_dir,
                candidate_attempt_id=new_att_id,
                clock=now_fn,
            )

            if res.get("status") == "saved":
                if cooldown_tracker:
                    cooldown_tracker.record_success()
                rel_p = res.get("rel_path")
                if cooldown_tracker and hasattr(cooldown_tracker, "_resolve_iso"):
                    now_iso = cooldown_tracker._resolve_iso()
                else:
                    raw_now = now_fn() if callable(now_fn) else now_fn
                    now_iso = raw_now.isoformat() if hasattr(raw_now, "isoformat") else str(raw_now)
                sys.stdout.write(f"  -> Resubmission succeeded! Saved: {rel_p}\n")
                if resolved_state is not None:
                    flow_state.record_item_state(
                        resolved_state,
                        output_name=rname,
                        prompt_hash=retry_item.get("prompt_hash", ""),
                        status="done",
                        attempt_id=new_att_id,
                        refs=retry_item.get("refs", []),
                        now_iso=now_iso,
                        retries_count=new_retries,
                        saved_path=rel_p,
                        completed_at=now_iso,
                    )
                    if project_dir:
                        flow_state.save_state(resolved_state, project_dir=project_dir)
                processed.append({"output_name": rname, "status": "done", "retries_count": new_retries})
            else:
                if cooldown_tracker:
                    cooldown_tracker.record_failure(state=resolved_state, project_dir=project_dir)
                resubmit_queue.add_failure(retry_item, current_retries=new_retries, state=resolved_state)
        else:
            if cooldown_tracker:
                cooldown_tracker.record_failure(state=resolved_state, project_dir=project_dir)
            resubmit_queue.add_failure(retry_item, current_retries=new_retries, state=resolved_state)

        if resolved_state is not None and project_dir:
            flow_state.save_state(resolved_state, project_dir=project_dir)

    return processed


def run_download_phase(page, queue: list, selectors: dict, project_dir: str,
                       batch_size: int = 10, max_retries: int = MAX_RESUBMIT_ATTEMPTS,
                       unmatched_dir: str = None, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
                       sleeper=None, clock=None, rng=None, state: dict = None) -> int:
    """Execute complete Phase C download and retry runner.

    Steps:
    1. Batch submissions with reference handling
    2. Intercept download stream directly via page.expect_download()
    3. Route uncertain downloads to images/_unmatched/ with manifest.json
    4. Handle suspicious errors by end-of-batch tab refresh & recheck
    5. Consecutive 3 failures trigger cooldown (>= 300s) with advisory
    6. Confirmed failures entered into end-of-run resubmit queue (max 2 retries)
    7. Over-cap retries marked 'failed' in state
    """
    sleep_fn = sleeper or time.sleep
    now_fn = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))

    items_to_process = [item for item in queue if item.get("action") == "generate"]
    if not items_to_process:
        sys.stdout.write("No items queued for generation (all skipped or queue empty).\n")
        return 0

    if state is None:
        state = flow_state.load_state(project_dir=project_dir)

    cooldown_tracker = CooldownTracker(
        failure_threshold=3,
        cooldown_seconds=cooldown_seconds,
        sleeper=sleep_fn,
        clock=now_fn,
    )
    resubmit_queue = ResubmitQueue(max_retries=max_retries, state=state)

    batches = flow_submit.plan_batches(items_to_process, batch_size=batch_size)
    total_batches = len(batches)

    sys.stdout.write(f"Executing Phase C download run: {len(items_to_process)} items in {total_batches} batch(es).\n")

    for batch_idx, batch in enumerate(batches, start=1):
        sys.stdout.write(f"\n=== Batch {batch_idx}/{total_batches} ({len(batch)} items) ===\n")
        suspicious_in_batch = []

        for item_idx, item in enumerate(batch, start=1):
            import flow_heal
            if flow_heal.is_pause_requested():
                flow_heal.wait_if_paused()
                selectors = flow_heal.reload_selectors(project_dir=project_dir)

            name = item["output_name"]
            att_id = item.get("attempt_id") or flow_state.generate_attempt_id()
            item["attempt_id"] = att_id
            item["tile_order"] = item_idx
            # Check if resumed from state
            if state and "items" in state and name in state["items"]:
                st_count = state["items"][name].get("retries_count")
                if st_count is not None and "retries_count" not in item:
                    item["retries_count"] = st_count

            sys.stdout.write(f"Batch {batch_idx}/{total_batches}: Item {item_idx}/{len(batch)} ({name}) submitting...\n")

            outcome = flow_submit.submit_single_prompt(page, item, selectors, sleeper=sleep_fn)
            has_error = is_error_banner_present(page, selectors)

            if outcome == "error":
                diag_dir, _ = flow_heal.dump_diagnostic_bundle(
                    page=page,
                    step_name="submit_single_prompt",
                    selector_key="prompt_box",
                    attempted_selector=selectors.get("prompt_box", ""),
                    output_name=name,
                    attempt_id=att_id,
                    project_dir=project_dir,
                )
                flow_heal.request_pause()
                flow_heal.wait_if_paused()
                selectors = flow_heal.reload_selectors(project_dir=project_dir)

            if outcome == "submitted" and not has_error:
                # Tile completed without error banner -> intercept download
                sys.stdout.write(f"  Tile ready for {name}. Intercepting download...\n")

                def trigger_fn():
                    trigger_download_from_page(page, selectors)

                res = flow_download.intercept_and_save_download(
                    page=page,
                    download_trigger_fn=trigger_fn,
                    expected_item=item,
                    project_dir=project_dir,
                    unmatched_dir=unmatched_dir,
                    candidate_attempt_id=att_id,
                    clock=now_fn,
                )

                if res.get("status") == "saved":
                    cooldown_tracker.record_success()
                    rel_p = res.get("rel_path")
                    alt_mark = " (saved as duplicate _alt)" if res.get("is_alt") else ""
                    sys.stdout.write(f"  -> Saved download: {rel_p}{alt_mark}\n")

                    now_iso = cooldown_tracker._resolve_iso()
                    flow_state.record_item_state(
                        state,
                        output_name=name,
                        prompt_hash=item.get("prompt_hash", ""),
                        status="done",
                        attempt_id=att_id,
                        refs=item.get("refs", []),
                        batch_id=batch_idx,
                        submitted_at=now_iso,
                        now_iso=now_iso,
                        retries_count=item.get("retries_count", 0),
                        saved_path=rel_p,
                        completed_at=now_iso,
                    )
                    flow_state.increment_daily_counter(state, count=1, now_iso=now_iso)
                elif res.get("status") == "unmatched":
                    sys.stdout.write(f"  -> Unmatched download isolated: {res.get('rel_path')}\n")
                    # Unmatched file quarantined; item counts as suspicious
                    suspicious_in_batch.append(item)
                else:
                    # Download trigger error
                    suspicious_in_batch.append(item)
            else:
                # Suspicious failure during generation
                sys.stdout.write(f"  -> Generation flagged suspicious failure ({outcome}, error_banner={has_error})\n")
                suspicious_in_batch.append(item)

            flow_state.save_state(state, project_dir=project_dir)

            # Natural jitter between consecutive items
            if item_idx < len(batch):
                jitter_s = flow_submit.calculate_jitter(rng)
                sleep_fn(jitter_s)

        # End of batch: handle suspicious failures via page refresh & recheck
        if suspicious_in_batch:
            recovered, confirmed = refresh_and_recheck_batch(
                page=page,
                selectors=selectors,
                suspicious_items=suspicious_in_batch,
                sleeper=sleep_fn,
            )

            # Process recovered items
            for rec_item in recovered:
                rname = rec_item["output_name"]
                att_id = rec_item["attempt_id"]

                def trigger_fn():
                    trigger_download_from_page(page, selectors)

                res = flow_download.intercept_and_save_download(
                    page=page,
                    download_trigger_fn=trigger_fn,
                    expected_item=rec_item,
                    project_dir=project_dir,
                    unmatched_dir=unmatched_dir,
                    candidate_attempt_id=att_id,
                    clock=now_fn,
                )

                if res.get("status") == "saved":
                    cooldown_tracker.record_success()
                    rel_p = res.get("rel_path")
                    now_iso = cooldown_tracker._resolve_iso()
                    flow_state.record_item_state(
                        state,
                        output_name=rname,
                        prompt_hash=rec_item.get("prompt_hash", ""),
                        status="done",
                        attempt_id=att_id,
                        refs=rec_item.get("refs", []),
                        batch_id=batch_idx,
                        now_iso=now_iso,
                        retries_count=rec_item.get("retries_count", 0),
                        saved_path=rel_p,
                        completed_at=now_iso,
                    )
                else:
                    confirmed.append(rec_item)

            # Process confirmed failures -> route to resubmit queue and check cooldown
            for conf_item in confirmed:
                resubmit_queue.add_failure(conf_item, state=state)
                cooldown_tracker.record_failure(state=state, project_dir=project_dir)

        # Inter-batch pause
        if batch_idx < total_batches:
            pause_s = flow_submit.calculate_inter_batch_pause(rng)
            sleep_fn(pause_s)

    # End of run: process resubmit queue
    if not resubmit_queue.is_empty():
        process_resubmit_queue(
            page=page,
            resubmit_queue=resubmit_queue,
            selectors=selectors,
            project_dir=project_dir,
            state=state,
            max_retries=max_retries,
            unmatched_dir=unmatched_dir,
            cooldown_tracker=cooldown_tracker,
            sleeper=sleep_fn,
            clock=now_fn,
        )

    sys.stdout.write("\nPhase C download run completed.\n")
    return 0
