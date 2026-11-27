# 001 — اتوماسیون ساخت و دانلود پیش‌نویس ۱K از گوگل Flow با Playwright CDP: technical spec

> Source of truth for the coder. Written for this project in Persian, with technical identifiers in English code spans. Anything not here is not expected.
> Every rule has a bold ID (**R1**, **R2** ...). If the card has scenarios, tag each scenario with the rules it proves (`@R1`) and try to cover every rule.

## 1. Summary

Add `tools/flow_sync.py --mode draft` that attaches to the user's already-open Google Flow Chrome via Playwright CDP, generates missing or stale image prompts from `prompts/prompts.txt`, and saves verified 1K drafts straight into `images/refs/` and `images/scenes/`. Approved or unchanged images are never regenerated. `--dry-run` checks selectors and the queue and never clicks Generate. No LLM APIs.

## 2. Rules

- **R1** The tool connects with Playwright `connect_over_cdp("http://127.0.0.1:9222")` to a Chrome started with `--remote-debugging-port=9222` and a separate profile (`C:\Users\alish\flow-chrome-profile` on Ali's machine, or the documented equivalent). It does not launch a second hidden browser and does not use `playwright install` browsers for this path.
- **R2** It finds the open tab whose URL contains `flow.google.com/project/` (also accept `labs.google` if that still appears). If none is found, it lists open tab titles/URLs and exits with a clear message. It does not read cookies, tokens, `localStorage`, or input values into logs or repo files.
- **R3** Verified live selectors (27 Nov 2026, project `https://flow.google.com/project/794c80ef-397e-42d4-9b87-bd66a0cd6ae2`, title `Google Flow – Nov 19 - 21:13`) must be used, and any change must be documented if Flow's UI shifts:
  - prompt: `div[role="textbox"][aria-label="What do you want to create?"]` (`contenteditable="true"`)
  - submit: `button[aria-label="Start generation"]` (disabled while the prompt is empty)
  - reference upload: `button[aria-label="Add ingredients to the prompt box"]` → `Upload media` (Playwright file chooser; no `input[type="file"]` in the DOM) → `Add to prompt`
  - image settings under Agent settings → Image defaults: model **Nano Banana 2.1**, aspect `flow-toggles[aria-label="Aspect ratio"]` radio **16:9**, outputs `flow-toggles[aria-label="Number of outputs"]` (prefer `x1` for drafts unless the user passes another count)
- **R4** `prompts/prompts.txt` is parsed in file order: all reference blocks first (`STYLE_ANCHOR`, then `CH_*` / `CAR_*` / `GRP_*` / `LOC_*` / `PROP_*`), then scene blocks (`=== IMG### ===`). Each block uses `[OUTPUT NAME:]` and `[REFS TO ATTACH:]`. Generation order is refs first, then scenes. A scene that lists a missing required ref is skipped and recorded, unless that ref is generated earlier in the same run.
- **R5** The prompt sent to Flow is the English body of the block (the style text plus `SCENE:`), not the `===` / `[OUTPUT NAME:]` / `[REFS TO ATTACH:]` meta lines.
- **R6** Skip (never regenerate) an image when all of these hold: a project file already exists for that output name, its prompt hash in `.kit/flow-state.json` matches the current prompt body, and `story.txt` does not mark `image-stale: yes` for that image. Also skip an image that already has an approved `pick:` and a matching file, unless the prompt hash changed or the file is missing. Missing files are always queued.
- **R7** `--dry-run` verifies CDP, the tab, selectors **R3**, the parsed queue, and skip/generate decisions, and must not click Start generation, must not upload files, and must not change project images.
- **R8** After Generate, the tool must discover and log the live Download / 1K / 2K (or equivalent) controls on the new image. The successful 1K save path is an intercepted browser download (or a clearly identified 1K download control), written directly to `images/refs/<KIND>/` or `images/scenes/` using `[OUTPUT NAME]` and the kit's Flow naming (`flowname.py`). Saving the on-page `<img>` preview is not a successful 1K draft.
- **R9** Known gap from the 27 Nov 2026 test: `STYLE_ANCHOR` and `CH_NIBBLES` both generated, and the second used the first as a reference successfully, but files were saved via the `<img>` fallback as **1376×768 WebP** bytes with a `.png` extension (STYLE_ANCHOR at 16:52, CH_NIBBLES at 16:57). This cycle must close that gap: capture the real download/1K controls and reject a WebP preview presented as a finished 1K file (wrong container or only-preview resolution).
- **R10** Downloads are never written into the user's `Downloads` folder. This avoids racing `tools/watch.py` (which cuts known Flow names from Downloads into the project). Do not start a second watcher. If a file were left in Downloads, `watch.py` could move it; that must not be the designed path.
- **R11** Pace requests to respect Flow rate limits (configurable delay between generates; default conservative). A run must be resumable from `.kit/flow-state.json` (queue position, hashes, last error, completed output names).
- **R12** The CLI is `python tools/flow_sync.py --mode draft` (and `--dry-run`). Cycle 002 adds `--mode final` on the same tool. The process uses zero LLM tokens: no OpenRouter or other chat/completion calls.
- **R13** Existing image files are never renamed. Secrets, cookies, and profile paths with credentials are not written under `rodo/` or committed.

## 3. Data

- `.kit/flow-state.json` (project-local, not an engine file): prompt hash per output name, status (`pending` / `done` / `skipped` / `error`), timestamps, last observed download-control labels, output path, and a schema version.
- Prompt hash: stable hash of the exact English prompt body sent to Flow (**R5**).
- Output paths: refs under `images/refs/<KIND>/` (`STYLE`, `CH`, `CAR`, `GRP`, `LOC`, `PROP`); scenes under `images/scenes/` (or the project's existing batch subfolder only if the kit already uses one for that id). Names must be parseable by `flowname.py`.

## 4. API / logic

No new HTTP API is required for this cycle. The CLI may be invoked while `tools/serve.py` is running; it must not break the file lock used by the write API. It only appends/updates `.kit/flow-state.json` and writes new image files.

CLI outline:

```text
python tools/flow_sync.py --mode draft [--dry-run] [--only NAME] [--limit N]
```

Exit `0` if the run (or dry-run) completed with no failed generates; non-zero on CDP failure, missing tab, or failed saves. Print a short queue summary.

## 5. Screens

No change to `review.html` in this cycle, except that new files appearing in `images/` show up on the next project load like any other import.

User-visible CLI messages (Persian is fine) must include: cannot reach port 9222; no Flow project tab; skipped because unchanged/approved; waiting for generation; saved path; rejected preview file; missing required ref.

## 6. Files to create or change

- `tools/flow_sync.py` — new CLI (draft mode)
- `.kit/flow-state.json` — created at runtime in the user project (not vendored in this repo)
- tests under `tools/tests/` for prompt parsing, skip rules, and hash behaviour (no live Flow calls in unit tests)
- this cycle's docs only; no change to `ENGINE.txt` until the script is stable enough to ship with `update.py` (that shipping step can be the last checklist item or a follow-up if preferred: if added to the engine, list it in `ENGINE.txt`)

## 7. Edge cases

- Chrome open but Flow tab not loaded or still on a login page: stop and say so; do not type credentials.
- Start generation stays disabled after fill: fail that item, do not loop forever.
- Required ref missing: skip the dependent image, continue others, non-zero only if any required item failed.
- Interrupted run: resume without repeating `done` hashes.
- `image-stale: yes` even if hash would match: queue it; after a successful verified save, the coder may clear the stale flag only with the same line-edit care as the rest of the kit (do not rewrite unrelated `story.txt` lines). If clearing stale is deferred, document it as an open follow-up rather than silently editing the scenario.
- Several outputs (`x2` default in the live UI): draft mode should set or use `x1` unless overridden, so one file maps to one `[OUTPUT NAME]`.

## 8. Acceptance run (if the card has scenarios)

Optional. `rodo test` (the card's `test.command`, or `testCommand` from `project.json` with `{NNN}` = `001`). Unit tests must not call Flow. Live checks are manual/`--dry-run` until a safe fixture exists.

## Acceptance criteria

- **Must happen:** `--dry-run` reports the verified selectors and a correct skip/generate queue; a real draft run saves a verified 1K file to the project image folders; approved and unchanged images are not regenerated; refs generate before scenes; runs are resumable; no LLM calls.
- **Must not happen:** Generate during `--dry-run`; WebP `<img>` preview accepted as success (**R9**); files dropped in Downloads; secrets in git; rename of existing images; regeneration of approved/unchanged pictures.
- **Done when:** unit tests for parse/skip/hash pass, `--dry-run` succeeds on a live tab without Generate, and one supervised live draft save is a real 1K download (not a preview), documented in the cycle progress notes.

## Documentation Impact

- `ARCHITECTURE.md` — one short subsection pointing at `tools/flow_sync.py` and `.kit/flow-state.json` when the code ships
- `README.md` / `README.fa.md` — a short “Flow sync” usage paragraph when the code ships
- `ENGINE.txt` — only if the script is included in `update.py`

## Open Questions

- Exact live labels of the post-generate Download / 1K / 2K controls — default if no answer: discover and log them on the first supervised generate, then pin the selectors in this spec before calling the cycle done
- Whether a successful draft should clear `image-stale: yes` in `story.txt` automatically — default if no answer: do not edit `story.txt` in cycle 001; only record state in `flow-state.json`

## Decisions

- Direct CDP to the user's Chrome, not a bundled browser. Because the user must already be signed into Flow and a separate debug profile was already proven.
- Skip approved/unchanged images by prompt hash + `image-stale` + missing-file checks. Because remaking confirmed pictures wastes credits and risks overwriting work.
- Never use the Downloads folder as a drop target. Because `watch.py` already owns that path.
