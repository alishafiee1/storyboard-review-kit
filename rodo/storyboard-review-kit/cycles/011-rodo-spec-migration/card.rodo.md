---
schemaVersion: 2
title: "Phase 8: Adopt rodo-spec as single source of dev-truth"
status: done
priority: medium
members: []
scope:
  allowed: []
  forbidden: []
---

Adoption of rodo-spec layout under `rodo/storyboard-review-kit/` as single development truth, deletion of legacy root docs (`ARCHITECTURE.md`, `CHANGELOG.md`, `docs/redesign/`), broken link fixes, and creation of `AGENTS.md`.

## Progress notes

- Updated: 2026-11-27
- Done: rodo-spec layout created, old dev-truth deleted, links and shots.py updated, tests verified.
- Remaining: none

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/011-rodo-spec-migration/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/011-rodo-spec-migration/spec.md)

## Checklist: قدم‌ها

- [x] ایجاد ساختار کامل rodo-spec شامل MAP.md، MEMORY.md، project.json، اسناد پروژه و چرخه‌ها
- [x] ایجاد AGENTS.md برای راهنمایی عامل‌های هوش مصنوعی بدون نیاز به RODO CLI
- [x] حذف اسناد قدیمی ریشه و پوشهٔ docs/redesign/ و اصلاح ارجاعات و مسیرهای اسکرین‌شات
