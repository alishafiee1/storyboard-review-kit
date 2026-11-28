# 015 — Phase C: Intercepted downloads, output naming, and resilient retries: technical spec

> Source of truth for the coder. Written in English for technical clarity.
> Every rule has a bold ID (**R1**, **R2** ...). Scenarios in `acceptance.feature` are tagged with `@R1`, `@R2`, etc.

## 1. Summary

Phase C implements intercepted browser download management, deterministic file mapping via `tools/flowname.py`, unmatched file isolation, and robust failure recovery. Downloads are tracked by submission order and attempt IDs. Real downloads are intercepted without touching the user's `Downloads` directory or saving `<img src>` previews. Transient Flow errors trigger an end-of-batch tab refresh; genuine failures queue for up to 2 end-of-run resubmits; late/duplicate arrivals are saved with `_alt` suffixes without overwriting; and 3 consecutive failures trigger a rate-limit cooldown.

## 2. Rules

- **R1** Download interception & project target: The runner intercepts Playwright `page.expect_download()` events initiated by clicking the live Flow download button. The download stream is written directly into `images/refs/<KIND>/` or `images/scenes/` under the resolved `[OUTPUT NAME]` formatted via `tools/flowname.py`. Saving `<img src="...">` previews is strictly rejected. Writing into `~/Downloads` is forbidden.
- **R2** Unmatched manifest isolation: If an intercepted download cannot be definitively correlated with an active submission attempt ID or output name, the file is moved to `images/_unmatched/<filename>` and logged in `images/_unmatched/manifest.json` (timestamp, original filename, bytes, attempt context) for later manual review or vision matching.
- **R3** Suspicious failure handling & end-of-batch refresh: If Flow displays a transient or suspicious generation failure banner, the runner does not mark the item permanently failed immediately. At the completion of the active 10-item batch, the runner refreshes the Flow tab and verifies whether the tile actually rendered successfully before determining the item's outcome.
- **R4** End-of-run resubmit queue: Real failures confirmed after the batch refresh are appended to an end-of-run resubmit queue. Resubmission re-types the prompt and re-attaches references by name (per Phase B rules). A maximum of 2 retry attempts is permitted per item. If generation fails after 2 resubmissions, status in `.kit/flow-state.json` is marked `failed`.
- **R5** Duplicate & late arrival preservation (`_alt`): If an image arrives late or a duplicate file is downloaded for an already populated output name, existing files are NEVER overwritten or renamed. The new image is stored alongside with an `_alt` suffix (e.g. `IMG005_alt.png` or `IMG005_alt2.png`).
- **R6** Consecutive failure cooldown: If 3 consecutive submissions fail, the runner assumes provider rate-limiting or quota depletion, pausing execution for a long cooldown period (minimum 300 seconds) and logging an advisory in `.kit/flow-state.json`.
- **R7** Zero LLM calls. No chat or completion model invocations inside `flow_sync.py`.
- **R8** Privacy & Security: No secrets, cookies, or credentials logged.
- **R9** File safety: Existing files never renamed. `ENGINE.txt` untouched.

## 3. Data

- `.kit/flow-state.json` update schema:
  ```json
  {
    "schemaVersion": 2,
    "items": {
      "IMG002": {
        "output_name": "IMG002",
        "attempt_id": "att_002_1",
        "status": "done",
        "retries_count": 1,
        "saved_path": "images/scenes/IMG002-exterior.png",
        "completed_at": "2026-11-28T10:20:00Z"
      }
    }
  }
  ```
- `images/_unmatched/manifest.json`:
  ```json
  [
    {
      "filename": "Flow_20261128_unmatched_1.png",
      "timestamp": "2026-11-28T10:20:05Z",
      "size_bytes": 1048576,
      "candidate_attempt_id": "att_002_1"
    }
  ]
  ```

## 4. API / Logic

CLI invocation:
```bash
python tools/flow_sync.py --mode download [--max-retries 2] [--unmatched-dir images/_unmatched]
```
Note: `--download` is supported as a shorthand CLI flag alias for `--mode download`.

## 5. Screens

Console output:
- Intercepted download path confirmation
- Unmatched file isolation notice
- End-of-batch refresh notice and reconciliation result
- Retry queue execution summary (items retried, success vs `failed`)
- Long cooldown notification when 3 consecutive errors occur

## 6. Files to create or change

- `tools/flow_sync.py` — Add download interception, retry queue, batch refresh, and cooldown logic
- `tools/flowname.py` — Ensure helper formatting matches output names and handles `_alt` suffixes
- `tools/tests/test_flow_download_retries.py` — Unit tests for attempt matching, unmatched manifest generation, duplicate naming, retry capping, and cooldown trigger

## 7. Edge cases

- Flow shows failure message but image download button is still active: end-of-batch refresh clarifies truth.
- Both original and retry produce downloads: both kept (`original` and `_alt`).
- Network disconnect during download: item queued for retry, partial bytes discarded.
- Unmatched directory does not exist: automatically created on first unmatched file.

## 8. Acceptance run

```bash
python -m unittest tools/tests/test_flow_download_retries.py
```

## Acceptance criteria

- **Must happen:** Downloads intercepted via browser event; target paths follow `flowname.py`; uncertain files isolated in `images/_unmatched/`; false errors resolved via end-of-batch refresh; retries capped at 2; duplicates saved with `_alt`; 3 consecutive errors trigger 300s+ cooldown.
- **Must not happen:** Saving `<img>` preview data URI or low-res WebP; dropping files into user `Downloads`; deleting or renaming existing images; exceeding 2 retries; calling LLM APIs; altering `ENGINE.txt`.
- **Done when:** Unit tests pass, and runner demonstrates end-of-batch refresh recovery, retry capping, and safe `_alt` duplicate handling.

## Documentation Impact

- none — internal tool module.

## Open Questions

- none

## Decisions

- End-of-batch refresh for false failures. Because Flow UI frequently flashes false-negative banners while internal rendering succeeds.
- Non-destructive `_alt` naming for duplicates. Because human storyboard artists should decide which generated version to keep or pick.
