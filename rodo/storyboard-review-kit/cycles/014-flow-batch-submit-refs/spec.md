# 014 — Phase B: Batch prompt submission and reference attachment by name: technical spec

> Source of truth for the coder. Written in English for technical clarity.
> Every rule has a bold ID (**R1**, **R2** ...). Scenarios in `acceptance.feature` are tagged with `@R1`, `@R2`, etc.

## 1. Summary

Phase B handles prompt dispatch and reference ingredient attachment inside Google Flow via Playwright. Instead of native file uploads, references are attached by name through the UI's ingredient search flow. Prompts are submitted in batches of 10 with 3–8 second randomized jitter between items, event-driven waits for generation tile readiness (no artificial sleeps), 30–90 second inter-batch pauses, and a configurable daily submission limit.

## 2. Rules

- **R1** References attached BY NAME (not file upload): Prompts referencing characters, locations, or styles (`[REFS TO ATTACH:]` or inline tokens) are typed in segments into the prompt box. At each reference point, the runner clicks `flow_selectors.json["ingredients_button"]` (`button[aria-label="Add ingredients to the prompt box"]`), inputs the exact reference name into the search field, presses `Enter` to attach the ingredient, and resumes typing the remaining prompt segment. The native file picker / OS file chooser is NEVER triggered.
- **R2** Batch submission with jitter: Generation requests are grouped into batches of up to 10 items. Between consecutive submissions within the same batch, the runner introduces a randomized jitter between 3.0 and 8.0 seconds to emulate natural human behavior and prevent immediate spam filtering.
- **R3** Inter-batch pause & batch wait: The runner waits for all items in the active 10-item batch before starting the next batch. Between consecutive batches, a randomized pause of 30 to 90 seconds is enforced.
- **R4** Configurable daily cap: A parameter `--daily-cap <N>` (default: 100) limits total generation submissions within a rolling 24-hour window. If reached, the run stops cleanly, logging remaining items as pending in `.kit/flow-state.json`.
- **R5** Event-based completion waits: The runner detects completion of image generation using DOM mutation / tile status events or network responses rather than static sleep timers. Once the UI shows the resulting tile is generated (observed in ~10–15s), the runner proceeds immediately.
- **R6** State tracking: After each submit, `.kit/flow-state.json` updates the item with `status: "submitted"`, `batch_index`, `submitted_at`, and current `attempt_id`.
- **R7** Zero LLM calls. No chat or completion model invocations inside `flow_sync.py`.
- **R8** Privacy & Security: No secrets, cookies, or credentials logged.
- **R9** File safety: Existing image files are never renamed. `ENGINE.txt` is untouched.

## 3. Data

- `tools/flow_selectors.json` additions:
  - `ingredients_button`: selector for opening ingredient dialog
  - `ingredient_search_input`: selector for searching ingredients
  - `result_tile`: selector for generated image card/tile
- `.kit/flow-state.json`:
  ```json
  {
    "schemaVersion": 2,
    "daily_submitted_count": 10,
    "last_batch_at": "2026-11-28T10:15:00Z",
    "items": {
      "IMG001": {
        "output_name": "IMG001",
        "attempt_id": "att_001_1",
        "status": "submitted",
        "batch_id": 1,
        "submitted_at": "2026-11-28T10:15:05Z"
      }
    }
  }
  ```

## 4. API / Logic

CLI invocation:
```bash
python tools/flow_sync.py --mode submit [--batch-size 10] [--daily-cap 100] [--only NAME]
```

## 5. Screens

Console output:
- Active batch progress (e.g. `Batch 1/3: Item 3/10 (IMG003) submitted with ref [CH_NIBBLES]`)
- Jitter and pause countdowns
- Event-wait elapsed timings
- Daily quota remaining

## 6. Files to create or change

- `tools/flow_sync.py` — Implement batch loop, prompt typing with reference search, event-wait logic
- `tools/flow_selectors.json` — Add ingredient and tile selectors
- `tools/tests/test_flow_batch_submit.py` — Unit tests for prompt segmentation, jitter calculation, batch chunking, and cap checks

## 7. Edge cases

- Ingredient search returns no results for a referenced name: log warning, mark item as `ref_not_found`, and do not submit a broken prompt.
- Generation tile takes longer than timeout (e.g. 120s): mark attempt as timed out and move to next batch item without crashing the session.
- Daily cap reached mid-batch: finish active batch item gracefully, persist queue state, exit 0.

## 8. Acceptance run

```bash
python -m unittest tools/tests/test_flow_batch_submit.py
```

## Acceptance criteria

- **Must happen:** Prompt segments typed sequentially; references attached by searching name and pressing Enter; 3–8s jitter between submissions; 30–90s pause between 10-item batches; event-based detection when generation completes.
- **Must not happen:** Native file upload dialog opened; fixed 60s+ sleeps while generation tile is already rendered; exceeding daily cap; LLM calls made; `ENGINE.txt` altered.
- **Done when:** Unit tests pass, and live runner attaches a reference by name, submits a batch of items with jitter, and detects completion via events.

## Documentation Impact

- none — internal tool capability.

## Open Questions

- none

## Decisions

- References attached by typing name into ingredient search rather than file upload. Because Flow already indexes project ingredients, and manual file upload dialogs are fragile across platforms.
- Event-based completion waits instead of fixed sleeps. Because user observed image generation in ~10s, and fixed sleeps wasted minutes per batch.
