# 001 — Phase A: Flow sync skeleton, CDP tab discovery, and dry-run queue: technical spec

> Source of truth for the coder. Written in English for technical clarity.
> Every rule has a bold ID (**R1**, **R2** ...). Scenarios in `acceptance.feature` are tagged with `@R1`, `@R2`, etc.

## 1. Summary

Phase A implements the foundational CLI skeleton `tools/flow_sync.py` and configuration data `tools/flow_selectors.json`. It connects via Playwright CDP to an already-running Chrome instance on `127.0.0.1:9222`, finds the active Flow project tab, parses `prompts/prompts.txt`, computes a skip/generate queue using prompt hashes, `image-stale` flags, and approved picks, and validates selector presence in `--dry-run` mode without ever triggering generation. Playwright is lazily imported so unit tests execute without playwright installed.

## 2. Rules

- **R1** `tools/flow_sync.py` provides a CLI skeleton supporting `--dry-run`, `--only <NAME>`, and `--config <PATH>`. Playwright (`playwright.sync_api` / `async_api`) MUST be imported lazily only when browser interaction is required, allowing unit tests to run in environments without Playwright installed.
- **R2** When connecting, the tool targets `http://127.0.0.1:9222` using CDP. It scans open tabs/pages for a URL containing `flow.google.com/project/` (or `labs.google/fx/` / legacy Flow URLs). If no matching tab is found, it logs available tab titles/URLs and exits with code 1 without error tracebacks.
- **R3** Flow UI selectors are externalized to `tools/flow_selectors.json` (data not code). The tool loads this file at runtime. In `--dry-run`, it queries the DOM to verify selector presence for prompt box, submit button, and ingredient reference button, reporting status per selector.
- **R4** `--dry-run` NEVER triggers generation. Under no circumstances may `button[aria-label="Start generation"]` (or any generation submit element) be clicked during `--dry-run`.
- **R5** Queue calculation parses `prompts/prompts.txt` in file order (references first, then scenes `=== IMG### ===`). An item is skipped if all conditions are met: an image file already exists for that output name, the stable SHA-256 hash of the English prompt text matches `.kit/flow-state.json`, and `story.txt` does not contain `image-stale: yes` for that image. An item with an approved `pick:` in `story.txt` and an existing image is skipped unless its prompt hash changed.
- **R6** State tracking initializes schema version 2 in `.kit/flow-state.json`. Each queue item tracks an `attempt_id` (UUID or timestamp-based monotonic id), current status (`pending`, `skipped`, `dry_run_verified`, `error`), prompt hash, output name, and reference dependencies.
- **R7** Step execution emits a per-step timing log (timestamp, elapsed ms, step name, outcome) to stdout/stderr or `.kit/flow-sync.log`.
- **R8** Zero LLM calls. No chat or completion model invocations inside `flow_sync.py`.
- **R9** Privacy & Security: No browser cookies, session tokens, passwords, or personal credentials may be logged or written into `.kit/` or repository files.
- **R10** No file modification to existing images. `ENGINE.txt` must remain untouched until the feature is stable and approved for distribution.

## 3. Data

- `tools/flow_selectors.json`:
  ```json
  {
    "version": 1,
    "flow_url_pattern": "flow\\.google\\.com/project/|labs\\.google/fx/",
    "prompt_box": "div[role=\"textbox\"][aria-label=\"What do you want to create?\"]",
    "submit_button": "button[aria-label=\"Start generation\"]",
    "ingredients_button": "button[aria-label=\"Add ingredients to the prompt box\"]",
    "ingredient_search_input": "input[placeholder*=\"Search\"], input[aria-label*=\"Search\"]"
  }
  ```
- `.kit/flow-state.json`:
  ```json
  {
    "schemaVersion": 2,
    "last_run": "2026-11-28T10:00:00Z",
    "items": {
      "STYLE_ANCHOR": {
        "output_name": "STYLE_ANCHOR",
        "prompt_hash": "a1b2c3d4...",
        "attempt_id": "att_001",
        "status": "dry_run_verified",
        "updated_at": "2026-11-28T10:00:05Z"
      }
    }
  }
  ```

## 4. API / Logic

CLI invocation:
```bash
python tools/flow_sync.py --dry-run [--only NAME] [--selectors tools/flow_selectors.json]
```

Exit codes:
- `0`: Success (all dry-run checks and queue analysis passed).
- `1`: CDP connection failed, Flow tab missing, or invalid selectors detected.

## 5. Screens

Console output only. Reports:
- CDP connection status (port 9222)
- Flow project tab title and URL
- Selector validation report (each selector in `flow_selectors.json` checked)
- Queue summary: total prompts, skipped items (with reasons: existing/unchanged/picked), queued items
- Step timing summary table

## 6. Files to create or change

- `tools/flow_sync.py` — CLI skeleton with lazy playwright loading and dry-run logic
- `tools/flow_state.py` — state schema/IO helpers, no playwright
- `tools/flow_selectors.json` — External selector mapping
- `tools/tests/test_flow_sync_dryrun.py` — Unit tests for prompt parsing, hash stability, skip rules, and state schema
- `.kit/flow-state.json` — Generated runtime state in target project (not committed in engine repo)

## 7. Edge cases

- Playwright not installed in environment: CLI `--help` and unit tests still execute cleanly; only active CDP calls fail with a friendly install tip.
- Chrome running on 9222 but user is on Google login screen: abort with warning "Flow login required; navigate to project page".
- `prompts/prompts.txt` missing or empty: exit 1 with clear diagnostic message.
- Malformed selectors JSON: report schema error and fallback to default built-ins if available.

## 8. Acceptance run

```bash
python -m unittest tools/tests/test_flow_sync_dryrun.py
```

## Acceptance criteria

- **Must happen:** CLI connects over CDP to port 9222; identifies Flow tab; validates selectors against DOM in `--dry-run`; outputs accurate skip/generate queue; logs step timing; records attempt ids in `.kit/flow-state.json`.
- **Must not happen:** Generate button clicked; prompt text submitted; files downloaded or written into `images/`; LLM calls made; `ENGINE.txt` modified.
- **Done when:** Unit tests pass without Playwright, and `--dry-run` successfully verifies selectors against an open Flow tab without triggering generation.

## Documentation Impact

- none — internal tools development. (README and ARCHITECTURE updates deferred until feature release).

## Open Questions

- none

## Decisions

- Lazy import of Playwright. Because unit tests must pass in environments where Playwright browser binaries are not installed.
- Selectors in `tools/flow_selectors.json`. Because Flow DOM changes can be patched without editing Python code (enabling Phase D self-heal).
- Explicit per-item attempt ids in `flow-state.json`. Because tracking retry lineage is necessary for Phase C download matching.
