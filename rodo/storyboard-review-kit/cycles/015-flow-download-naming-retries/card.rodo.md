---
schemaVersion: 2
title: "Phase C: Intercepted downloads, output naming, and resilient retries"
status: done
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
- Done: رفع تمام بازخوردهای بازبینی فاز C شامل ذخیره‌سازی اتمیک با O_CREAT|O_EXCL در flow_download بدون رونویسی، پاکسازی ایمپورت‌های بلااستفاده، اعمال سقف قطعی ۲ بازآزمایی بر پایهٔ retries_count در وضعیت، بررسی و طبقه‌بندی مجزای تایل هر آیتم با ثبت وضعیت uncertain برای تایل‌های نامشخص، مستندسازی نام مستعار --download در مشخصات، محدودسازی خطاهای صید شده در _prepare_runner، و افزودن تست‌های واحد اختصاصی.
- Remaining: ندارد (تکمیل شد)
- Verified: unit tests (287 tests, only known starter audio/fa failure), browser tests (71 passed, 0 failed), atomic non-overwriting save, retries_count capping, per-item tile recheck.

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/015-flow-download-naming-retries/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/015-flow-download-naming-retries/spec.md)
- [سناریوهای پذیرش](/rodo/storyboard-review-kit/cycles/015-flow-download-naming-retries/acceptance.feature)

## Checklist: قدم‌ها

- [x] رهگیری رویداد دانلود مرورگر و ذخیرهٔ مستقیم به مسیر `[OUTPUT NAME]` با قوانین `flowname.py`
- [x] جداسازی خروجی‌های نامشخص و ذخیره در `images/_unmatched/` همراه با `manifest.json`
- [x] رسیدگی به خطاهای مشکوک با رفرش در پایان هر بسته و اعتبارسنجی مجدد
- [x] پیاده‌سازی صف بازآزمایی در پایان اجرا (تایپ مجدد پرامپت و مرجع‌ها، حداکثر ۲ بار)
- [x] ذخیرهٔ تصاویر دیررس یا تکراری با پسوند `_alt` بدون حذف هیچ فایلی
- [x] اعمال استراحت طولانی (cooldown) پس از ۳ خطای پشت‌سرهم (احتمال rate limit)
- [x] تمیزکاری انجام شد؛ تست و رسیدگی به خطا حفظ شد (clean.md)
- [x] تست پذیرش پاس شد
