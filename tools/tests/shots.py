# -*- coding: utf-8 -*-
"""Screenshots of the real review page, for the visual comparison with docs/redesign/mockups/ (phase 6).
  python tools/tests/shots.py            writes docs/redesign/screens/{desktop-review,desktop-modal,desktop-drawer,mobile-review,mobile-drawer,mobile-modal,*-gallery}.png
It builds a throw-away project (the test fixture plus a 50-picture story in the style of the mock-ups: scene 4 «غار», picture 45, two voices),
starts its own server on a free port and drives the page like a user. The still is a crop of the painting in the mock-up (fixture/still-cave.png,
made once from docs/redesign/mockups/desktop.png). Nothing in the page is faked: what you see is what the app draws."""
import os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as T  # noqa: E402  (the tests' Proj helper: temp project + server)

KIT = T.KIT
OUT = os.path.join(KIT, "docs", "redesign", "screens")
STILL = os.path.join(T.FIX, "still-cave.png")
MOCK = os.path.join(KIT, "docs", "redesign", "mockups", "desktop.png")

PROMPT = """STYLE LOCK: 16:9 widescreen. A richly detailed painterly oil-painted cave interior, cinematic firelight. MIMO is a 25-year-old slim stickman with a perfectly circular flat white head, short dark messy hair, oval dot eyes, short brows, a small mouth, NO nose, true single-line black limbs, a flat WHITE short-sleeved T-shirt and flat BLACK shorts. MIMO is a clean flat graphic character; do not paint him with the same brushy oil texture as the world.

SHOT: three-quarter view, medium-wide.
ACTION: standing still, looking up at the wall paintings, thoughtful, both feet planted.
SETTING: prehistoric cave, ochre buffalo and hunter paintings, warm firelight, umber rock.
MOOD: wonder, quiet ritual."""


def story():
    scenes = [(1, "بیدار شدن", 1, 12), (2, "راه", 13, 24), (3, "نیمکت", 25, 40), (4, "غار", 41, 50)]
    out = ["# قسمت ۱: «توهم کنترل»", "tts-model: elevenlabs/eleven-v4-turbo", "",
           "speaker: راوی | #8a6d3b | george | توصیفی", "speaker: میمو | #6a7b57 | charlie | کنجکاو", ""]
    for n, title, a, b in scenes:
        out += ["=== scene-%02d | %s | - ===" % (n, title)]
        if n == 4:
            out += ["env: غار، آتش، نقاشی‌های دیواری."]
        for i in range(a, b + 1):
            out += ["[IMG%03d]" % i]
            if i % 3 != 0 and i < 44:
                out += ["status: ok"]
            if i == 47:
                out += ["off: yes"]
            if i == 45:
                out += ["pick: e5f6a7b8", "note: دیوار پشت میمو کمی تاریک‌تر باشد.",
                        "say: راوی | برای اجداد ما، نقاشی روی دیوار غار فقط هنر نبود. یک جور جادو بود.",
                        "en: For our ancestors, painting on the cave wall wasn't just art. It was a kind of magic.", "id: IMG045-1",
                        "say: میمو (کنجکاو) | اگر اینو بکشم، شکار بهتر می‌شه؟",
                        "en: If I draw this, will the hunt go better?", "id: IMG045-2"]
            elif i % 5 == 0:
                out += ["act: نمای %d." % i]
        out += [""]
    return "\n".join(out) + "\n"


def make_still(browser):
    """Crop the painting out of the mock-up (once) so the screenshots show a real picture instead of a flat colour."""
    if os.path.exists(STILL):
        return
    page = browser.new_page(viewport={"width": 1376, "height": 768})
    page.goto("file:///" + MOCK.replace("\\", "/").lstrip("/"))
    page.screenshot(path=STILL, clip={"x": 748, "y": 214, "width": 570, "height": 321})
    page.close()


def build(proj):
    root = proj.root
    open(os.path.join(root, "scenario", "story.txt"), "w", encoding="utf-8", newline="\n").write(story())
    pr = ["# prompts", ""]
    for i in range(1, 51):
        pr += ["=== IMG%03d ===" % i]
        if i == 45:
            pr += ["[REFS TO ATTACH: STYLE_ANCHOR| CH_MIMO]", PROMPT]
        else:
            pr += ["Prompt of picture %d." % i]
        pr += [""]
    open(os.path.join(root, "prompts", "prompts.txt"), "w", encoding="utf-8", newline="\n").write("\n".join(pr))
    for f in os.listdir(os.path.join(root, "images", "scenes")):  # the fixture's own tiny pictures give way to the still
        if f.startswith("IMG00") and f.endswith((".png",)) and "_x" not in f:
            os.remove(os.path.join(root, "images", "scenes", f))
    still = open(STILL, "rb").read()
    now = time.time()
    put = lambda rel, age: (os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True), open(os.path.join(root, rel), "wb").write(still),
                            os.utime(os.path.join(root, rel), (now - age, now - age)))
    for rel in ("images/refs/CH/CH_MIMO.png", "images/refs/STYLE/STYLE_ANCHOR.png"):
        put(rel, 900)
    for i in range(1, 51):
        if i != 45 and i != 49:  # picture 49 has no file: the empty slot of the gallery
            put("images/scenes/IMG%03d_x.png" % i, 800)
        if i in (7, 21, 33):
            put("images/scenes/IMG%03d_y_a1b2c3d4.png" % i, 700)
    for name, age in (("IMG045_cave.png", 500), ("IMG045_cave_e5f6a7b8_4K.png", 400), ("IMG045_cave_a1b2c3d4_2K.png", 300), ("IMG045_cave_9a8b7c6d.png", 200)):
        put("images/scenes/" + name, age)
    for lg in ("fa", "en"):
        os.makedirs(os.path.join(root, "audio", lg), exist_ok=True)
        for k, secs in ((1, 16), (2, 12)):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", str(secs),
                            os.path.join(root, "audio", lg, "IMG045-%d.mp3" % k)], check=True)


def main():
    from playwright.sync_api import sync_playwright
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = None
        for ch in ("msedge", "chrome", None):
            try:
                browser = p.chromium.launch(channel=ch)
                break
            except Exception:
                continue
        make_still(browser)
        proj = T.Proj("1-توهم-کنترل")
        try:
            build(proj)

            def open_at(w, h):
                ctx = browser.new_context(viewport={"width": w, "height": h}, locale="fa-IR")
                page = ctx.new_page()
                page.goto(proj.url + "/review.html#IMG045")
                page.wait_for_selector(".blk.on")
                page.evaluate("document.fonts.ready")
                page.wait_for_function("[...document.querySelectorAll('.blk.on img')].every(i => i.complete)")
                page.wait_for_timeout(600)
                return page

            page = open_at(1376, 768)
            page.click("#lang")  # English under the Persian, like the mock-up
            page.wait_for_selector(".blk.on .en")
            page.wait_for_timeout(300)
            page.evaluate("document.querySelectorAll('.blk.on .it')[1].click()")  # the second line is the active one, like in the mock-up
            page.mouse.move(700, 740)
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(OUT, "desktop-review.png"))
            page.click("#bPrompt")
            page.wait_for_selector("dialog.pm[open]")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(OUT, "desktop-modal.png"))
            page.keyboard.press("Escape")
            page.wait_for_selector("dialog.pm", state="detached")
            page.click("#menuBtn")
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(OUT, "desktop-drawer.png"))
            page.click("[data-panel=scenes]")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(OUT, "desktop-drawer-scenes.png"))
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            page.click("#more")  # the image menu, the note popover, a line being edited, the scene label dialog and the voice manager
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(OUT, "desktop-menu.png"))
            page.keyboard.press("Escape")
            page.click("#bNote")
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(OUT, "desktop-note.png"))
            page.mouse.click(700, 650)
            page.click(".blk.on .it >> nth=0 >> .fa .v")
            page.wait_for_selector(".ie.say")
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(OUT, "desktop-edit-line.png"))
            page.keyboard.press("Escape")
            page.click(".blk.on .slabel")
            page.wait_for_selector("dialog.dlg[open]")
            page.screenshot(path=os.path.join(OUT, "desktop-scene-dialog.png"))
            page.keyboard.press("Escape")
            page.click(".blk.on [data-vgen] >> nth=0")
            page.wait_for_selector("dialog.dlg[open]")
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(OUT, "desktop-voice-dialog.png"))
            page.keyboard.press("Escape")
            page.context.close()
            page = open_at(390, 844)
            page.screenshot(path=os.path.join(OUT, "mobile-review.png"))
            page.click("#menuBtn")
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(OUT, "mobile-drawer.png"))
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            page.click("[data-fwd=bPrompt]")
            page.wait_for_selector("dialog.pm[open]")
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(OUT, "mobile-modal.png"))
            page.context.close()
            for name, w, h in (("desktop-gallery", 1376, 768), ("mobile-gallery", 390, 844)):  # the start page: no address
                ctx = browser.new_context(viewport={"width": w, "height": h}, locale="fa-IR")
                page = ctx.new_page()
                t0 = time.time()
                page.goto(proj.url + "/review.html")
                page.wait_for_function("document.querySelectorAll('#ggrid .tile[data-id]').length == 50")
                assert time.time() - t0 < 1.0, "50 tiles must show in under a second: %.2fs" % (time.time() - t0)
                page.evaluate("document.fonts.ready")
                page.wait_for_function("[...document.querySelectorAll('#ggrid img')].slice(0, 30).every(i => i.complete)")
                page.wait_for_timeout(300)
                page.screenshot(path=os.path.join(OUT, name + ".png"))
                ctx.close()
        finally:
            proj.close()
        browser.close()
    print("screenshots written to", OUT)


if __name__ == "__main__":
    main()
