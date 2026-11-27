# AGENTS.md

Instructions for AI coding agents working on `storyboard-review-kit`.

## Single Source of Development Truth
- **Start here:** Always read `rodo/storyboard-review-kit/MAP.md` then `rodo/storyboard-review-kit/MEMORY.md` first.
- Detailed specifications, architecture, and current context live in `rodo/storyboard-review-kit/project/*.md` and active/completed cycle cards in `rodo/storyboard-review-kit/cycles/`.
- The `rodo/storyboard-review-kit/` directory is the **only development truth**. Legacy root documentation (`ARCHITECTURE.md`, `CHANGELOG.md`) and `docs/redesign/` have been migrated and removed.

## Core Invariants
- **File line limits:** Every JavaScript file in `tools/ui/*.js` must strictly stay under the 700-line test limit. Split modules if they approach 700 lines.
- **ENGINE.txt boundary:** `ENGINE.txt` is the strict allow-list that `tools/update.py` copies into storyboard projects. **Never** add `AGENTS.md`, `rodo/`, tests, or other development documentation to `ENGINE.txt`.
- **Architecture principles:** Plain-text files (`scenario/story.txt`, `scenario/reference.txt`, `prompts/prompts.txt`) are the database. There is no build step, no frontend framework, and no database engine.
- **Atomic line edits & safety:** Edits to text files are performed line-by-line under file locks with 409 conflict detection. Reversible snapshots are saved to `.kit/history/` (or `.kit/history-refs/`) before structural edits.

## Development Workflow
- **New features:** Every new feature, behavior change, or user-facing adjustment requires a RODO cycle card under `rodo/storyboard-review-kit/cycles/NNN-slug/`.
- **Minor fixes:** Tiny non-behavioral fixes (refactoring, typos, comments) do not need a cycle card; record them in a single line in `rodo/storyboard-review-kit/CHANGELOG.md`.

## Running Tests
Run tests using Python 3:
- Unit tests:
  ```bash
  python -m unittest discover -s tools/tests -p "test_*.py"
  ```
- Browser integration tests (Playwright):
  ```bash
  python tools/tests/run.py
  ```
- **Known pre-existing failure (do NOT fix):**
  `test_settings.StarterFolders.test_the_starter_has_the_working_folders_and_no_premiere_folder`
