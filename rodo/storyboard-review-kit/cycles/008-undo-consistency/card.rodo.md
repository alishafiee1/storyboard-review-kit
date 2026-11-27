---
schemaVersion: 2
title: "Phase 5: Reversible set-aside and gallery bulk actions"
status: done
priority: medium
members: []
scope:
  allowed: []
  forbidden: []
---

Snapshotting `/api/image` on `off: yes`, atomic snapshotted `/api/imagebulk` for gallery bulk operations, and full undo support with Ctrl+Z.

## Progress notes

- Updated: 2026-11-27
- Done: Undo snapshots for set-aside and /api/imagebulk implemented and verified.
- Remaining: none

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/008-undo-consistency/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/008-undo-consistency/spec.md)

## Checklist: قدم‌ها

- [x] ایجاد اسنپ‌شات پیش از کنار گذاشتن تصویر (off: yes)
- [x] پیاده‌سازی اندپوینت اتمیک /api/imagebulk برای عملیات گروهی در گالری
- [x] قابلیت برگشت بایت‌به‌بایت با Ctrl+Z برای تغییرات کنار گذاشتن و گروهی
