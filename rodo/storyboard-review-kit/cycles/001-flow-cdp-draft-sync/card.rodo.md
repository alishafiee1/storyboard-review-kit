---
schemaVersion: 2
title: "اتوماسیون ساخت و دانلود پیش‌نویس ۱K از گوگل Flow با Playwright CDP"
status: todo
priority: medium
workflow: major
members: []
scope:
  allowed:
    - "ابزار جدید tools/flow_sync.py با --mode draft و --dry-run"
    - "پروندهٔ وضعیت .kit/flow-state.json"
    - "خواندن scenario/story.txt و prompts/prompts.txt (بدون پاک کردن انتخاب‌ها)"
    - "نوشتن پیش‌نویس ۱K فقط در images/refs/ و images/scenes/"
    - "اتصال به Chrome باز کاربر روی درگاه 9222"
  forbidden:
    - "کلیک Generate در حالت --dry-run"
    - "ساخت دوبارهٔ تصویری که پرامپت آن عوض نشده و فایل دارد، یا انتخاب‌شده است"
    - "ذخیره در Downloads یا تداخل با tools/watch.py"
    - "قبول پیش‌نمایش WebP به‌جای دانلود واقعی ۱K به‌عنوان خروجی موفق"
    - "درخواست به مدل زبانی یا ثبت راز و کوکی در مخزن"
    - "تغییر نام فایل تصویر موجود یا دست زدن به پروژه‌های دیگر"
---

با یک دستور، فقط تصویرهایی که لازم‌اند از Flow ساخته می‌شوند و پیش‌نویس با کیفیت پایه مستقیم در پوشهٔ پروژه ذخیره می‌شود. تصویرهایی که عوض نشده‌اند یا تأیید شده‌اند دوباره ساخته نمی‌شوند. می‌توان اول یک اجرای آزمایشی بدون ساخت تصویر گرفت.

## Progress notes

- Updated: 2026-11-27
- Done: هنوز شروع نشده
- Remaining: همهٔ قدم‌ها

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/001-flow-cdp-draft-sync/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/001-flow-cdp-draft-sync/spec.md)
- [طرح معماری](/rodo/storyboard-review-kit/cycles/001-flow-cdp-draft-sync/design.md)
- [سناریوهای پذیرش](/rodo/storyboard-review-kit/cycles/001-flow-cdp-draft-sync/acceptance.feature)

## Checklist: قدم‌ها

- [ ] `--dry-run` روی تب زندهٔ Flow انتخابگرهای تأییدشده را پیدا می‌کند و Generate را نمی‌زند
- [ ] صف ساخت از `prompts/prompts.txt` (ابتدا refs، بعد `IMG###`) با `flow-state.json` و `image-stale` درست ساخته می‌شود و موارد تأییدشده یا بدون تغییر کنار گذاشته می‌شوند
- [ ] کنترل‌های واقعی Download / 1K بعد از ساخت یک تصویر ثبت و به مسیر مستقیم پوشهٔ پروژه وصل می‌شوند؛ خروجی موفق WebP پیش‌نمایش نیست
- [ ] آهنگ‌دهی محدودیت نرخ و ازسرگیری کار می‌کند و فایلی در Downloads رها نمی‌شود
- [ ] تمیزکاری انجام شد؛ تست و رسیدگی به خطا حفظ شد (clean.md)
- [ ] تست پذیرش پاس شد
