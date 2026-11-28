# 002 — ارتقا و جایگزینی کیفیت ۲K تصاویر تاییدشده و مدیریت خودکار زیپ در Flow: technical spec

> Source of truth for the coder. Written for this project in Persian, with technical identifiers in English code spans. Anything not here is not expected.
> Every rule has a bold ID (**R1**, **R2** ...). If the card has scenarios, tag each scenario with the rules it proves (`@R1`) and try to cover every rule.

## 1. Summary

> **Dependency:** This cycle depends on cycle 016 (Phase D: Review kit UI panel and self-healing).

Extend `tools/flow_sync.py` with `--mode final` so only approved (`pick:`) images that do not yet have a verified 2K file are upscaled/downloaded at 2K from the open Flow tab. Browser downloads are intercepted — both single files and multi-image `.zip` bundles, which are extracted and mapped to the exact `[OUTPUT NAME]` / `IMG###` path. A WebP preview is never accepted as 2K. The 2K file is written as a quality sibling (`_2K`) beside the 1K draft; existing files are not renamed. `.kit/flow-state.json` is updated. Zero LLM tokens.

## 2. Rules

- **R1** `--mode final` is the same CLI as cycle 001: `python tools/flow_sync.py --mode final [--dry-run] [--only NAME]`. It uses the same CDP connection rules as 001 (port `9222`, `flow.google.com/project/`, no bundled browser, no secrets in the repo).
- **R2** The queue is built from `story.txt` and `.kit/flow-state.json`. An image is included only if it has an approved selection (`pick:` on that picture) and it does not already have a verified 2K (or better, `_4K`) file for that same version (`rid` when known, otherwise the approved file's version group in `flowname.py` / `media.py`). Unapproved pictures, stale pictures without a pick, and pictures already at 2K are skipped.
- **R3** This mode must not generate a brand-new image from scratch unless Flow requires opening the existing result to request 2K. It must not remake a 1K draft for an unapproved id. Draft generation stays in `--mode draft`.
- **R4** 2K is obtained through the live Flow download/upscale UI (the exact 2K control labels were not visible before a generate in the 27 Nov 2026 dry-run and must be pinned here once captured in cycle 001 or in the first supervised final run). The successful path is an intercepted browser download, not an on-page `<img>` fetch.
- **R5** If the download is a single image file, it is written to the kit path for that `[OUTPUT NAME]` / `IMG###` with a `_2K` quality suffix parseable by `flowname.py` (same `rid` as the approved version when the name carries one). If the download is a `.zip` (or similar bundle) of several images, the tool extracts it to a temporary directory under `.kit/`, maps each member to the exact output name / `IMG###`, writes each verified file to the project image folders, then deletes the temp bundle. Unmapped members are kept in `.kit/` for inspection and reported, not silently dropped into `images/`.
- **R6** A file is accepted as 2K only after format and dimension checks: a real image container (JPEG/PNG/WebP-as-final only if it is the actual Flow 2K asset and meets the size rule — a preview or a 1376×768 test-fallback is not enough), and pixel size consistent with 2K for 16:9 (significantly larger than the 1K draft; reject if it matches the known preview size **1376×768** from the 27 Nov test, or if the container is a tiny preview). Failed checks leave the 1K draft untouched and record an error in `flow-state.json`.
- **R7** Safe replacement means: the verified `_2K` file is added beside the 1K draft; the existing 1K file is not renamed or deleted in this cycle. `media.resolve()` already prefers 4K, then 2K, then 1K, so the review page and exports will show the 2K once it exists, and `pick:` (the `rid`) stays valid. Never overwrite a file that belongs to a different `rid` / version.
- **R8** `.kit/flow-state.json` is updated with the 2K path, hashes if useful, download type (`file` / `zip`), and status. `--dry-run` prints the final queue and does not click upscale/download and does not write image files.
- **R9** Same anti-conflict rule as 001: do not use the user's `Downloads` folder; do not race `tools/watch.py`. Zip extraction happens inside `.kit/`, then files are moved into `images/refs/` or `images/scenes/`.
- **R10** Zero LLM token usage. No chat or completion APIs.
- **R11** Existing image files are never renamed. Secrets are not committed. `--mode draft` behaviour from cycle 001 stays intact.

## 3. Data

- Inputs: `scenario/story.txt` (`pick:`), `prompts/prompts.txt` (`[OUTPUT NAME:]`), `.kit/flow-state.json`, files already in `images/refs/` and `images/scenes/`.
- Outputs: new `*_2K*` files next to the approved version; updates in `.kit/flow-state.json`; optional log of zip member maps.
- Version identity: `(base, rid)` per `ARCHITECTURE.md` / `flowname.py`. Quality suffix does not create a new version.

## 4. API / logic

No new HTTP API required. CLI:

```text
python tools/flow_sync.py --mode final [--dry-run] [--only NAME]
```

Mapping from zip members: prefer Flow file names that `flowname.parse` understands and that match a queued `[OUTPUT NAME]` or `IMG###`; then slug match (`flowname.slugs_match`) against the prompt output slug; never guess across different bases.

## 5. Screens

No required change to `review.html`. After a 2K file appears, the existing version UI should show the `2K` label and prefer that file for the same `pick:`.

CLI messages must say: not approved so skipped; already has 2K; zip member could not be mapped; rejected because preview/too small; saved `_2K` path.

## 6. Files to create or change

- `tools/flow_sync.py` — add `--mode final` (same file as cycle 001)
- unit tests for queue selection (pick / already-2K / unapproved) and zip mapping
- `ARCHITECTURE.md` and README when the code ships (same as 001, plus 2K / zip)

## 7. Edge cases

- `pick:` points at a `rid` whose 1K file is missing: report and skip; do not invent another version.
- Zip contains a mix of queued and unknown images: write the mapped ones, isolate the rest, non-zero if any queued item is missing from the zip.
- 4K already present: treat as already satisfied (skip 2K).
- Flow only offers a zip for one image: still go through the extract/map path.
- Dimension check uncertain for unusual aspect ratios: compare against that image's 1K file when present (2K must be substantially larger on both sides) and against the 1376×768 preview known from the test.

## 8. Acceptance run (if the card has scenarios)

Optional. `rodo test` with `{NNN}` = `002`. Unit tests must not call Flow. Zip mapping and dimension rejection must be tested with fixtures (including a WebP preview and a fake zip).

## Acceptance criteria

- **Must happen:** only approved images without verified 2K are queued; single-file and zip downloads are intercepted and mapped to the right `IMG###` / `[OUTPUT NAME]`; a verified 2K file appears as a `_2K` sibling; `flow-state.json` is updated; `--dry-run` is safe; no LLM calls.
- **Must not happen:** 2K for an unapproved image; accepting a 1376×768 WebP preview as 2K; renaming or deleting 1K before a verified 2K exists; writing into Downloads; overwriting a different `rid`.
- **Done when:** unit tests for the queue and zip/dimension rules pass, and a supervised live run stores at least one verified 2K file that the review page prefers for the existing `pick:`.

## Documentation Impact

- `ARCHITECTURE.md` — document `--mode final`, zip mapping, and that 2K is a quality sibling
- `README.md` / `README.fa.md` — usage for draft vs final
- none for `story.txt` format

## Open Questions

- Exact 2K / upscale button labels in the live Flow UI — default if no answer: reuse the control log from cycle 001 if captured, otherwise discover on the first supervised `--mode final` run and pin them here
- Whether Flow's 2K asset is JPEG, PNG, or a high-resolution WebP — default if no answer: accept the real downloaded asset after the size check, but still reject the known 1376×768 preview pattern

## Decisions

- 2K only for approved picks. Because higher quality should not be spent on unreviewed drafts.
- Add a `_2K` sibling and do not rename 1K. Because the kit's version model forbids renaming and already prefers the best quality for the same `rid`.
- Zip bundles are extracted and mapped automatically. Because Flow may deliver several images in one download and manual unpacking is error-prone.
