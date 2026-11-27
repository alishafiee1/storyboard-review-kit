---
schemaVersion: 2
title: "Phase 7: References mode with BOOK_RULES and separate history"
status: done
priority: medium
members: []
scope:
  allowed: []
  forbidden: []
---

Complete references mode support: `book = "story" | "refs"`, centralized `BOOK_RULES` in kitcore, dedicated `.kit/history-refs/`, backward-compatible `scan_images`, shared speakers, and scoped `scene-00` guards.

## Progress notes

- Updated: 2026-11-27
- Done: BOOK_RULES, scenario/reference.txt, history-refs, shared speakers, and tests complete.
- Remaining: none

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/010-references-mode/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/010-references-mode/spec.md)

## Checklist: قدم‌ها

- [x] تعریف BOOK_RULES در kitcore برای تفکیک story و refs
- [x] پشتیبانی از فایل scenario/reference.txt و پوشهٔ تاریخچهٔ .kit/history-refs/
- [x] حفظ سازگاری پس‌رو در scan_images، اشتراک گوینده‌ها و محدودسازی scene-00 به story
