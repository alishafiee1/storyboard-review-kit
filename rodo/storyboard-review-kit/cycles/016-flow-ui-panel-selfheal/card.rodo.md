---
schemaVersion: 2
title: "Phase D: Review kit UI panel and self-healing selector diagnosis"
status: done
priority: medium
workflow: standard
members: []
scope:
  allowed:
    - "افزودن گزینهٔ 'ساخت با Flow' به منوی سه‌نقطهٔ بالای صفحه (⋯)"
    - "دکمه‌های باز کردن کروم، شروع، توقف/ادامه و فهرست ناموفق‌ها با امکان ارسال مجدد"
    - "اجرای فرآیند پس‌زمینه از طریق tools/jobs.py و نمایش پیشرفت زنده"
    - "فرمان باز کردن کروم از tools/serve.py با پورت 9222 و پروفایل پایدار مجزا"
    - "توقف موقت در صورت بروز خطا و ذخیرهٔ بستهٔ تشخیصی خودترمیمی در .kit/flow-errors/<timestamp>/"
    - "امکان وصله زدن خودکار/دستی فایل tools/flow_selectors.json و ادامهٔ کار"
  forbidden:
    - "درخواست به مدل زبانی (LLM) درون کدهای سرور یا flow_sync"
    - "ذخیره کردن کلمات عبور یا کوکی‌های مرورگر در گزارش خطا"
    - "تغییر فایل‌های پایتون خارج از tools/flow_selectors.json در فرآیند خودترمیمی"
    - "تغییر نام یا بازنویسی فایل تصاویر موجود"
    - "تغییر ENGINE.txt"
    - "افزایش حجم فایل‌های جاوااسکریپت فرانت‌اند به بالای ۷۰۰ خط"
---

افزودن پنل تعاملی «ساخت با Flow» در منوی بالای استوری‌بورد با دکمه‌های اجرای کروم مستقل، شروع و کنترل کار پس‌زمینه، و نوار پیشرفت زنده. پشتیبانی از خودترمیمی انتخابگرها از طریق ذخیرهٔ اسنپ‌شات و خطای DOM در `.kit/flow-errors/<timestamp>/` جهت اصلاح متمرکز `tools/flow_selectors.json` بدون نیاز به دستکاری کد.

## Progress notes

- Updated: 2026-11-28
- Done: پیاده‌سازی کامل R1 تا R9 فاز D و اعمال اصلاحات بازبینی: حلقهٔ بازآزمایی انتخابگر در resume، اجرای مسیر دانلود Phase C و ذخیره در flow-state.json، گارد دکمه‌های pause/resume/start، صف ارسال مجدد، ادغام سلکتورها و رفع dedupe تشخیصی، پاکسازی داده‌های حساس و هندلینگ ۴۰۴.
- Remaining: هیچ (کامل شد)
- Verified: واحد (۳۰۹ آزمون پاس، ۱ شکست از قبل شناخته‌شده starter audio/fa)، مرورگر (۷۲ آزمون پاس، ۰ شکست)

## Refs

- [توضیح ساده](/rodo/storyboard-review-kit/cycles/016-flow-ui-panel-selfheal/simple.md)
- [سند فنی](/rodo/storyboard-review-kit/cycles/016-flow-ui-panel-selfheal/spec.md)
- [سناریوهای پذیرش](/rodo/storyboard-review-kit/cycles/016-flow-ui-panel-selfheal/acceptance.feature)

## Checklist: قدم‌ها

- [x] افزودن آیتم 'ساخت با Flow' به منوی بالای صفحه (⋯) و طراحی پنل مودال/شناور
- [x] پیاده‌سازی دکمهٔ Open Chrome با اجرای کروم در پورت 9222 و پروفایل پایدار جداگانه
- [x] اتصال دکمه‌های Start/Stop/Resume به مدیریت کارهای پس‌زمینه (`tools/jobs.py`) با گزارش زنده
- [x] نمایش فهرست موارد شکست‌خورده با دکمهٔ اختصاصی ارسال مجدد (resend) برای هر آیتم
- [x] پیاده‌سازی مکانیزم توقف و ثبت گزارش عیب‌یابی در `.kit/flow-errors/<timestamp>/` (شامل گام، انتخابگر، اسکرین‌شات و تکه‌کد DOM)
- [x] پشتیبانی از ادامهٔ کار (Resume) پس از به‌روزرسانی `tools/flow_selectors.json`
- [x] تمیزکاری انجام شد؛ تست و رسیدگی به خطا حفظ شد (clean.md)
- [x] تست پذیرش پاس شد
