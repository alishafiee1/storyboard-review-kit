---
schemaVersion: 2
title: "Versions, voices/takes, and Flow intake"
status: done
priority: medium
members: []
scope:
  allowed: []
  forbidden: []
---

Support for Flow version naming, stable dialogue line IDs (IMGnnn-k), multi-take audio variants, and the automated Downloads watcher.

## Progress notes

- Updated: 2026-11-27
- Done: Version parser, line IDs, recursive media scans, and watch.py implemented and verified.
- Remaining: none

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/004-versions-voices-intake/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/004-versions-voices-intake/spec.md)

## Checklist: قدم‌ها

- [x] الگوهای تطبیق نسخه با شناسه‌های تصادفی Flow و سطوح کیفیت 2K/4K
- [x] اختصاص شناسه‌های پایدار id: به هر خط دیالوگ و بازنویسی مسیرهای صوتی
- [x] اسکن بازگشتی تصاویر و پیاده‌سازی دیده‌بان watch.py برای پوشهٔ Downloads
