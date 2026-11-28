# Technical Spec: 002-versions-voices-intake

- **R1:** Image versions are keyed on `(base, rid)` where rid is the 8-hex Flow suffix; `_4K` replaces `_2K` while retaining approval.
- **R2:** Stable line IDs follow `IMGnnn-k` and audio files follow `audio/<lang>/<id>_<rid>.mp3`.
- **R3:** `watch.py` cuts matching files from Downloads into `images/scenes/bNN/` without overwriting existing files.
