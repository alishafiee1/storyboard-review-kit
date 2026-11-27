# Technical Spec: 010-references-mode

- **R1:** `BOOK_RULES` in `kitcore.py` centralizes regex, paths, and history directories for `story` and `refs`.
- **R2:** `scan_images(book="story")` retains default argument for backward compatibility.
- **R3:** Global speakers remain in `scenario/story.txt` and are shared across both books.
- **R4:** `scene-00` guard logic strictly checks `book == "story"`.
