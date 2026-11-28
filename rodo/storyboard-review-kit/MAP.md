# نقشهٔ پروژه: Storyboard Review Kit

> هر کارت و سندهایش در `rodo/<project>/cycles/NNN-slug/` می‌ماند. این فایل وقتی یک کارت تمام یا لغو می‌شود به‌روز می‌شود (نه وسط کدنویسی)، تا چند نفر هم‌زمان کار کنند و Git تداخل نگیرد. وضعیت کار جاری در کارت‌هاست.
> کوتاه بماند (حدود ۴۰ خط). اول از همه همین را بخوانید.

## این پروژه چیست

یک ابزار رایگان و تک‌صفحه‌ای برای بررسی استوری‌بورد ویدیوهای ساخته‌شده با هوش مصنوعی. سناریو، پرامپت، تصویر و صدا در فایل‌های متنی ساده می‌مانند و روی یک صفحه ویرایش و انتخاب می‌شوند.

## الان کجاییم

نسخهٔ جاری کیت `2.7.0` است. بازطراحی صفحه، حالت مرجع‌ها (`refs`)، کنترل سرعت، نوار ابزار تصویر، جابه‌جایی خط، عملیات گروهی گالری و پذیرش rodo-spec به‌عنوان منبع حقیقت توسعه تا این نسخه آمده‌اند. اتوماسیون ساخت تصویر در Google Flow در پنج فاز تدریجی (A اسکلت و dry-run، B ارسال دسته‌ای و مراجع با نام، C دانلود و بازآزمایی، D پنل UI و خودترمیمی، و ارتقای نهایی ۲K) طراحی شده است.

## انجام‌شده

- [003-foundation-plain-text](cycles/003-foundation-plain-text/card.rodo.md) — پایهٔ کیت محلی بازبینی مبتنی بر متن ساده
- [004-versions-voices-intake](cycles/004-versions-voices-intake/card.rodo.md) — نسخه‌ها، برداشت‌های صوتی و دریافت فایل‌های Flow
- [005-sketchbook-redesign](cycles/005-sketchbook-redesign/card.rodo.md) — پوستهٔ دفتر نقاشی، گالری و بهبودهای موبایل تا نسخهٔ 2.7.0
- [006-dead-code-cleanup](cycles/006-dead-code-cleanup/card.rodo.md) — مرحلهٔ ۱: پاکسازی کدهای مرده، رد افزودن به scene-00 و هماهنگی تست‌ها
- [007-speed-control](cycles/007-speed-control/card.rodo.md) — مرحلهٔ ۲: کنترل سرعت یکپارچه کنار نوار پخش
- [008-picture-toolbar-scene-menu](cycles/008-picture-toolbar-scene-menu/card.rodo.md) — مرحلهٔ ۳: نوار ابزار روی هر تصویر و منوی صحنه
- [009-line-move-and-insert-bar](cycles/009-line-move-and-insert-bar/card.rodo.md) — مرحلهٔ ۴: جابه‌جایی خط با /api/moveline و نوار افزودن دیالوگ
- [010-undo-consistency](cycles/010-undo-consistency/card.rodo.md) — مرحلهٔ ۵: برگشت‌پذیری کنار گذاشتن تصویر و عملیات گروهی گالری (/api/imagebulk)
- [011-scene-grouped-gallery](cycles/011-scene-grouped-gallery/card.rodo.md) — مرحلهٔ ۶: گروه‌بندی گالری با هدر صحنه و انتخاب‌گر بندانگشتی
- [012-references-mode](cycles/012-references-mode/card.rodo.md) — مرحلهٔ ۷: حالت مرجع‌ها (refs) با قوانین متمرکز، گوینده‌های مشترک و تاریخچهٔ جدا
- [013-rodo-spec-migration](cycles/013-rodo-spec-migration/card.rodo.md) — مرحلهٔ ۸: پذیرش rodo-spec به‌عنوان تنها منبع حقیقت توسعه و حذف اسناد قدیمی
- [001-flow-sync-skeleton-dryrun](cycles/001-flow-sync-skeleton-dryrun/card.rodo.md) — فاز A: اسکلت همگام‌ساز Flow و اجرای آزمایشی (dry-run)
- [014-flow-batch-submit-refs](cycles/014-flow-batch-submit-refs/card.rodo.md) — فاز B: ارسال دسته‌ای پرامپت‌ها و اتصال مراجع با نام
- [016-flow-ui-panel-selfheal](cycles/016-flow-ui-panel-selfheal/card.rodo.md) — فاز D: پنل کاربری در بازبینی و خودترمیمی خطاها

## لغوشده

> قالب هر خط: لینک چرخه، بعد « — »، بعد دلیل لغو.

## بعدی

- [015 فاز C: دریافت دانلودها، نام‌گذاری دقیق و مدیریت بازآزمایی‌ها](cycles/015-flow-download-naming-retries/simple.md)
- [002 ارتقا و جایگزینی کیفیت ۲K تصاویر تاییدشده و مدیریت خودکار زیپ در Flow (وابسته به 016)](cycles/002-flow-2k-final-and-zip/simple.md)
