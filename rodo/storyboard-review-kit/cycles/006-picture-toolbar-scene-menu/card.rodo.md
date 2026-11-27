---
schemaVersion: 2
title: "Phase 3: Per-picture toolbar and scene menu"
status: done
priority: medium
members: []
scope:
  allowed: []
  forbidden: []
---

Direct toolbar buttons on each image figure (`figure.shot > .pic-bar`) and an independent scene action menu (`⋯`) next to `.slabel`, removing legacy top bar popover hacks.

## Progress notes

- Updated: 2026-11-27
- Done: Per-picture toolbar and scene menu implemented, tested across single-picture and no-picture blocks.
- Remaining: none

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/006-picture-toolbar-scene-menu/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/006-picture-toolbar-scene-menu/spec.md)

## Checklist: قدم‌ها

- [x] قرار دادن نوار ابزار اقدامات مستقیم روی کادر هر تصویر
- [x] ایجاد منوی ⋯ کنار عنوان صحنه برای عملیات صحنه (حتی در بلوک‌های بدون تصویر)
- [x] حذف دکمهٔ شلوغ بیشتر (#more) از نوار بالا
