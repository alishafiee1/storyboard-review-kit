# Technical Spec: 008-undo-consistency

- **R1:** `POST /api/image` triggers a pre-edit snapshot whenever `off` is updated.
- **R2:** `POST /api/imagebulk` applies bulk status/off operations atomically with a single history snapshot.
- **R3:** `Ctrl+Z` reliably restores previous state byte-for-byte via `/api/undo`.
