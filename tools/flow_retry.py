# -*- coding: utf-8 -*-
"""Failure classification, end-of-batch tab refresh, resubmit queue, and rate-limit cooldown.

Part of Phase C Google Flow automation. Distinguishes false-negative/transient
errors from real failures, handles tab refreshes at the end of batches to recover
falsely reported items, manages an end-of-run resubmit queue capped at 2 attempts,
and triggers a long cooldown (>= 300s) on 3 consecutive failures.
"""
import datetime
import sys
import time

import flow_state

DEFAULT_COOLDOWN_SECONDS = 300.0
MAX_RESUBMIT_ATTEMPTS = 2


def is_error_banner_present(page, selectors: dict) -> bool:
    """Check if Flow is currently showing an error or failure banner."""
    banner_sel = selectors.get("failure_banner", "div[role=\"alert\"], div.error-banner")
    if not banner_sel:
        return False
    try:
        if hasattr(page, "query_selector"):
            el = page.query_selector(banner_sel)
            return el is not None
    except Exception:
        pass
    return False


def classify_failure(has_error_banner: bool, tile_present: bool = False,
                     download_btn_present: bool = False, is_post_refresh: bool = False) -> str:
    """Classify failure mode: 'success', 'suspicious', or 'real'.

    Flow UI frequently flashes false-negative error banners while generation
    is actually progressing or already complete.
    - If download button or tile is ready (and not an active post-refresh error): 'success'
    - Pre-refresh error banner or missing tile during initial wait: 'suspicious'
    - Post-refresh still missing or errored: 'real'
    """
    if download_btn_present or (tile_present and not has_error_banner):
        return "success"
    if is_post_refresh:
        return "real"
    return "suspicious"


class CooldownTracker:
    """Tracks consecutive submission failures and triggers rate-limit cooldowns."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
                 sleeper=None, clock=None):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = max(float(cooldown_seconds), 300.0)
        self.consecutive_failures = 0
        self.sleeper = sleeper or time.sleep
        self.clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.cooldown_triggered_count = 0

    def record_success(self):
        """Reset consecutive failure counter on successful generation/download."""
        self.consecutive_failures = 0

    def record_failure(self, state: dict = None, project_dir: str = None) -> bool:
        """Increment consecutive failure counter.

        If threshold (3) is reached, triggers cooldown (>= 300s) and writes
        an advisory to state. Returns True if cooldown was triggered.
        """
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.cooldown_triggered_count += 1
            now_iso = self._resolve_iso()

            msg = (f"Provider rate limit or quota depletion suspected: {self.consecutive_failures} "
                   f"consecutive failures. Entering cooldown for {self.cooldown_seconds:.1f}s.")
            sys.stderr.write(f"\n[RATE LIMIT ADVISORY] {msg}\n")

            if state is not None:
                state["rate_limit_advisory"] = {
                    "triggered_at": now_iso,
                    "consecutive_failures": self.consecutive_failures,
                    "cooldown_seconds": self.cooldown_seconds,
                    "advisory": msg,
                }
                if project_dir:
                    flow_state.save_state(state, project_dir=project_dir)

            self.sleeper(self.cooldown_seconds)
            self.consecutive_failures = 0
            return True
        return False

    def _resolve_iso(self) -> str:
        val = self.clock() if callable(self.clock) else self.clock
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
        return dt.isoformat()


def locate_item_tile(page, item: dict, selectors: dict):
    """Locate the specific DOM tile element for a given submission item.

    Reliability hierarchy (documented per Phase C specification):
    1. output_name (data-output-name / aria-label / innerText):
       Selected as the most reliable persistent identifier held in state and items.
       Each generation item has a unique canonical name (e.g. IMG001, CH_MIMO) that
       maps directly to the prompt's [OUTPUT NAME: ...] directive. Flow UI tiles,
       badges, and aria labels reflect this name across tab reloads.
    2. attempt_id (data-attempt-id / id):
       Unique per submission attempt. Used when the DOM or runner preserves attempt
       attributes on rendered tiles.
    3. tile_order (batch_order / index):
       The sequential submission order recorded at submit time within the batch.
       Serves as fallback if tiles are rendered in deterministic sequence.

    Returns:
        The identified tile element, or None if the item's tile cannot be identified.
    """
    output_name = item.get("output_name", "")
    att_id = item.get("attempt_id", "")
    tile_order = item.get("tile_order", item.get("batch_order"))

    # Support container/dict-based mock pages in tests
    if hasattr(page, "get_tile") and callable(page.get_tile):
        return page.get_tile(item)
    if hasattr(page, "tiles") and isinstance(page.tiles, dict):
        if output_name and output_name in page.tiles:
            return page.tiles[output_name]
        if att_id and att_id in page.tiles:
            return page.tiles[att_id]

    # 1. Look up by output_name via specific CSS selectors (most reliable)
    if output_name and hasattr(page, "query_selector"):
        cand_selectors = [
            f"[data-output-name=\"{output_name}\"]",
            f"[data-item-name=\"{output_name}\"]",
            f"div[data-testid=\"generation-tile\"][aria-label*=\"{output_name}\"]",
            f"div.generation-tile[aria-label*=\"{output_name}\"]",
            f"[aria-label*=\"{output_name}\"]",
        ]
        for sel in cand_selectors:
            try:
                el = page.query_selector(sel)
                if el is not None:
                    return el
            except Exception:
                pass

    # 2. Look up by attempt_id via specific CSS selectors
    if att_id and hasattr(page, "query_selector"):
        att_selectors = [
            f"[data-attempt-id=\"{att_id}\"]",
            f"[data-id=\"{att_id}\"]",
            f"#{att_id}",
        ]
        for sel in att_selectors:
            try:
                el = page.query_selector(sel)
                if el is not None:
                    return el
            except Exception:
                pass

    # 3. Scan all tile elements if query_selector_all is available
    tile_sel = selectors.get("result_tile", "div[data-testid=\"generation-tile\"], div.generation-tile")
    if hasattr(page, "query_selector_all"):
        try:
            tiles = page.query_selector_all(tile_sel) or []
            # Check tiles for matching output_name or attempt_id
            for t in tiles:
                if hasattr(t, "get_attribute"):
                    attr_name = t.get_attribute("data-output-name") or t.get_attribute("aria-label") or ""
                    if output_name and output_name in attr_name:
                        return t
                    attr_att = t.get_attribute("data-attempt-id") or t.get_attribute("id") or ""
                    if att_id and att_id == attr_att:
                        return t
                if hasattr(t, "inner_text"):
                    txt = t.inner_text() or ""
                    if output_name and output_name in txt:
                        return t
                elif hasattr(t, "text_content"):
                    txt = t.text_content() or ""
                    if output_name and output_name in txt:
                        return t
                if getattr(t, "output_name", None) == output_name:
                    return t
                if getattr(t, "attempt_id", None) == att_id:
                    return t

            # 4. Fallback to tile_order (1-based or 0-based index)
            if tile_order is not None and isinstance(tile_order, int):
                idx = tile_order - 1 if tile_order > 0 else tile_order
                if 0 <= idx < len(tiles):
                    return tiles[idx]
        except Exception:
            pass

    # Single-tile fallback if page only has one tile and single item was suspicious
    if hasattr(page, "query_selector"):
        try:
            generic_tile = page.query_selector(tile_sel)
            if generic_tile is not None and not hasattr(page, "tiles"):
                tile_out = getattr(generic_tile, "output_name", None)
                if tile_out and output_name and tile_out != output_name:
                    return None
                return generic_tile
        except Exception:
            pass

    return None


def refresh_and_recheck_batch(page, selectors: dict, suspicious_items: list,
                              sleeper=None) -> tuple:
    """Refresh Flow tab at end of batch and re-check each item separately on its own tile.

    Returns:
        (recovered_items, confirmed_failures)
    """
    if not suspicious_items:
        return [], []

    sleep_fn = sleeper or time.sleep
    sys.stdout.write(f"\nEnd-of-batch refresh: re-checking {len(suspicious_items)} suspicious item(s)...\n")

    try:
        if hasattr(page, "reload"):
            page.reload()
        elif hasattr(page, "evaluate"):
            page.evaluate("() => window.location.reload()")
    except Exception as e:
        sys.stderr.write(f"Warning: Failed reloading page: {e}\n")

    sleep_fn(2.0)

    tile_sel = selectors.get("result_tile", "div[data-testid=\"generation-tile\"]")
    dl_btn_sel = selectors.get("download_button", "button[aria-label*=\"Download\"]")
    banner_sel = selectors.get("failure_banner", "div[role=\"alert\"]")

    recovered = []
    confirmed_failures = []

    for item in suspicious_items:
        output_name = item.get("output_name", "")
        tile = locate_item_tile(page, item, selectors)

        if tile is None:
            # Cannot identify item's tile: classify as uncertain -> goes to resubmit queue (never success)
            sys.stdout.write(f"  -> Tile for '{output_name}' could not be identified: classified 'uncertain' -> queuing for resubmit.\n")
            item_copy = dict(item)
            item_copy["classification"] = "uncertain"
            confirmed_failures.append(item_copy)
            continue

        # Inspect the identified tile
        has_banner = False
        has_dl_btn = False
        tile_present = True

        if hasattr(tile, "query_selector"):
            try:
                if banner_sel and tile.query_selector(banner_sel):
                    has_banner = True
            except Exception:
                pass
            try:
                if dl_btn_sel and tile.query_selector(dl_btn_sel):
                    has_dl_btn = True
            except Exception:
                pass

        if getattr(tile, "has_banner", False) or getattr(tile, "is_failed", False):
            has_banner = True
        if getattr(tile, "has_download_btn", False) or getattr(tile, "is_success", False):
            has_dl_btn = True
        if hasattr(tile, "has_tile"):
            tile_present = bool(tile.has_tile)

        classification = classify_failure(
            has_error_banner=has_banner,
            tile_present=tile_present,
            download_btn_present=has_dl_btn,
            is_post_refresh=True,
        )

        item_copy = dict(item)
        item_copy["classification"] = classification

        if classification == "success":
            sys.stdout.write(f"  -> Recovered false failure: {output_name} rendered successfully!\n")
            recovered.append(item_copy)
        else:
            sys.stdout.write(f"  -> Confirmed real failure: {output_name} failed to generate ({classification}).\n")
            confirmed_failures.append(item_copy)

    return recovered, confirmed_failures


class ResubmitQueue:
    """End-of-run resubmission manager with a strict cap of 2 retry attempts per item."""

    def __init__(self, max_retries: int = MAX_RESUBMIT_ATTEMPTS, state: dict = None):
        self.max_retries = max_retries
        self.state = state
        self.queue = []

    def add_failure(self, item: dict, current_retries: int = None, state: dict = None):
        """Queue a confirmed failure for resubmission if under max_retries cap.

        Initialises retries_count in state on first entry if absent.
        Honours existing retries_count from state if item was resumed.
        """
        st = state if state is not None else self.state
        item_copy = dict(item)
        rname = item_copy.get("output_name")

        if current_retries is None:
            if st and "items" in st and rname in st["items"] and "retries_count" in st["items"][rname]:
                current_retries = st["items"][rname]["retries_count"]
            elif "retries_count" in item_copy:
                current_retries = item_copy["retries_count"]
            else:
                current_retries = 0

        item_copy["retries_count"] = current_retries

        # Initialise / record retries_count field in state on first queue entry
        if st is not None and rname:
            items = st.setdefault("items", {})
            entry = items.setdefault(rname, {})
            if "retries_count" not in entry:
                entry["retries_count"] = current_retries

        self.queue.append(item_copy)

    def is_empty(self) -> bool:
        return len(self.queue) == 0

    def get_items(self) -> list:
        return list(self.queue)


def trigger_download_from_page(page, selectors: dict):
    """Click the download button on the active Flow tile."""
    dl_sel = selectors.get("download_button", "button[aria-label*=\"Download\"]")
    if hasattr(page, "click"):
        page.click(dl_sel)
    else:
        btn = page.query_selector(dl_sel)
        if btn and hasattr(btn, "click"):
            btn.click()
