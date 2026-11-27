# Technical Spec: 001-foundation-plain-text

- **R1:** Plain-text files (`scenario/story.txt`, `prompts/prompts.txt`) serve as the database.
- **R2:** Edits are performed line-by-line under a file lock with 409 conflict detection for external modifications.
- **R3:** The server binds only to 127.0.0.1 and serves static files without build tools.
