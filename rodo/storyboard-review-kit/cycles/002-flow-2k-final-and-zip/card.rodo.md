---
schemaVersion: 2
title: "ارتقا و جایگزینی کیفیت ۲K تصاویر تاییدشده و مدیریت خودکار زیپ در Flow"
status: todo
priority: medium
workflow: major
members: []
scope:
  allowed:
    - "گسترش tools/flow_sync.py با --mode final"
    - "خواندن pick: از story.txt و وضعیت از .kit/flow-state.json"
    - "دانلود ۲K فقط برای تصاویر تأییدشده‌ای که هنوز فایل ۲K معتبر ندارند"
    - "باز کردن زیپ چندتصویری و نگاشت به [OUTPUT NAME] / IMG###"
    - "نوشتن فایل _2K کنار پیش‌نویس ۱K، بدون تغییر نام فایل موجود"
  forbidden:
    - "ارتقای ۲K برای تصویر تأییدنشده"
    - "قبول پیش‌نمایش WebP به‌عنوان فایل ۲K"
    - "تغییر نام یا حذف پیش‌نویس ۱K قبل از تأیید فایل ۲K"
    - "درخواست به مدل زبانی یا ثبت راز در مخزن"
    - "رها کردن زیپ یا فایل در Downloads و تکیه بر watch.py"
    - "بازنویسی فایل نسخه‌ای با rid متفاوت"
---

بعد از تأیید تصویر در صفحهٔ بررسی، یک دستور فقط همان تصویرهای تأییدشده را در Flow به کیفیت بالاتر می‌برد، فایل را مستقیم می‌گیرد (حتی اگر چند تصویر در یک زیپ باشد)، و نسخهٔ باکیفیت را کنار پیش‌نویس می‌گذارد. تصویر تأییدنشده دست نمی‌خورد.

## Progress notes

- Updated: 2026-11-27
- Done: هنوز شروع نشده
- Remaining: همهٔ قدم‌ها

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/002-flow-2k-final-and-zip/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/002-flow-2k-final-and-zip/spec.md)
- [طرح معماری](/rodo/storyboard-review-kit/cycles/002-flow-2k-final-and-zip/design.md)
- [سناریوهای پذیرش](/rodo/storyboard-review-kit/cycles/002-flow-2k-final-and-zip/acceptance.feature)
- [چرخهٔ پیش‌نویس ۱K](/rodo/storyboard-review-kit/cycles/001-flow-cdp-draft-sync/simple.md)

## Checklist: قدم‌ها

- [ ] صف `--mode final` فقط از تصاویر با `pick:` و بدون فایل ۲K معتبر ساخته می‌شود
- [ ] دانلود مرورگر (تک‌فایل یا زیپ چندتصویری) گرفته، استخراج و به `[OUTPUT NAME]` / `IMG###` نگاشته می‌شود
- [ ] فایل ۲K از نظر ظرف و ابعاد واقعی بررسی می‌شود؛ پیش‌نمایش WebP رد می‌شود و پیش‌نویس ۱K تا تأیید ۲K سر جایش می‌ماند
- [ ] `flow-state.json` به‌روز می‌شود و CLI واحد `tools/flow_sync.py --mode draft|final` بدون مصرف مدل زبانی کار می‌کند
- [ ] تمیزکاری انجام شد؛ تست و رسیدگی به خطا حفظ شد (clean.md)
- [ ] تست پذیرش پاس شد
