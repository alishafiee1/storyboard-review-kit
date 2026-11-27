# 001 — اتوماسیون ساخت و دانلود پیش‌نویس ۱K از گوگل Flow با Playwright CDP: design

> Only for MAJOR changes. The coder reads it together with spec.md.

## Problem

ساخت تصویر در Google Flow امروز دستی است. آزمایش ۲۷ نوامبر ۲۰۲۶ ثابت کرد اتصال CDP، پر کردن پرامپت، Generate، و وصل کردن مرجع کار می‌کند؛ ولی ذخیره از روی تگ `<img>` به یک فایل WebP با پسوند `.png` انجام شد و کنترل‌های Download / 1K / 2K ثبت نشدند.

## Proposed approach

یک CLI واحد (`tools/flow_sync.py`) به Chrome باز کاربر روی درگاه `9222` وصل می‌شود. حالت `--mode draft` صف را از `prompts/prompts.txt` و `story.txt` و `.kit/flow-state.json` می‌سازد، بین ساخت‌ها فاصله می‌گذارد، و دانلود مرورگر را مستقیم در پوشهٔ پروژه ذخیره می‌کند. `--dry-run` همان مسیر را بدون کلیک Generate طی می‌کند. حالت `--mode final` در چرخهٔ 002 به همین فایل اضافه می‌شود.

## Architecture impact

لایهٔ جدید در `tools/`، در کنار `watch.py` و `flowname.py`، بدون تغییر مدل دادهٔ `story.txt`. صفحهٔ بررسی همان فایل‌های جدید را مثل هر ورود دیگری می‌بیند. `flow-state.json` در `.kit/` می‌ماند تا `update.py` آن را لمس نکند.

## Components affected

- جدید: `tools/flow_sync.py`
- خواندنی: `tools/story.py`, `tools/flowname.py`, `tools/media.py`, `tools/kitcore.py`
- زمان اجرا: Chrome با `--remote-debugging-port=9222` و پروفایل جدا (`flow-chrome-profile`)
- نباید: نوشتن در Downloads؛ رقابت با `tools/watch.py`

## Data / API impact

هیچ endpoint تازه در `api.py` برای این چرخه لازم نیست. فقط فایل تصویر جدید و `.kit/flow-state.json`. ویرایش `story.txt` در این چرخه پیش‌فرض نیست (سؤال باز در spec).

## Trade-offs

- وابستگی به UI زندهٔ Flow (انتخابگرها ممکن است عوض شوند) در برابر API رسمی که نداریم
- یک خروجی در هر Generate (`x1`) برای نگاشت ساده به `[OUTPUT NAME]`، در برابر پیش‌فرض فعلی UI که ۲ خروجی است
- ذخیرهٔ مستقیم در پروژه، در برابر تکیه بر ناظر Downloads که الان برای کار دستی است

## Risks

- عوض شدن لیبل دکمه‌های دانلود بعد از ساخت؛ باید در اجرای اول ثبت و در spec قفل شوند
- محدودیت نرخ Flow؛ باید فاصله و ازسرگیری داشته باشیم
- اشتباه گرفتن پیش‌نمایش با فایل نهایی (همین در آزمایش رخ داد)

## Alternatives considered

- ادامه با fallback تگ `<img>`: رد شد، چون فایل WebP نامعتبر به‌عنوان png ذخیره شد
- رها کردن فایل در Downloads برای `watch.py`: رد شد، چون رقابت و زمان‌بندی مبهم است
- مرورگر Playwright جدا: رد شد، چون ورود به حساب Flow باید در پروفایل کاربر بماند

## Decisions

- اتصال CDP به Chrome کاربر، نه مرورگر همراه Playwright. چون ورود به Flow و پروفایل جدا قبلاً درست کار کرده است.
- موفقیت یعنی دانلود واقعی ۱K، نه پیش‌نمایش صفحه. چون آزمایش ۲۷ نوامبر خلاف این بود.
- CLI واحد برای draft و (بعداً) final، بدون مصرف توکن مدل زبانی. چون پرامپت‌ها از قبل در پروژه هستند.
