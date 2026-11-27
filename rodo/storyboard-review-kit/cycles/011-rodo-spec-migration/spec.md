# Technical Spec: 011-rodo-spec-migration

- **R1:** `rodo/storyboard-review-kit/` is the single source of development truth.
- **R2:** Legacy dev-truth files (`ARCHITECTURE.md`, `CHANGELOG.md`, and `docs/redesign/`) are deleted.
- **R3:** Broken links in `README.md`, `README.fa.md`, `docs/index.html`, and `tools/serve.py` are redirected.
- **R4:** `tools/tests/shots.py` writes to `tools/tests/screens/` and no longer depends on deleted redesign files.
- **R5:** `ENGINE.txt` remains strictly free of development documentation.
