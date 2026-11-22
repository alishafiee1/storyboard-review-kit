# CLAUDE.md — نام پروژه را اینجا بنویس

قبل از هر کاری روی تصویرها، پرامپت‌ها یا سناریو این‌ها را بخوان:
1. `skills/how-to-write-prompts-for-flow.md` — استاندارد پرامپت‌نویسی برای Flow و قالب `story.txt`.
2. `skills/image-style-skill.txt` — متن سبک نقاشی این پروژه.

| مسیر | چیست |
|---|---|
| `review.html` + `click-for-review.bat` | بازبینی و ویرایش (موتور؛ با `python tools/update.py` به‌روز می‌شود، دستی ویرایشش نکن) |
| `scenario/story.txt` | سناریوی دوزبانه، گوینده‌ها، یادداشت‌ها و پرچم‌ها |
| `prompts/prompts.txt` | همهٔ پرامپت‌ها |
| `images/` | `refs/` رفرنس‌ها و `scenes/` تصویرهای ساخته‌شده (`IMG001_...jpg`) |
| `tools/tts.py`, `tools/voices.py` | ساخت صدا و فهرست صداها (کلید `OPENROUTER_API_KEY` در `.env`) |
| `tools/update.py` | به‌روزرسانی موتور از GitHub بدون دست زدن به داده‌های پروژه |
