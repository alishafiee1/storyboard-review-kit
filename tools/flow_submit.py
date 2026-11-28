# -*- coding: utf-8 -*-
"""Prompt segmentation, reference attachment, batching, jitter, and submit logic for Flow automation (Phase B).

Provides pure planning functions (batching, jitter, daily cap), prompt segmentation
into text chunks and reference name attachments, and Playwright-driving submission
routines using duck-typed page objects.
"""
import datetime
import random
import re
import sys
import time

import flow_state


def clean_ref_name(name: str) -> str:
    """Normalize a reference name from prompts.txt or story.txt.

    Strips file extensions (.jpg, .png, etc.), hex suffix tails (_12345678),
    and bracket/at prefixes ([REF], @REF).
    """
    if not name:
        return ""
    s = str(name).strip()
    # Strip brackets or @ prefix
    s = s.strip("[]@ \t\r\n")
    # Remove file extension if present
    s = re.sub(r"\.(jpg|jpeg|png|webp)$", "", s, flags=re.I)
    # Remove 8-char hex hash tail (e.g. _4eb46d68 or _11112222)
    s = re.sub(r"_[0-9a-fA-F]{8}$", "", s)
    return s.strip()


def extract_prompt_body(text: str) -> str:
    """Extract English prompt body without kit directives ([REFS TO ATTACH:...], [OUTPUT NAME:...])."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\[REFS TO ATTACH:[^\]]*\]$", stripped, re.I):
            continue
        if re.match(r"^\[OUTPUT NAME:[^\]]*\]$", stripped, re.I):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def segment_prompt(raw_prompt: str, refs: list = None) -> list:
    """Segment a prompt into sequential text chunks and reference attachment points.

    Returns a list of dicts:
      {"type": "text", "value": str}
      {"type": "ref", "value": str}

    References in `refs` that do not appear in the prompt body text are attached
    at the start. References appearing inline (or bracketed/at-prefixed) split the
    prompt body so that the runner can type text, attach the reference by name,
    and continue typing.
    """
    body = extract_prompt_body(raw_prompt)
    if not body and not refs:
        return []

    # Clean and deduplicate given refs
    given_refs = []
    for r in (refs or []):
        cleaned = clean_ref_name(r)
        if cleaned and cleaned not in given_refs:
            given_refs.append(cleaned)

    all_target_refs = list(given_refs)

    # Detect any inline bracketed or @ tokens in the body (e.g. [CH_NIBBLES] or @CH_NIBBLES)
    inline_candidates = re.findall(r"(?:\[([A-Za-z0-9_\-]+)\]|@([A-Za-z0-9_\-]+))", body)
    for c1, c2 in inline_candidates:
        candidate = clean_ref_name(c1 or c2)
        if candidate and candidate not in all_target_refs:
            # Check if candidate matches standard ref conventions (CH_, LOC_, STYLE_, PROP_, etc.)
            if "_" in candidate or candidate.isupper():
                all_target_refs.append(candidate)

    if not all_target_refs:
        return [{"type": "text", "value": body}] if body else []

    # Sort target refs by length descending to prevent sub-string prefix collisions
    sorted_targets = sorted(all_target_refs, key=len, reverse=True)

    # Build regex to match any of the refs in body: [REF], @REF, or \bREF\b
    patterns = []
    for r in sorted_targets:
        escaped = re.escape(r)
        patterns.append(rf"\[{escaped}\]")
        patterns.append(rf"@{escaped}\b")
        patterns.append(rf"\b{escaped}\b")

    combined_re = re.compile("(" + "|".join(patterns) + ")")

    # Split body into text parts and ref matches
    tokens = combined_re.split(body)
    body_segments = []
    matched_refs_in_body = set()

    for token in tokens:
        if not token:
            continue
        cleaned = clean_ref_name(token)
        if cleaned in all_target_refs:
            body_segments.append({"type": "ref", "value": cleaned})
            matched_refs_in_body.add(cleaned)
        else:
            if body_segments and body_segments[-1]["type"] == "text":
                body_segments[-1]["value"] += token
            else:
                body_segments.append({"type": "text", "value": token})

    # Any ref from given_refs not found in body is attached at the beginning
    prefix_segments = []
    for r in given_refs:
        if r not in matched_refs_in_body:
            prefix_segments.append({"type": "ref", "value": r})

    return prefix_segments + body_segments


def plan_batches(queue_items: list, batch_size: int = 10) -> list:
    """Split queue items into batches of `batch_size` (default: 10)."""
    if batch_size <= 0:
        batch_size = 10
    return [queue_items[i:i + batch_size] for i in range(0, len(queue_items), batch_size)]


def calculate_jitter(rng=None, min_s: float = 3.0, max_s: float = 8.0) -> float:
    """Calculate random jitter in seconds between submissions within a batch (3.0–8.0s)."""
    if rng is not None:
        if hasattr(rng, "uniform"):
            return float(rng.uniform(min_s, max_s))
        if callable(rng):
            return float(rng())
    return random.uniform(min_s, max_s)


def calculate_inter_batch_pause(rng=None, min_s: float = 30.0, max_s: float = 90.0) -> float:
    """Calculate random pause in seconds between batches (30.0–90.0s)."""
    if rng is not None:
        if hasattr(rng, "uniform"):
            return float(rng.uniform(min_s, max_s))
        if callable(rng):
            return float(rng())
    return random.uniform(min_s, max_s)


def is_daily_cap_reached(state: dict, daily_cap: int = 100, now: datetime.datetime = None) -> bool:
    """Check if the daily submission cap has been reached within the rolling 24-hour window."""
    if daily_cap is None or daily_cap <= 0:
        return False
    count = flow_state.get_daily_submitted_count(state, now=now)
    return count >= daily_cap


def attach_reference_by_name(page, ref_name: str, selectors: dict,
                             search_timeout_s: float = 5.0) -> bool:
    """Search and attach a reference by name in the Flow ingredients menu.

    1. Clicks ingredients_button
    2. Inputs ref_name into ingredient_search_input
    3. Verifies that search returned matching item; if missing, cancels and returns False
    4. Presses Enter (or confirms) to attach
    5. Returns True

    The native OS file chooser is NEVER triggered.
    """
    btn_sel = selectors.get("ingredients_button", "button[aria-label=\"Add ingredients to the prompt box\"]")
    search_sel = selectors.get("ingredient_search_input", "input[placeholder*=\"Search\"], input[aria-label*=\"Search\"]")
    result_sel = selectors.get("ingredient_result_item", "div[role=\"option\"], div[role=\"listbox\"] div[role=\"button\"]")

    # Step 1: Open ingredients menu
    try:
        if hasattr(page, "click"):
            page.click(btn_sel)
        else:
            el = page.query_selector(btn_sel)
            if el:
                el.click()
            else:
                return False
    except Exception as e:
        sys.stderr.write(f"Warning: Failed clicking ingredients button ({btn_sel}): {e}\n")
        return False

    # Step 2: Locate search input and type reference name
    try:
        if hasattr(page, "wait_for_selector"):
            page.wait_for_selector(search_sel, timeout=int(search_timeout_s * 1000))
        if hasattr(page, "fill"):
            page.fill(search_sel, ref_name)
        elif hasattr(page, "type"):
            page.type(search_sel, ref_name)
        else:
            inp = page.query_selector(search_sel)
            if inp:
                if hasattr(inp, "fill"):
                    inp.fill(ref_name)
                elif hasattr(inp, "type"):
                    inp.type(ref_name)
            else:
                sys.stderr.write(f"Warning: Ingredient search input not found ({search_sel})\n")
                return False
    except Exception as e:
        sys.stderr.write(f"Warning: Failed entering search for '{ref_name}': {e}\n")
        return False

    # Step 3: Verify matching result item exists
    try:
        if hasattr(page, "query_selector"):
            result_item = page.query_selector(result_sel)
            if result_item is None:
                sys.stderr.write(f"Warning: Reference '{ref_name}' not found in ingredients search results.\n")
                # Close dialog gracefully
                if hasattr(page, "keyboard") and page.keyboard:
                    page.keyboard.press("Escape")
                return False
    except Exception:
        # If query fails, attempt Enter anyway or handle gracefully
        pass

    # Step 4: Press Enter to attach
    try:
        if hasattr(page, "keyboard") and page.keyboard:
            page.keyboard.press("Enter")
        elif hasattr(page, "press"):
            page.press(search_sel, "Enter")
    except Exception as e:
        sys.stderr.write(f"Warning: Failed pressing Enter to attach reference '{ref_name}': {e}\n")
        return False

    return True


def wait_for_generation_tile(page, selectors: dict, timeout_s: float = 120.0,
                             poll_interval_s: float = 0.5, sleeper=None) -> bool:
    """Event-based wait for generation completion tile without fixed sleep timers.

    Uses page.wait_for_selector if available; otherwise falls back to event polling.
    Returns True if generation completed within timeout_s, False if timed out.
    """
    tile_sel = selectors.get("result_tile", "div[data-testid=\"generation-tile\"]")

    if hasattr(page, "wait_for_selector"):
        try:
            res = page.wait_for_selector(tile_sel, timeout=int(timeout_s * 1000))
            return res is not None
        except Exception:
            return False

    # Polling branch only exists for duck-typed fakes and Playwright pages use wait_for_selector.
    sleep_fn = sleeper or time.sleep
    t0 = time.time()
    while (time.time() - t0) < timeout_s:
        try:
            el = page.query_selector(tile_sel)
            if el is not None:
                return True
        except Exception:
            pass
        sleep_fn(poll_interval_s)

    return False


def submit_single_prompt(page, item: dict, selectors: dict, timeout_s: float = 120.0,
                         sleeper=None) -> str:
    """Submit a single prompt to Flow: type segments, attach refs, click submit, and wait for event.

    Returns one of:
      "submitted"     - prompt submitted and generation tile detected
      "ref_not_found" - an ingredient was missing from search; broken prompt not submitted
      "timed_out"     - submitted, but generation tile wait timed out (> 120s)
      "error"         - unexpected error during submission
    """
    raw_prompt = item.get("raw_prompt", "")
    refs = item.get("refs", [])
    segments = segment_prompt(raw_prompt, refs)

    prompt_box_sel = selectors.get("prompt_box", "div[role=\"textbox\"][aria-label=\"What do you want to create?\"]")
    submit_btn_sel = selectors.get("submit_button", "button[aria-label=\"Start generation\"]")

    # Focus prompt box
    try:
        if hasattr(page, "click"):
            page.click(prompt_box_sel)
        else:
            box = page.query_selector(prompt_box_sel)
            if box:
                box.click()
    except Exception as e:
        sys.stderr.write(f"Error focusing prompt box ({prompt_box_sel}): {e}\n")
        return "error"

    # Type segments and attach references in sequence
    for seg in segments:
        seg_type = seg.get("type")
        seg_val = seg.get("value", "")

        if seg_type == "text":
            if not seg_val:
                continue
            try:
                if hasattr(page, "keyboard") and page.keyboard:
                    page.keyboard.type(seg_val)
                elif hasattr(page, "type"):
                    page.type(prompt_box_sel, seg_val)
                else:
                    box = page.query_selector(prompt_box_sel)
                    if box and hasattr(box, "type"):
                        box.type(seg_val)
            except Exception as e:
                sys.stderr.write(f"Error typing text segment into prompt box: {e}\n")
                return "error"

        elif seg_type == "ref":
            ok = attach_reference_by_name(page, seg_val, selectors)
            if not ok:
                # Rule Edge Case: Ingredient search returned no results; do not submit broken prompt
                return "ref_not_found"

    # Click submit button
    try:
        if hasattr(page, "click"):
            page.click(submit_btn_sel)
        else:
            sub_btn = page.query_selector(submit_btn_sel)
            if sub_btn:
                sub_btn.click()
            else:
                sys.stderr.write(f"Error: Submit button not found ({submit_btn_sel})\n")
                return "error"
    except Exception as e:
        sys.stderr.write(f"Error clicking submit button ({submit_btn_sel}): {e}\n")
        return "error"

    # Event-based wait for generation tile completion
    tile_ok = wait_for_generation_tile(page, selectors, timeout_s=timeout_s, sleeper=sleeper)
    if not tile_ok:
        sys.stderr.write(f"Warning: Generation wait timed out ({timeout_s}s) for {item.get('output_name')}\n")
        return "timed_out"

    return "submitted"


def _resolve_clock(clock):
    """Resolve clock argument into (datetime.datetime, ISO string)."""
    if clock is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
        return dt, dt.isoformat()
    val = clock() if callable(clock) else clock
    if isinstance(val, (int, float)):
        dt = datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc)
    elif isinstance(val, datetime.datetime):
        dt = val if val.tzinfo is not None else val.replace(tzinfo=datetime.timezone.utc)
    elif isinstance(val, str):
        dt = datetime.datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = datetime.datetime.now(datetime.timezone.utc)
    return dt, dt.isoformat()


def run_submit_batches(page, queue: list, selectors: dict, project_dir: str,
                       batch_size: int = 10, daily_cap: int = 100,
                       rng=None, sleeper=None, clock=None, state: dict = None) -> int:
    """Execute batch submission loop respecting jitter, batch pauses, daily cap, and state tracking.

    Returns exit code 0 on completion or graceful cap stop.
    """
    sleep_fn = sleeper or time.sleep
    now_fn = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))

    items_to_submit = [item for item in queue if item.get("action") == "generate"]
    if not items_to_submit:
        sys.stdout.write("No items queued for generation (all skipped or queue empty).\n")
        return 0

    if state is None:
        state = flow_state.load_state(project_dir=project_dir)

    now_dt, now_iso = _resolve_clock(now_fn)

    # Initial daily cap check
    if is_daily_cap_reached(state, daily_cap=daily_cap, now=now_dt):
        sys.stdout.write(f"Daily generation cap ({daily_cap}) already reached for rolling 24h. Stopping cleanly.\n")
        return 0

    batches = plan_batches(items_to_submit, batch_size=batch_size)
    total_batches = len(batches)
    sys.stdout.write(f"Submitting {len(items_to_submit)} item(s) in {total_batches} batch(es) (batch_size={batch_size}, daily_cap={daily_cap}).\n")

    for batch_idx, batch in enumerate(batches, start=1):
        sys.stdout.write(f"\n--- Batch {batch_idx}/{total_batches} ({len(batch)} items) ---\n")

        for item_idx, item in enumerate(batch, start=1):
            now_dt, now_iso = _resolve_clock(now_fn)

            # Check daily cap mid-batch
            if is_daily_cap_reached(state, daily_cap=daily_cap, now=now_dt):
                sys.stdout.write(f"Daily cap ({daily_cap}) reached mid-batch. Halting cleanly; remaining items remain pending.\n")
                # Mark remaining items in queue as pending
                for rem in items_to_submit:
                    rname = rem["output_name"]
                    curr_status = state.get("items", {}).get(rname, {}).get("status")
                    if curr_status not in ("submitted", "ref_not_found"):
                        flow_state.record_item_state(
                            state,
                            output_name=rname,
                            prompt_hash=rem.get("prompt_hash", ""),
                            status="pending",
                            attempt_id=rem.get("attempt_id"),
                            refs=rem.get("refs", []),
                            now_iso=now_iso,
                        )
                flow_state.save_state(state, project_dir=project_dir)
                return 0

            name = item["output_name"]
            refs = item.get("refs", [])
            att_id = item.get("attempt_id") or flow_state.generate_attempt_id()

            refs_repr = f" with ref [{' | '.join(refs)}]" if refs else ""
            sys.stdout.write(f"Batch {batch_idx}/{total_batches}: Item {item_idx}/{len(batch)} ({name}){refs_repr} submitting...\n")

            outcome = submit_single_prompt(page, item, selectors, sleeper=sleep_fn)
            now_dt, now_iso = _resolve_clock(now_fn)

            if outcome == "submitted":
                sys.stdout.write(f"  -> Generated: {name} (attempt: {att_id})\n")
                flow_state.record_item_state(
                    state,
                    output_name=name,
                    prompt_hash=item.get("prompt_hash", ""),
                    status="submitted",
                    attempt_id=att_id,
                    refs=refs,
                    batch_id=batch_idx,
                    submitted_at=now_iso,
                    now_iso=now_iso,
                )
                flow_state.increment_daily_counter(state, count=1, now_iso=now_iso, now=now_dt)
            elif outcome == "ref_not_found":
                sys.stdout.write(f"  -> Skipped submission: reference not found for {name}\n")
                flow_state.record_item_state(
                    state,
                    output_name=name,
                    prompt_hash=item.get("prompt_hash", ""),
                    status="ref_not_found",
                    attempt_id=att_id,
                    refs=refs,
                    batch_id=batch_idx,
                    now_iso=now_iso,
                )
            elif outcome == "timed_out":
                sys.stdout.write(f"  -> Timed out waiting for generation tile: {name}\n")
                flow_state.record_item_state(
                    state,
                    output_name=name,
                    prompt_hash=item.get("prompt_hash", ""),
                    status="timed_out",
                    attempt_id=att_id,
                    refs=refs,
                    batch_id=batch_idx,
                    now_iso=now_iso,
                )
            else:
                sys.stdout.write(f"  -> Submission failed with error: {name}\n")
                flow_state.record_item_state(
                    state,
                    output_name=name,
                    prompt_hash=item.get("prompt_hash", ""),
                    status="error",
                    attempt_id=att_id,
                    refs=refs,
                    batch_id=batch_idx,
                    now_iso=now_iso,
                )

            state["last_batch_at"] = now_iso
            flow_state.save_state(state, project_dir=project_dir)

            # Jitter between consecutive submissions within active batch regardless of outcome
            if item_idx < len(batch):
                jitter_s = calculate_jitter(rng)
                sys.stdout.write(f"  Jitter: waiting {jitter_s:.1f}s before next submission...\n")
                sleep_fn(jitter_s)

        # Inter-batch pause (between batches, never after the final batch)
        now_dt, now_iso = _resolve_clock(now_fn)
        if batch_idx < total_batches and not is_daily_cap_reached(state, daily_cap=daily_cap, now=now_dt):
            pause_s = calculate_inter_batch_pause(rng)
            sys.stdout.write(f"Batch {batch_idx} completed. Pausing for {pause_s:.1f}s before batch {batch_idx + 1}...\n")
            sleep_fn(pause_s)

    sys.stdout.write("\nAll batches finished successfully.\n")
    return 0
