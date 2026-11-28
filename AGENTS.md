<!-- rodo:start -->
This repo uses the RODO method (kit 2.6.0). Before any work: read `.agents/skills/rodo/SKILL.md`,
run `rodo sync`, then `rodo resume`. At the end of every session run `rodo sync`.
RODO projects: see `rodo/*/project.json`. Never write secrets into rodo files. Never create boards.
Never run `git pull`, `git fetch`, `git merge` or `git rebase`. If the repo is behind, tell the user once.
<!-- rodo:end -->

## Invariants
- Every JavaScript file in `tools/ui/*.js` must stay under 700 lines; split a module before it reaches the limit.
- `ENGINE.txt` is the allow-list that `tools/update.py` copies into storyboard projects. Never add `AGENTS.md`, `CLAUDE.md`, `.agents/`, `rodo/`, tests, or other development docs to it.
- Unit tests: `python -m unittest discover -s tools/tests -p "test_*.py"`
- Browser tests: `python tools/tests/run.py`
- Known pre-existing unit failure (do not "fix" in unrelated work): `test_settings.StarterFolders.test_the_starter_has_the_working_folders_and_no_premiere_folder` (starter `audio/fa`).
