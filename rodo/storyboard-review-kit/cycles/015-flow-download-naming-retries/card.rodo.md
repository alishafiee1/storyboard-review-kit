---
schemaVersion: 2
title: "Phase C: Intercepted downloads, output naming, and resilient retries"
status: todo
priority: medium
workflow: standard
members: []
scope:
  allowed:
    - "رهگیری دانلود مرورگر و ذخیرهٔ فایل با نام [OUTPUT NAME] از طریق tools/flowname.py"
    - "انتقال تصاویر نامشخص به images/_unmatched/ همراه با فایل مانیفست"
    - "مدیریت خطاهای مشکوک با رفرش صفحه در انتهای بسته و بررسی مجدد"
    - "صف بازآزمایی (resubmit queue) در پایان اجرا با حداکثر ۲ بار تلاش مجدد"
    - "ذخیرهٔ تصاویر دیررس یا تکراری با پسوند _alt بدون حذف فایل قبلی"
    - "مکث طولانی (cooldown) پس از ۳ خطای متوالی (احتمال محدودیت نرخ)"
  forbidden:
    - "ذخیره کردن تگ <img> پیش‌نمایش به‌جای دانلود واقعی"
    - "نوشتن فایل در پوشهٔ Downloads یا تداخل با tools/watch.py"
    - "تغییر نام یا بازنویسی فایل تصاویر تأییدشده یا موجود قبلی"
    - "تلاش مجدد بیش از ۲ بار برای هر آیتم"
    - "استفاده از مدل زبانی (LLM) درون flow_sync"
    - "دستکاری ENGINE.txt"
---

رهگیری رویداد واقعی دانلود مرورگر در Google Flow و ذخیرهٔ مستقیم تصاویر با نام استاندارد پروژه با استفاده از `tools/flowname.py`. مدیریت حرفه‌ای خطاها شامل رفرش در پایان بسته برای خطاهای کاذب، صف تلاش مجدد در پایان اجرا (حداکثر ۲ بار)، ذخیرهٔ ایمن فایل‌های تکراری با پسوند `_alt`، و استراحت طولانی در صورت خطای متوالی.

## Progress notes

- Updated: 2026-11-28
- Done: هنوز شروع نشده
- Remaining: همهٔ قدم‌ها

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/015-flow-download-naming-retries/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/015-flow-download-naming-retries/spec.md)
- [سناریوهای پذیرش](/rodo/storyboard-review-kit/cycles/015-flow-download-naming-retries/acceptance.feature)

## Checklist: قدم‌ها

- [ ] رهگیری رویداد دانلود مرورگر و ذخیرهٔ مستقیم به مسیر `[OUTPUT NAME]` با قوانین `flowname.py`
- [ ] جداسازی خروجی‌های نامشخص و ذخیره در `images/_unmatched/` همراه با `manifest.json`
- [ ] رسیدگی به خطاهای مشکوک با رفرش در پایان هر بسته و اعتبارسنجی مجدد
- [ ] پیاده‌سازی صف بازآزمایی در پایان اجرا (تایپ مجدد پرامپت و مرجع‌ها، حداکثر ۲ بار)
- [ ] ذخیرهٔ تصاویر دیررس یا تکراری با پسوند `_alt` بدون حذف هیچ فایلی
- [ ] اعمال استراحت طولانی (cooldown) پس از ۳ خطای پشت‌سرهم (احتمال rate limit)
- [ ] تمیزکاری انجام شد؛ تست و رسیدگی به خطا حفظ شد (clean.md)
- [ ] تست پذیرش پاس شد
