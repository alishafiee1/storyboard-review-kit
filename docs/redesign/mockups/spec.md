# مشخصات دیزاین — صفحه‌ی ریویو (تم دفتر نقاشی)

این سند برای پیاده‌سازی است (مثلاً Claude روی لپ‌تاپ). ماکاپ‌های مرجع:

- `out/desktop.png` — صفحه‌ی اصلی دسکتاپ
- `out/mobile.png` — موبایل: صفحه اصلی + منوی باز
- `out/modal.png` — همان دسکتاپ با دیالوگ «پرامپت تصویر»

ماکاپ‌ها راهنمای حس، لایه‌بندی و سلسله‌مراتب‌اند، نه پیکسل‌پرفکت. متن روی تصویر را کپی نکن؛ رشته‌های همین فایل و فونت `Vazirmatn` را به کار ببر.

---

## 1. Principle

A quiet open sketchbook, not a dashboard. One large scene still, narration beside (or below) it, a handful of fine-liner icons, everything else in a menu. Warm paper, thin ink, lots of air. Persian RTL first.

The desktop is literally a two-page spread: the still is a photo mounted on the right-hand page; the script lives on the left-hand page; a faint binding gutter runs between them. The bottom chrome can follow the pages (transport under the image, approve under the text) rather than one heavy full-width toolbar.

---

## 2. Palette

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#F3EEE4` | App background, page fill |
| `--paper-shade` | `#E8E0D2` | Subtle shade, drawer edge, image mount |
| `--paper-bright` | `#F7F3EB` | Modal / bottom-sheet card |
| `--ink` | `#2A2723` | Primary text and icons |
| `--ink-muted` | `#6E6860` | Meta, English lines, secondary labels |
| `--line` | `#C9BFAE` | Hairlines, input borders, icon strokes when quiet |
| `--line-soft` | `#DDD4C6` | Very faint separators |
| `--accent` | `#B55A42` | Rare: current-line tick, focus caret, flag |
| `--approve` | `#5E7356` | Approve / Save outline and label |
| `--wash-sand` | `#E6D7C0` | Narrator chip, selected menu row |
| `--wash-olive` | `#D5DBC8` | Current dialogue block, progress fill |
| `--chip-mimo` | `#D9D4CC` | Mimo speaker chip |
| `--overlay` | `rgba(42, 39, 35, 0.28)` | Modal dimmer — warm tracing-paper, never flat black |

No neon, no gray-blue Material surfaces, no heavy drop shadows, no gradients. At most a whisper of contact shade under the modal or a mounted still.

---

## 3. Typography

- Font: `Vazirmatn` for all UI and all Persian body. Latin (English dialogue, `EN`, prompt textarea) can stay in Vazirmatn or a humanist mono inside the prompt editor only.
- Direction: `dir="rtl"` on the app root. English dialogue lines are `dir="ltr"`.
- Title (project name): 18px / medium / `--ink`
- Persian body (narration): 16–17px desktop, 15–16px mobile / regular / `--ink` / line-height **1.8**
- English secondary: 13–14px desktop, 12–13px mobile / `--ink-muted`
- Chips, tags, meta, times: 11–12px / `--ink-muted`
- Do not set Persian with a Latin font. Keep ZWNJ where it belongs in source strings (`می‌شه`, `می‌کنم`, …).

---

## 4. Spacing and chrome

- Desktop canvas reference: 1376×768, but the UI is fluid. Content max-width can fill the viewport with **28–32px** page padding.
- Top bar: **56px** desktop, **48px** mobile, one `--line` hairline under it, no fill other than paper.
- Bottom bar: **56px**, one hairline above it.
- Icon size: **20×20px**, stroke **1.5px**, ink color, **16–18px** gap. No badge bubbles, no filled circular icon buttons (the play control is the exception: a thin ink circle ~28–32px with a small triangle).
- Corner radius: **2px** on outline buttons; almost sharp. Phone-frame mockups used a large radius; the real mobile web app is just the screen, no device frame.
- Image mount: 16–24px paper margin around the still, thin hand-drawn-looking 1px border (`--line` is enough in CSS; a perfectly straight border is fine), two small washi-tape marks (olive and sand) at the top corners of the still. Optional, can be a CSS decoration.
- Gutter: a narrow vertical binding shade between the two desktop pages, ~16–24px.
- Text page padding: 28–32px desktop, 16–20px mobile.
- Do not wrap the text column or the image in Material cards or boxed panels.

---

## 5. Desktop layout

RTL two-column spread under the top bar:

- **Right page (~60%)**: the scene still, mounted as above. This is the hero. The still itself has no burned-in captions, subtitles, or speech bubbles.
- **Left page (~40%)**: scene text (`متن صحنه`), line counter (`خط ۲ از ۲`), then dialogue blocks.

Top bar, visual order from the **right**:

1. Hamburger (`☰`) — opens the scene-list / menu drawer from the right
2. Project title + muted episode label
3. Centered scene navigator: chevrons + `۴۵ / ۵۰` + a thin tick-line with olive wash at 45/50, caption `تأیید شده`
4. Far left: the **outside icons** (see §7), then `فا / EN`, then overflow `⋯`

Bottom area (preferred, as in `out/desktop.png`):

- Under the image page: previous / play / next, a thin progress line, time `۰:۱۲ / ۰:۲۸` (display with Persian digits in the Persian locale).
- Under the text page: `کنار بگذار` (quiet text + tray icon) and the primary `تأیید` outline stamp.

A single full-width bottom bar is an acceptable fallback (see `candidates/desktop_c2.png`) if splitting the chrome is awkward in code.

---

## 6. Mobile layout

Vertical stack, no side-by-side columns:

1. Slim top bar: hamburger, title, `۴۵ / ۵۰`, `فا / EN`, `⋯`
2. Full-width 16:9 still, with the same tape/border treatment and 16px side margin
3. Thin playback line + time + small play
4. Text block under the image, scrollable. Show the **active line** first in view; older lines scroll above.
5. Bottom action bar: prev, play, next, then the key icons, then `تأیید`

Secondary tools open in a **right-edge paper drawer** covering ~80% width, with a sliver of the dimmed still visible on the left. Row height ~48px, icon on the right of each label, no colored fills. A pale sand wash marks the selected row.

The prompt editor on mobile is a **bottom sheet** covering ~75% height (see `prompts/flow_prompt_mobile.md`, Prompt 3b), not a tiny centered desktop modal.

---

## 7. Icons outside vs inside the menu

### Always visible (fine-liner, no labels except `تأیید` / `فا / EN`)

| Action | Label | Icon | Where |
|---|---|---|---|
| Approve | تأیید | olive check, outline stamp-button | desktop text-page footer; mobile bottom bar (end / left) |
| Set aside | کنار بگذار | tray / skip | desktop footer, text label + icon; on narrow mobile it may move into the menu |
| Notes | یادداشت | pencil | desktop top-left icon row; mobile bottom bar |
| Image prompt | پرامپت تصویر | landscape frame | same |
| Video prompt | پرامپت ویدیو | clapper or film frame | same |
| Flag | نشانه‌گذاری | flag | same |
| Language | فا / EN | text pill, hairline, active side darker | top bar |
| Overflow | منو | three dots | top bar |
| Menu / scenes | — | hamburger | top bar, right |
| Playback | — | prev, play, next + thin progress | under the still (and mobile bottom transport) |
| Line voice preview | — | tiny speaker on the line meta row | in the text page |

Approve looks like a quiet library stamp: 2px-radius rectangle, 1px `--approve` stroke, olive check, word `تأیید` in `--approve`. Not a bright filled CTA.

### Inside the hamburger or `⋯` menu / drawer

- فهرست صحنه‌ها
- فیلتر
- سرعت پخش (trailing value, e.g. `۱×`)
- زیرنویس
- صداها و گوینده‌ها
- رفرنس‌ها
- نسخه‌ها و آرشیو
- حالت بررسی
- کنار بگذار (if it did not fit on the mobile bar)
- یادداشت‌ها (list entry, in addition to the pencil icon)

Do **not** put Filter, Speed, Subtitles, Voices, References, Versions, or Review back into the top bar as text tabs. That is the clutter the redesign removes.

---

## 8. Dialogue / narration block

Each line, RTL:

1. Speaker chip: small oval, 1px ink outline, light wash (`--wash-sand` for `راوی`, `--chip-mimo` for `میمو`), label in 11–12px
2. Meta: `صدای راوی · آرام و روایی` or `لحنی کنجکاوانه`, plus a tiny speaker to preview that line
3. Persian body
4. English body (`dir="ltr"`, muted)
5. Tags as quietly underlined words, not heavy pills: e.g. `غار` `نقاشی` `جادو`

The **active line** gets a pale olive wash and a 2px terracotta tick on the right edge. Blocks are separated by a short hairline, never a boxed card.

Placeholder copy (episode 1, scene 45), for mock data only:

- راوی / صدای راوی · آرام و روایی
  - برای اجداد ما، نقاشی روی دیوار غار فقط هنر نبود. یک جور جادو بود.
  - For our ancestors, painting on the cave wall wasn't just art. It was a kind of magic.
  - غار، نقاشی، جادو
- میمو / لحنی کنجکاوانه
  - اگر اینو بکشم، شکار بهتر می‌شه؟
  - If I draw this, will the hunt go better?
  - شکار، کنترل

Other UI strings: `توهم کنترل`, `اپیزود ۱`, `تأیید شده`, `متن صحنه`, `خط ۲ از ۲`, `تأیید`, `کنار بگذار`, `پرامپت تصویر`, `پرامپت ویدیو`, `صحنه ۴۵ · قابل ویرایش`, `بستن`, `رونوشت`, `ذخیره`.

---

## 9. Prompt-edit modal

Opens over the current page with the warm `--overlay` dimmer (paper texture should still be hinted, not a black veil).

Desktop: a centered paper card, about 760×560px, `--paper-bright`, 1px `--line` border, optional washi tape on the top edge, padding 28–32px, faint contact shade only.

- Header, RTL: title `پرامپت تصویر` or `پرامپت ویدیو`; subtitle `صحنه ۴۵ · قابل ویرایش`; close `×` on the left
- Body: one large textarea, hairline border, 13–14px, comfortable leading, visible caret, no syntax highlighter, no model picker, no token graphs
- Footer, RTL: short meta on the start/right (e.g. `انگلیسی`); on the end/left: `بستن` (text only), `رونوشت` (hairline + copy icon), `ذخیره` (olive stamp, same language as Approve)

The dialog has one job: read, edit, save, and copy the prompt.

Mobile: bottom sheet, ~75% height, same content, a small drag tick on top.

---

## 10. Scene still (content rules)

The still is a production frame, not UI. 16:9. No burned-in captions, no speech bubbles, no watermarks. In this series the on-model Mimo is a flat graphic stickman (circular white head, messy dark hair, no nose, white T-shirt, black shorts, single-line limbs) inside a painterly world. The review app must not composite text onto that image.

---

## 11. What not to build

- A row of text tabs in the header (فیلتر / سرعت / پخش / زیرنویس / صداها / رفرنس‌ها / بررسی all visible at once)
- Heavy cards, drop shadows, rounded-rectangle button soup
- Fat colorful filled icons
- A harsh black modal backdrop
- Crowding both full dialogue blocks and a dense toolbar onto a mobile first screen — crop to the image + the active line, and let the rest scroll

---

## 12. Reference candidates

Kept in `out/`. Runners-up in `candidates/`:

- `desktop_c2.png` — same theme, full-width bottom bar, slightly weaker English wrapping
- `mobile_c2.png` — rejected: leaked `48px` / `56px` labels, heavier notch, messier captions
- `modal_c2.png` — usable, but footer is more LTR and the textarea has a worse typo

Flow prompts (self-contained, English, for Google Flow) are in `prompts/flow_prompt_desktop.md` and `prompts/flow_prompt_mobile.md`.
