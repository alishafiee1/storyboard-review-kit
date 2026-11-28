---
schemaVersion: 2
title: "Phase 4: Line moves and insert bar"
status: done
priority: medium
members: []
scope:
  allowed: []
  forbidden: []
---

Line moving support via `/api/moveline` preserving stable line IDs and voices, drag grip and reorder buttons per line, and unified thin `+` insert bar.

## Progress notes

- Updated: 2026-11-27
- Done: /api/moveline endpoint and UI insert bar implemented and verified with tests.
- Remaining: none

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/009-line-move-and-insert-bar/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/009-line-move-and-insert-bar/spec.md)

## Checklist: قدم‌ها

- [x] پیاده‌سازی اندپوینت /api/moveline با اسنپ‌شات و حفظ شناسه‌های خطوط
- [x] افزودن دستگیرهٔ کشیدن و دکمه‌های بالا/پایین به هر خط متن
- [x] جایگزینی دکمه‌های سه‌گانهٔ افزودن خط با یک نوار باریک + درج
