---
schemaVersion: 2
title: "Phase A: Flow sync skeleton, CDP tab discovery, and dry-run queue"
status: done
priority: medium
workflow: standard
members: []
scope:
  allowed:
    - "ابزار جدید tools/flow_sync.py به همراه پرچم --dry-run"
    - "فایل انتخابگرهای Flow در tools/flow_selectors.json"
    - "پروندهٔ وضعیت .kit/flow-state.json با ساختار attempt id"
    - "خواندن scenario/story.txt و prompts/prompts.txt برای صف‌بندی"
    - "اتصال به Chrome کاربر روی 127.0.0.1:9222 و پیدا کردن تب Flow"
    - "تست‌های واحد برای پارس پرامپت، قوانین رد کردن، هش و وضعیت"
  forbidden:
    - "کلیک روی دکمهٔ Generate یا ارسال دستور ساخت به Flow"
    - "افزودن مرجع یا آپلود فایل در صفحه"
    - "استفاده از مدل زبانی (LLM) درون flow_sync"
    - "ذخیره یا لاگ کردن اسرار، کوکی‌ها یا توکن‌ها"
    - "تغییر نام یا بازنویسی فایل تصاویر موجود"
    - "دست زدن به ENGINE.txt قبل از پایداری کامل"
---

اسکلت ابزار خط فرمان `tools/flow_sync.py` با قابلیت اجرای آزمایشی (`--dry-run`). ابزار به کروم کاربر روی درگاه 9222 وصل می‌شود، تب Flow را پیدا کرده و وجود انتخابگرها را بررسی می‌کند. صف تولید بر اساس پرامپت، تصویر تأییدشده و پرچم کهنگی تعیین می‌شود بدون اینکه دکمهٔ Generate فشرده شود.

## Progress notes

- Updated: 2026-11-28
- Done: پیاده‌سازی اسکلت CLI با واردسازی تنبل Playwright، فایل انتخابگرهای JSON، کشف تب Flow روی CDP، منطق صف skip/generate طبق قوانین R5، لاگ زمان‌بندی قدم‌ها و flow-state.json با شناسهٔ تلاش، به همراه ۲۵ آزمون واحد ایزوله.
- Remaining: هیچ (همهٔ R-idهای چرخه 001 پاس شدند).

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/001-flow-sync-skeleton-dryrun/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/001-flow-sync-skeleton-dryrun/spec.md)
- [طرح معماری](/rodo/storyboard-review-kit/cycles/001-flow-sync-skeleton-dryrun/design.md)
- [سناریوهای پذیرش](/rodo/storyboard-review-kit/cycles/001-flow-sync-skeleton-dryrun/acceptance.feature)

## Checklist: قدم‌ها

- [x] ساخت اسکلت CLI ابزار `tools/flow_sync.py` با واردسازی تنبل (lazy import) برای Playwright
- [x] ذخیره و بارگذاری انتخابگرهای Flow از `tools/flow_selectors.json` (داده به‌جای کد)
- [x] اتصال CDP به `127.0.0.1:9222` و یافتن تب فعال `flow.google.com/project/`
- [x] پارس `prompts/prompts.txt` و محاسبهٔ صف skip/generate بر اساس هش پرامپت، `image-stale` و تصویر تأییدشده
- [x] پیاده‌سازی حالت `--dry-run`: بررسی وجود انتخابگرها روی صفحه بدون کلیک Generate
- [x] پیاده‌سازی لاگ زمان‌بندی قدم‌ها و ساختار پروندهٔ وضعیت `.kit/flow-state.json` با attempt id
- [x] آزمون‌های واحد برای پارس، قوانین پرش، هش و ذخیرهٔ وضعیت (بدون نیاز به Playwright زنده)
- [x] تمیزکاری انجام شد؛ تست و رسیدگی به خطا حفظ شد (clean.md)
- [x] تست پذیرش پاس شد
