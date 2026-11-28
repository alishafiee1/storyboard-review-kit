# -*- coding: utf-8 -*-
"""CLI and dry-run execution for Google Flow automation (Phase A).

Connects over Chrome DevTools Protocol (CDP), locates the active Flow tab,
validates UI selectors, and computes the generation/skip queue without
triggering generation or modifying existing images.
"""
import argparse
import os
import re
import sys
import time

# Note: kitcore, story, flowname are safe to import (pure Python)
import flowname
import kitcore
import story
from flow_state import (compute_prompt_hash, generate_attempt_id, load_state,
                        record_item_state, save_state, time_step)

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_SELECTORS_REL = os.path.join("tools", "flow_selectors.json")

BUILTIN_SELECTORS = {
    "version": 1,
    "flow_url_pattern": r"flow\.google\.com/project/|labs\.google/fx/",
    "prompt_box": "div[role=\"textbox\"][aria-label=\"What do you want to create?\"]",
    "submit_button": "button[aria-label=\"Start generation\"]",
    "ingredients_button": "button[aria-label=\"Add ingredients to the prompt box\"]",
    "ingredient_search_input": "input[placeholder*=\"Search\"], input[aria-label*=\"Search\"]",
    "ingredient_result_item": "div[role=\"option\"], div[role=\"listbox\"] div[role=\"button\"]",
    "result_tile": "div[data-testid=\"generation-tile\"], div[role=\"img\"][aria-label*=\"Generated\"], div.generation-tile",
    "download_button": "button[aria-label*=\"Download\"], button[data-testid*=\"download\"], div.generation-tile button[aria-label*=\"Download\"]",
    "failure_banner": "div[role=\"alert\"], div[data-testid*=\"error\"], div.error-banner, div[class*=\"error-message\"]",
    "_unverified": ["ingredient_search_input", "ingredient_result_item", "result_tile", "download_button", "failure_banner"],
}


def load_selectors(path: str = None, project_dir: str = None) -> dict:
    """Load selectors from JSON file, falling back to built-ins if missing or invalid."""
    candidate_paths = []
    if path:
        candidate_paths.append(os.path.abspath(path))
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_paths.append(os.path.join(tools_dir, "flow_selectors.json"))
    if project_dir:
        candidate_paths.append(os.path.join(os.path.abspath(project_dir), DEFAULT_SELECTORS_REL))

    for p in candidate_paths:
        if os.path.isfile(p):
            try:
                import json
                with open(p, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and "prompt_box" in data and "submit_button" in data:
                    res = dict(BUILTIN_SELECTORS)
                    res.update(data)
                    return res
                sys.stderr.write(f"Warning: Malformed selectors in {p}, using default built-ins.\n")
            except Exception as e:
                sys.stderr.write(f"Warning: Failed reading selectors from {p}: {e}, using default built-ins.\n")
            break

    return dict(BUILTIN_SELECTORS)


def scan_existing_image_bases(project_dir: str) -> set:
    """Scan images directory to find all output names that currently have an image file."""
    images_dir = os.path.join(project_dir, "images")
    if not os.path.isdir(images_dir):
        return set()

    cfg = flowname.settings(project_dir)
    bases = set()
    for f in flowname.walk(images_dir):
        if not f.lower().endswith(kitcore.IMG_EXT):
            continue
        fname = os.path.basename(f)
        p = flowname.parse(fname, cfg)
        if p and p.get("base"):
            bases.add(p["base"])
        else:
            stem = os.path.splitext(fname)[0]
            m = flowname.LEGACY_IMG.match(stem)
            if m:
                bases.add(m.group(1))
            else:
                # Reference name without hex id tail
                clean = re.sub(r"_[0-9a-fA-F]{8}$", "", stem)
                bases.add(clean)
                bases.add(stem)
    return bases


def scan_story_markers(project_dir: str) -> dict:
    """Parse scenario/story.txt and scenario/reference.txt for image markers and metadata."""
    img_info = {}
    for book in ("story", "refs"):
        fname = "story.txt" if book == "story" else "reference.txt"
        path = os.path.join(project_dir, "scenario", fname)
        if not os.path.isfile(path):
            continue
        lines = kitcore.read_lines(path)
        scenes = story.story_scenes(lines, book=book)
        for sc in scenes:
            for b in sc.get("blocks", []):
                for img in b.get("images", []):
                    img_info[img["id"]] = {
                        "pick": (img.get("pick") or "").strip(),
                        "stale": bool(img.get("stale")),
                        "status": img.get("status") or "",
                        "off": bool(img.get("off")),
                    }
    return img_info


def compute_queue(project_dir: str, only_name: str = None) -> tuple:
    """Parse prompts.txt, compare against state and disk, and compute skip/generate decisions.

    Returns:
        (queue_items, summary_dict)
    """
    prompts_file = os.path.join(project_dir, "prompts", "prompts.txt")
    if not os.path.isfile(prompts_file):
        raise FileNotFoundError(f"prompts/prompts.txt not found in {project_dir}")

    lines = kitcore.read_lines(prompts_file)
    ranges = story.prompt_ranges(lines)
    if not ranges:
        raise ValueError(f"prompts/prompts.txt in {project_dir} is empty or has no prompt blocks")

    parsed_prompts = story.parse_prompts(lines)
    # File order: non-IMG (references) first, then scenes (IMG###) in file order
    scene_re = kitcore.BOOK_RULES["story"]["item_re"]
    ordered_keys = list(ranges.keys())
    ref_keys = [k for k in ordered_keys if not scene_re.match(k)]
    scene_keys = [k for k in ordered_keys if scene_re.match(k)]
    all_keys = ref_keys + scene_keys

    if only_name:
        if only_name not in all_keys:
            raise KeyError(f"Item '{only_name}' not found in prompts.txt")
        all_keys = [only_name]

    existing_images = scan_existing_image_bases(project_dir)
    story_markers = scan_story_markers(project_dir)
    state = load_state(project_dir=project_dir)
    state_items = state.get("items", {})

    queue = []
    summary = {
        "total": len(all_keys),
        "skipped": 0,
        "queued": 0,
        "reasons": {}
    }

    for key in all_keys:
        pdata = parsed_prompts.get(key, {})
        raw_prompt = pdata.get("prompt", "")
        refs = pdata.get("refs", [])
        curr_hash = compute_prompt_hash(raw_prompt)

        prev_item = state_items.get(key, {})
        prev_hash = prev_item.get("prompt_hash")
        prev_att_id = prev_item.get("attempt_id")

        has_image = key in existing_images
        sinfo = story_markers.get(key, {})
        is_stale = sinfo.get("stale", False)
        pick_val = sinfo.get("pick", "")
        has_approved_pick = bool(pick_val)

        # Rule R5:
        # 1) An item with an approved pick in story.txt and an existing image is skipped
        #    unless its prompt hash changed.
        # 2) Otherwise, skipped if: image exists AND prompt hash matches state AND not stale.
        if has_approved_pick and has_image:
            if prev_hash and curr_hash != prev_hash:
                action = "generate"
                reason = "prompt_hash_changed"
            else:
                action = "skip"
                reason = "approved_pick"
        else:
            if has_image and (prev_hash == curr_hash) and (not is_stale):
                action = "skip"
                reason = "existing_and_unchanged"
            else:
                action = "generate"
                if not has_image:
                    reason = "image_missing"
                elif is_stale:
                    reason = "image_stale"
                elif prev_hash and curr_hash != prev_hash:
                    reason = "prompt_hash_changed"
                else:
                    reason = "new_prompt"

        if action == "skip":
            att_id = prev_att_id or generate_attempt_id()
            status = "skipped"
            summary["skipped"] += 1
        else:
            att_id = generate_attempt_id()
            status = "pending"
            summary["queued"] += 1

        summary["reasons"][reason] = summary["reasons"].get(reason, 0) + 1

        queue.append({
            "output_name": key,
            "action": action,
            "reason": reason,
            "prompt_hash": curr_hash,
            "attempt_id": att_id,
            "status": status,
            "refs": refs,
            "raw_prompt": raw_prompt,
            "has_image": has_image,
            "has_approved_pick": has_approved_pick,
            "is_stale": is_stale,
        })

    return queue, summary


def connect_cdp(cdp_url: str):
    """Lazily import playwright and connect to Chrome over CDP.

    Returns (playwright_context, browser) or (None, None) on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("Error: Playwright is not installed. Install with: pip install playwright\n")
        return None, None

    try:
        pw = sync_playwright().start()
    except Exception as e:
        sys.stderr.write(f"Error: Failed starting Playwright: {e}\n")
        return None, None

    try:
        browser = pw.chromium.connect_over_cdp(cdp_url)
        return pw, browser
    except Exception as e:
        try:
            pw.stop()
        except Exception:
            pass
        sys.stderr.write(f"Error: Could not connect to Chrome on {cdp_url}. Is Chrome running with --remote-debugging-port=9222?\n")
        return None, None


def find_flow_tab(browser, selectors: dict):
    """Search open browser pages across contexts for the Flow tab."""
    pages = []
    try:
        for ctx in browser.contexts:
            pages.extend(ctx.pages)
    except Exception as e:
        sys.stderr.write(f"Error retrieving browser contexts: {e}\n")
        return None

    if not pages:
        sys.stderr.write("Error: No open browser tabs detected in Chrome instance.\n")
        return None

    pattern = selectors.get("flow_url_pattern") or BUILTIN_SELECTORS["flow_url_pattern"]
    regex = re.compile(pattern)

    login_page = None
    for p in pages:
        url = p.url or ""
        if "accounts.google.com" in url or "/signin" in url:
            login_page = p
        if regex.search(url):
            return p

    if login_page:
        sys.stderr.write("Flow login required; navigate to project page\n")
        return None

    sys.stderr.write("No active Flow tab found.\nOpen tabs:\n")
    for p in pages:
        try:
            t = p.title()
        except Exception:
            t = "(untitled)"
        sys.stderr.write(f" - {t}: {p.url}\n")
    return None


def verify_selectors(page, selectors: dict) -> tuple:
    """Verify presence of required selectors in page DOM without clicking anything.

    Distinguishes verified selectors from unverified best-guesses.
    Returns (all_verified_ok_bool, results_dict).
    """
    results = {}
    all_ok = True
    unverified_keys = set(selectors.get("_unverified", []))
    check_keys = [
        ("prompt_box", selectors.get("prompt_box")),
        ("submit_button", selectors.get("submit_button")),
        ("ingredients_button", selectors.get("ingredients_button")),
        ("ingredient_search_input", selectors.get("ingredient_search_input")),
        ("ingredient_result_item", selectors.get("ingredient_result_item")),
        ("result_tile", selectors.get("result_tile")),
        ("download_button", selectors.get("download_button")),
        ("failure_banner", selectors.get("failure_banner")),
    ]
    for key, sel in check_keys:
        if not sel:
            continue
        try:
            el = page.query_selector(sel)
            found = el is not None
        except Exception:
            found = False
        is_unverified = key in unverified_keys
        results[key] = {"selector": sel, "found": found, "unverified": is_unverified}
        if not is_unverified and not found and key in ("prompt_box", "submit_button", "ingredients_button"):
            all_ok = False

    return all_ok, results


def run_dry_run(args, project_dir: str) -> int:
    """Execute complete dry-run sequence and report results."""
    timings = []

    def timed_action(name, fn, *fn_args, **fn_kwargs):
        t0 = time.perf_counter()
        try:
            with time_step(name, project_dir=project_dir, verbose=args.verbose):
                res = fn(*fn_args, **fn_kwargs)
            return res
        finally:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            timings.append((name, elapsed_ms))

    # 1. Config & selectors
    selectors = timed_action("load_selectors", load_selectors, args.selectors, project_dir)

    # 2. Queue calculation
    try:
        queue, summary = timed_action("compute_queue", compute_queue, project_dir, args.only)
    except FileNotFoundError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1
    except (ValueError, KeyError) as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    # 3. Connect to Chrome CDP
    pw, browser = timed_action("cdp_connect", connect_cdp, args.cdp_url)
    if not browser:
        return 1

    try:
        # 4. Find Flow tab
        page = timed_action("find_flow_tab", find_flow_tab, browser, selectors)
        if not page:
            return 1

        tab_title = page.title()
        tab_url = page.url

        # 5. Verify selectors (never clicks submit button!)
        all_ok, sel_results = timed_action("verify_selectors", verify_selectors, page, selectors)
        if not all_ok:
            sys.stderr.write("Error: One or more required Flow selectors were not found on the page.\n")
            for k, info in sel_results.items():
                if not info.get("unverified"):
                    mark = "FOUND" if info["found"] else "MISSING"
                    sys.stderr.write(f"  [{mark}] {k}: {info['selector']}\n")
            return 1

        # 6. Update state
        state = load_state(project_dir=project_dir)
        for item in queue:
            status = "skipped" if item["action"] == "skip" else "dry_run_verified"
            record_item_state(
                state,
                output_name=item["output_name"],
                prompt_hash=item["prompt_hash"],
                status=status,
                attempt_id=item["attempt_id"],
                refs=item["refs"],
            )
        timed_action("save_state", save_state, state, project_dir=project_dir)

    finally:
        try:
            browser.close()
        except Exception:
            pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass

    # 7. Print Console Report
    sys.stdout.write("============================================================\n")
    sys.stdout.write("Flow Sync (Phase A Dry-Run) Summary\n")
    sys.stdout.write("============================================================\n")
    sys.stdout.write(f"CDP Connection: Connected to {args.cdp_url}\n")
    sys.stdout.write(f"Flow Project Tab: \"{tab_title}\" ({tab_url})\n\n")

    sys.stdout.write("Selectors Validation:\n")
    for k, info in sel_results.items():
        if not info.get("unverified"):
            mark = "FOUND" if info["found"] else "MISSING"
            sys.stdout.write(f"  [{mark}] {k}: {info['selector']}\n")

    unverified_items = {k: v for k, v in sel_results.items() if v.get("unverified")}
    if unverified_items:
        sys.stdout.write("\nUnverified Selectors:\n")
        for k, info in unverified_items.items():
            mark = "UNVERIFIED:FOUND" if info["found"] else "UNVERIFIED:MISSING"
            sys.stdout.write(f"  [{mark}] {k}: {info['selector']}\n")

    sys.stdout.write("\nQueue Summary:\n")
    sys.stdout.write(f"  Total prompts : {summary['total']}\n")
    sys.stdout.write(f"  Skipped items : {summary['skipped']}\n")
    sys.stdout.write(f"  Queued items  : {summary['queued']}\n")
    if summary["reasons"]:
        sys.stdout.write("  Reasons breakdown:\n")
        for r, cnt in sorted(summary["reasons"].items()):
            sys.stdout.write(f"    - {r}: {cnt}\n")

    sys.stdout.write("\nStep Timing:\n")
    for name, elapsed_ms in timings:
        sys.stdout.write(f"  {name:<18} : {elapsed_ms}ms\n")
    sys.stdout.write("============================================================\n")
    sys.stdout.write("Dry-run completed successfully. Zero generation calls made.\n")
    return 0


def _cleanup_browser(pw, browser):
    if browser:
        try:
            browser.close()
        except Exception:
            pass
    if pw:
        try:
            pw.stop()
        except Exception:
            pass


def _prepare_runner(args, project_dir: str):
    selectors = load_selectors(args.selectors, project_dir)
    try:
        queue, _ = compute_queue(project_dir, args.only)
    except (FileNotFoundError, ValueError, KeyError) as e:
        sys.stderr.write(f"Error: {e}\n")
        return None, None, None, None, None

    pw, browser = connect_cdp(args.cdp_url)
    if not browser:
        return None, None, None, None, None

    try:
        page = find_flow_tab(browser, selectors)
        if not page:
            _cleanup_browser(pw, browser)
            return None, None, None, None, None

        all_ok, sel_results = verify_selectors(page, selectors)
        if not all_ok:
            sys.stderr.write("Error: Required selectors missing on page:\n")
            for k, info in sel_results.items():
                if not info.get("unverified") and not info["found"]:
                    sys.stderr.write(f"  [MISSING] {k}: {info['selector']}\n")
            _cleanup_browser(pw, browser)
            return None, None, None, None, None

        return page, queue, selectors, pw, browser
    except Exception:
        _cleanup_browser(pw, browser)
        raise


def run_submit(args, project_dir: str) -> int:
    """Execute Phase B batch submission with references and natural delays."""
    is_submit = bool(getattr(args, "submit", False) or getattr(args, "mode", None) == "submit")
    if not is_submit:
        sys.stderr.write("Error: Explicit submit opt-in required (--submit or --mode submit).\n")
        return 1

    import flow_submit

    page, queue, selectors, pw, browser = _prepare_runner(args, project_dir)
    if not page:
        return 1
    try:
        return flow_submit.run_submit_batches(
            page=page,
            queue=queue,
            selectors=selectors,
            project_dir=project_dir,
            batch_size=args.batch_size,
            daily_cap=args.daily_cap,
        )
    finally:
        _cleanup_browser(pw, browser)


def run_download(args, project_dir: str) -> int:
    """Execute Phase C intercepted download, naming, and resilient retries."""
    is_download = bool(getattr(args, "download", False) or getattr(args, "mode", None) == "download")
    if not is_download:
        sys.stderr.write("Error: Explicit download opt-in required (--download or --mode download).\n")
        return 1

    from flow_recover import run_download_phase

    page, queue, selectors, pw, browser = _prepare_runner(args, project_dir)
    if not page:
        return 1
    try:
        return run_download_phase(
            page=page,
            queue=queue,
            selectors=selectors,
            project_dir=project_dir,
            batch_size=args.batch_size,
            max_retries=args.max_retries,
            unmatched_dir=args.unmatched_dir,
            cooldown_seconds=args.cooldown_seconds,
        )
    finally:
        _cleanup_browser(pw, browser)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Flow sync automation CLI (Phase A: Dry-run, Phase B: Submit, Phase C: Download)")
    parser.add_argument("--dry-run", action="store_true", help="Validate selectors and queue without generating")
    parser.add_argument("--submit", action="store_true", help="Execute batch submissions to Flow (Phase B)")
    parser.add_argument("--download", action="store_true", help="Execute intercepted download and retries (Phase C)")
    parser.add_argument("--mode", default=None, choices=["dry-run", "submit", "download"], help="Execution mode: dry-run, submit, or download")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for submissions (default: 10)")
    parser.add_argument("--daily-cap", type=int, default=100, help="Daily submission cap (default: 100)")
    parser.add_argument("--max-retries", type=int, default=2, help="Maximum resubmit attempts per item (default: 2)")
    parser.add_argument("--unmatched-dir", default=None, help="Directory for unmatched downloads (default: images/_unmatched)")
    parser.add_argument("--cooldown-seconds", type=float, default=300.0, help="Cooldown in seconds after 3 consecutive failures (default: 300.0)")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL, help=f"CDP URL (default: {DEFAULT_CDP_URL})")
    parser.add_argument("--project", default=".", help="Project directory (default: current directory)")
    parser.add_argument("--verbose", action="store_true", help="Verbose timing output")
    parser.add_argument("--only", default=None, help="Process only a specific output name")
    parser.add_argument("--config", default=None, help="Optional config path")
    parser.add_argument("--selectors", default=None, help="Path to flow_selectors.json")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    project_dir = os.path.abspath(args.project)

    is_dry_run = bool(args.dry_run or (args.mode == "dry-run"))
    is_submit = bool(args.submit or (args.mode == "submit"))
    is_download = bool(args.download or (args.mode == "download"))

    active_modes = sum([is_dry_run, is_submit, is_download])
    if active_modes > 1:
        sys.stderr.write("Error: Conflicting modes specified. Choose exactly one of --dry-run, --submit, or --download.\n")
        return 1

    if active_modes == 0:
        sys.stderr.write("Phase A supports only --dry-run, Phase B adds --submit, and Phase C adds --download. Please run with --dry-run, --submit, or --download.\n")
        return 1

    if is_dry_run:
        return run_dry_run(args, project_dir)
    elif is_submit:
        return run_submit(args, project_dir)
    else:
        return run_download(args, project_dir)


if __name__ == "__main__":
    sys.exit(main())
