# 016 — Phase D: Review kit UI panel and self-healing selector diagnosis: technical spec

> Source of truth for the coder. Written in English for technical clarity.
> Every rule has a bold ID (**R1**, **R2** ...). Scenarios in `acceptance.feature` are tagged with `@R1`, `@R2`, etc.

## 1. Summary

Phase D integrates Flow automation directly into the storyboard review web UI. The top menu `⋯` gains an entry 'ساخت با Flow' opening an interactive dashboard. The dashboard provides controls to spawn Chrome with `--remote-debugging-port=9222` and a persistent user profile, trigger jobs via `tools/jobs.py`, stream live progress, and manage individual failed resubmits. In case of unexpected selector breakage, the system pauses execution and writes self-healing diagnostics into `.kit/flow-errors/<timestamp>/`, allowing an external AI or operator to patch `tools/flow_selectors.json` and resume without losing run state.

## 2. Rules

- **R1** Review UI entry point: The top `⋯` options menu in `review.html` exposes an action titled "ساخت با Flow". Clicking it opens a dedicated panel with controls: "Open Chrome", "Start", "Stop / Resume", live progress bar, and failed items queue. Frontend JS files must remain strictly under 700 lines.
- **R2** Chrome orchestration: The server backend (`tools/serve.py`) provides an endpoint (e.g. `/api/flow/launch-chrome`) that launches Google Chrome with `--remote-debugging-port=9222` and `--user-data-dir=<profile_path>/flow-chrome-profile`. The browser persists session credentials across launches so login occurs only once.
- **R3** Background job management: Clicking "Start" initiates generation execution in the background managed by `tools/jobs.py`. The UI polls `/api/job/<id>` to display real-time metrics: active batch, percent complete, step elapsed time, and item status.
- **R4** Pause, resume, and item resend: The user can pause (Stop) and unpause (Resume) the active job. Any item flagged as `failed` appears in a retry list with an individual "resend" button to re-dispatch that item without restarting the entire queue.
- **R5** Self-healing diagnostics snapshot: When a DOM interaction or selector step fails during generation, `flow_sync.py` automatically pauses and exports a complete diagnostic bundle into `.kit/flow-errors/<timestamp>/`:
  - `step.json`: metadata including failing step name, target selector key, attempt ID, and timestamp.
  - `screenshot.png`: full viewport snapshot at failure instant.
  - `dom.html`: DOM snippet centered on the relevant parent container.
- **R6** Safe self-healing patch contract: An external AI agent or human may inspect the diagnostic bundle and update ONLY `tools/flow_selectors.json`. Modifying Python source code during self-healing is strictly forbidden. Resuming the job reloads `tools/flow_selectors.json` and retries the paused step immediately.
- **R7** Zero LLM calls inside `flow_sync.py` and the local server backend.
- **R8** Privacy & Security: The diagnostic DOM snippet and screenshot must sanitize sensitive user information; cookies, auth headers, and session tokens are strictly excluded from exported diagnostics.
- **R9** File safety: Existing image files are never renamed. `ENGINE.txt` is untouched until production promotion.

## 3. Data

- Diagnostic directory structure:
  ```text
  .kit/flow-errors/20261128T102500/
  ├── step.json
  ├── screenshot.png
  └── dom.html
  ```
- `step.json` schema:
  ```json
  {
    "timestamp": "2026-11-28T10:25:00Z",
    "step": "open_ingredients",
    "selector_key": "ingredients_button",
    "attempted_selector": "button[aria-label=\"Add ingredients to the prompt box\"]",
    "item_output_name": "IMG007",
    "attempt_id": "att_007_1"
  }
  ```

## 4. API / Logic

Endpoints added to `tools/serve.py`:
- `POST /api/flow/launch-chrome`: Spawns Chrome on port 9222 with separate profile.
- `POST /api/flow/start`: Triggers `flow_sync` background job via `jobs.py`.
- `POST /api/flow/pause`: Requests pause of active job.
- `POST /api/flow/resume`: Resumes paused job (reloading selectors).
- `POST /api/flow/resend`: Resends a specific failed item.

## 5. Screens

Modal panel "ساخت با Flow":
- Header with close button
- Chrome status badge (Connected / Disconnected) + "Open Chrome" button
- Start / Pause / Resume action buttons
- Progress meter: `Batch 2/4 | 14/36 images generated (38%)`
- Failed items table with "Resend" button per row
- Error notification badge with link to diagnostic timestamp if self-heal paused

## 6. Files to create or change

- `tools/serve.py` — Add `/api/flow/*` endpoints
- `tools/ui/flow_panel.js` (or split module under 700 lines) — Frontend modal logic
- `tools/flow_sync.py` — Pause/resume signals and diagnostic dumping
- `tools/tests/test_flow_panel_api.py` — Unit tests for API endpoints and diagnostic dump format

## 7. Edge cases

- Chrome executable not in standard OS PATH: return helpful diagnostic message in UI rather than silent server crash.
- User clicks "Resume" without updating selectors: tool retries the step; if still failing, pauses again without creating infinite error folders (cooldown limit on diagnostic folders).
- Job terminated while paused: `.kit/flow-state.json` retains pending state for clean recovery on next launch.

## 8. Acceptance run

```bash
python -m unittest tools/tests/test_flow_panel_api.py
```

## Acceptance criteria

- **Must happen:** UI panel accessible from top `⋯` menu; Chrome launchable on 9222 with dedicated profile; jobs executed in background with live progress updates; failed items individually re-sendable; step failures export diagnostic package; resuming reloads updated `flow_selectors.json`.
- **Must not happen:** LLM calls initiated by backend; JS files exceeding 700 lines; secrets dumped in DOM/screenshot artifacts; Python source altered by self-healing routines; modifying `ENGINE.txt`.
- **Done when:** Unit tests pass, and manual test validates opening Chrome, starting a job via the UI, receiving progress updates, and dumping diagnostics on deliberate selector mismatch.

## Documentation Impact

- none — internal feature.

## Open Questions

- none

## Decisions

- Diagnostics dumped to `.kit/flow-errors/` with selector isolation. Because AI agents can easily fix a structured JSON file without risking subtle bugs in executable Python code.
- Persistent separate Chrome profile. Because users should log in to Google once and not need credentials injected into the automation code.
