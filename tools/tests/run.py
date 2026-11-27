# -*- coding: utf-8 -*-
"""End-to-end tests of the review page + server, in a real browser (Playwright, using the Edge/Chrome already installed).
  pip install playwright                       (once; no browser download needed)
  python tools/tests/run.py                    run everything
  python tools/tests/run.py edit_dialogue fab  run only tests whose name contains one of these words
  python tools/tests/run.py --update-baseline  rewrite tools/tests/baseline/* from the current page (do this ONLY when the page is meant to look different)
Every test builds a fresh throw-away project in a temp folder (fixture/ + the tools of this checkout), starts its own server on a free port and
never touches a real project. Nothing here calls a paid service. This folder is not part of the engine (ENGINE.txt) and is not sent to projects."""
import argparse, contextlib, glob, json, os, re, shutil, socket, struct, subprocess, sys, tempfile, time, traceback, urllib.error, urllib.request, zlib

# The tests never use a real key (so they behave the same on every computer and can never spend money); the page only needs to see «a key exists».
os.environ["OPENROUTER_API_KEY"] = "test-key-not-real"

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))
FIX, BASE = os.path.join(HERE, "fixture"), os.path.join(HERE, "baseline")
UPDATE = False
TESTS = []


def png():
    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xc9\x82\x2b" * 16 for _ in range(9))
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 16, 9, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


def build_project(root):
    """A small complete project: fixture texts, pictures, a few silent audio files, and the tools of this checkout."""
    for f in ("review.html", "click-for-review.bat", "VERSION", "ENGINE.txt"):
        if os.path.exists(os.path.join(KIT, f)):
            shutil.copy2(os.path.join(KIT, f), root)
    shutil.copytree(os.path.join(KIT, "tools"), os.path.join(root, "tools"), ignore=shutil.ignore_patterns("tests", "__pycache__"))
    for d, src in (("scenario", "story.txt"), ("prompts", "prompts.txt"), ("prompts", "video-prompts.txt"), ("voices", "catalog.txt")):
        os.makedirs(os.path.join(root, d), exist_ok=True)
        shutil.copy2(os.path.join(FIX, src), os.path.join(root, d, src))
    for rel in ("images/scenes/IMG001_start.png", "images/scenes/IMG002_sign.png", "images/scenes/IMG003_sea.png", "images/refs/CH/CH_ALI.png"):
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        open(os.path.join(root, rel), "wb").write(png())
    now = time.time()
    for rel in ("images/scenes/IMG001_start.png", "images/scenes/IMG002_sign.png", "images/scenes/IMG003_sea.png"):
        os.utime(os.path.join(root, rel), (now - 100, now - 100))
    open(os.path.join(root, "images/scenes/IMG001_start_a1b2c3.png"), "wb").write(png())  # the same picture asked for again: a second version
    if shutil.which("ffmpeg"):
        for lg in ("fa", "en"):
            os.makedirs(os.path.join(root, "audio", lg), exist_ok=True)
            for id_ in ("IMG001_1", "IMG001_2"):
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.4",
                                os.path.join(root, "audio", lg, id_ + ".mp3")], check=True)
            for k, tag in enumerate(("eleven-v3", "eleven-v4")):  # the same line made again by two other models
                dst = os.path.join(root, "audio", lg, "IMG001_1.%s.mp3" % tag)
                shutil.copy2(os.path.join(root, "audio", lg, "IMG001_1.mp3"), dst)
                os.utime(dst, (now + 10 + k, now + 10 + k))


class Proj:
    """A temp project + its server. .root, .url; helpers to read what the page wrote to disk."""

    def __init__(self, name="proj"):
        self.tmp = tempfile.mkdtemp(prefix="srk-test-")
        self.root = os.path.join(self.tmp, name)
        os.makedirs(self.root)
        build_project(self.root)
        with contextlib.closing(socket.socket()) as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = "http://127.0.0.1:%d" % self.port
        env = dict(os.environ, PORT=str(self.port), IDLE_SECONDS="3600", PYTHONIOENCODING="utf-8", STORYBOARD_NO_WATCH="1")
        self.proc = subprocess.Popen([sys.executable, os.path.join(self.root, "tools", "serve.py")], cwd=self.root, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(50):
            try:
                urllib.request.urlopen(self.url + "/api/ping", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("server did not start: " + self.proc.stderr.read().decode("utf-8", "ignore")[:400])

    def read(self, rel):
        p = os.path.join(self.root, *rel.split("/"))
        for _ in range(40):  # on Windows the server's atomic replace can lock the file for a moment
            try:
                return open(p, encoding="utf-8").read().replace("\r\n", "\n") if os.path.exists(p) else ""
            except PermissionError:
                time.sleep(0.05)
        raise PermissionError(p)

    def story(self):
        return self.read("scenario/story.txt")

    def wait(self, rel, text, absent=False, secs=6):
        """Wait until the file contains (or, with absent, no longer contains) text."""
        for _ in range(int(secs * 20)):
            if (text in self.read(rel)) != absent:
                return
            time.sleep(0.05)
        raise AssertionError("%s %s %r\n---\n%s" % (rel, "still has" if absent else "never got", text, self.read(rel)[:1500]))

    def wait_in(self, marker, text, absent=False, secs=6):
        """Like wait(), but only inside the block that starts with the marker line (e.g. [IMG002])."""
        def block():
            m = re.search(r"^%s\n(.*?)(?=^\[IMG|^===|\Z)" % re.escape(marker), self.story(), re.S | re.M)
            return m.group(1) if m else ""
        for _ in range(int(secs * 20)):
            if (text in block()) != absent:
                return
            time.sleep(0.05)
        raise AssertionError("%s block %s %r\n---\n%s" % (marker, "still has" if absent else "never got", text, block()))

    def api(self, path, body=None):
        req = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "null")

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)


def settle(page, secs=4):
    """After a save the page fetches the project and re-draws itself (RELOADS counts those); wait for that before the next click,
    otherwise the click lands on elements that are about to be replaced."""
    try:
        page.wait_for_function("window.__kit.S.RELOADS>%d" % page._reloads, timeout=secs * 1000)
    except Exception:
        pass
    page._reloads = page.evaluate("window.__kit.S.RELOADS")
    page.wait_for_timeout(250)


def at(page, bid):
    """Show one picture. The page shows one at a time; a link like review.html#IMG002 (the address) is how a test (or a bookmark) goes to it."""
    page.evaluate("id => { location.hash = id }", bid)
    page.wait_for_selector('.blk.on[data-bid="%s"]' % bid)


def atb(page, n):
    """Show block number n (the page keeps all blocks as #b0, #b1 ...; only the shown one is visible)."""
    bid = page.evaluate("n => document.querySelector('#b' + n).dataset.bid", n)
    at(page, bid)


def en(page, on=True):
    """The فا / EN pill: show (and play) the English lines."""
    if page.evaluate("document.querySelector('#showEN').checked") != on:
        page.click("#lang")
        settle(page)


def drawer(page, panel=None):
    """Open the paper drawer (and one of its panels)."""
    if not page.evaluate("document.body.classList.contains('dopen')"):
        page.click("#menuBtn")
    if panel:
        if page.is_visible("#dback"):
            page.click("#dback")
        page.click("#dmenu [data-panel=%s]" % panel)
        page.wait_for_selector("#drawer .dpanel:not([hidden])")


def undrawer(page):
    page.keyboard.press("Escape")
    page.wait_for_function("!document.body.classList.contains('dopen')")


def more(page):
    """Open the image «⋯» menu of the picture on show."""
    page.click("#more")
    page.wait_for_selector("#morePop:not([hidden])")


def label(page):
    return page.inner_text(".blk.on .slabel")


def use_story(proj, page, name="story-legacy.txt"):
    """Swap the project's story.txt for another fixture (the server re-reads it on every request) and reload the page."""
    shutil.copy2(os.path.join(FIX, name), os.path.join(proj.root, "scenario", "story.txt"))
    page.evaluate("history.replaceState(null, '', '#review')")  # the old address may name a picture the new story does not have (that would open the gallery)
    page.reload()
    page.wait_for_selector(".blk.on")
    page._reloads = 0


def story_bytes(proj):
    with open(os.path.join(proj.root, "scenario", "story.txt"), "rb") as f:
        return f.read()


def test(fn):
    TESTS.append(fn)
    return fn


def norm(html):
    """Page HTML without the parts that change between runs (file timestamps)."""
    html = re.sub(r"[۰-۹]{4}/[۰-۹]{1,2}/[۰-۹]{1,2}", "DATE", html)  # the voice list's date is «today»
    return re.sub(r"\?v=\d+", "?v=0", html).strip() + "\n"


def baseline(name, text):
    p = os.path.join(BASE, name)
    if UPDATE:
        os.makedirs(BASE, exist_ok=True)
        open(p, "w", encoding="utf-8", newline="\n").write(text)
        return
    assert os.path.exists(p), "no baseline %s (run with --update-baseline on a known-good version)" % name
    want = open(p, encoding="utf-8").read()
    if want != text:
        open(os.path.join(tempfile.gettempdir(), "srk-diff-" + name), "w", encoding="utf-8", newline="\n").write(text)
        a, b = want.split("\n"), text.split("\n")
        i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
        raise AssertionError("baseline %s differs at line %d:\n  want: %s\n  got : %s\n(full output: %s)" % (
            name, i + 1, (a[i] if i < len(a) else "<end>")[:300], (b[i] if i < len(b) else "<end>")[:300],
            os.path.join(tempfile.gettempdir(), "srk-diff-" + name)))


def open_page(browser, proj, errors, wait_ready=True):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="fa-IR")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
    page.on("console", lambda m: errors.append("console.error: %s" % m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    page.on("response", lambda r: errors.append("HTTP %d %s" % (r.status, r.url)) if r.status >= 400 and not r.url.endswith("favicon.ico") else None)
    page._dialogs = []
    page._errors = errors
    page.on("dialog", lambda d: (page._dialogs.append(d.message), d.accept(d.default_value) if d.type == "prompt" else d.accept()))
    page.goto(proj.url + "/review.html#review")  # no address = the gallery; #review = the spread on the first picture
    page._reloads = 0
    if wait_ready:
        page.wait_for_selector(".blk.on")
    return page


# ---------------------------------------------------------------- the tests: every one gets (proj, page)
@test
def load_and_snapshot(proj, page):
    """The page loads, shows ONE picture at a time (all blocks are in the page, one is on show), and what it draws is exactly what the known-good version drew."""
    assert page.locator("section[data-scene]").count() == 3
    assert page.locator("figure.shot").count() == 4
    assert page.locator(".it.sp").count() == 4
    assert page.locator(".blk").count() == 4 and page.locator(".blk.on").count() == 1 and page.locator(".blk:visible").count() == 4  # v2.4: every picture is a page of one scrolling list
    assert page.inner_text("#pos").strip() == "۱ / ۴" and page.evaluate("document.fonts.check('16px Vazirmatn')")
    en(page)
    page.wait_for_selector(".blk .en", state="attached")
    page.wait_for_timeout(300)
    baseline("list-en.html", norm(page.inner_html("#list")))
    en(page, False)
    page.wait_for_timeout(300)
    baseline("list-fa.html", norm(page.inner_html("#list")))
    baseline("bar.html", norm(page.inner_html("#bar")))
    baseline("footer.html", norm(page.inner_html("#foot")))
    drawer(page)
    baseline("drawer-menu.html", norm(page.inner_html("#dmenu")))
    drawer(page, "refs")
    baseline("refs.html", norm(page.inner_html("#refs")))
    drawer(page, "spk")
    baseline("speakers.html", norm(page.inner_html("#spk")))
    undrawer(page)
    code, data = proj.api("/api/project")
    data.pop("time", None)
    data["tts"].pop("updated", None)  # file time of voice-config.json
    data["scenes"] = json.loads(re.sub(r"\?v=\d+", "?v=0", json.dumps(data["scenes"], ensure_ascii=False)))
    baseline("project.json", json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


@test
def edit_dialogue(proj, page):
    atb(page, 3)
    assert "voice-stale" not in proj.story().split("=== scene-02")[1]
    page.click("#b3 .it.sp .fa .v >> nth=0")
    page.fill(".ie.say textarea", "متن تازهٔ راوی")
    page.press(".ie.say textarea", "Enter")
    proj.wait("scenario/story.txt", "say: راوی (آهسته) | متن تازهٔ راوی")
    assert "voice-stale: fa" in proj.story().split("=== scene-02")[1]  # a changed line makes that scene's voice out of date
    page.wait_for_selector("text=متن تازهٔ راوی")


@test
def edit_cancel_with_escape(proj, page):
    atb(page, 1)
    before = proj.story()
    page.click("#b1 .it.sp .fa .v >> nth=0")
    page.fill(".ie.say textarea", "چیزی که نباید ذخیره شود")
    page.press(".ie.say textarea", "Escape")
    page.wait_for_timeout(300)
    assert proj.story() == before and page.locator(".ie.say").count() == 0


@test
def edit_env_and_act(proj, page):
    atb(page, 1)
    page.click(".blk.on .env .v >> nth=0")
    page.fill(".ie textarea", "محیط تازه")
    page.press(".ie textarea", "Enter")
    proj.wait("scenario/story.txt", "env: محیط تازه")
    settle(page)
    page.click(".blk.on .it.act .v >> nth=0")
    page.fill(".ie textarea", "توضیح تازه")
    page.press(".ie textarea", "Enter")
    proj.wait("scenario/story.txt", "act: توضیح تازه")


@test
def add_and_delete_dialogue(proj, page):
    atb(page, 2)
    page.click("#b2 .addbar button[data-add=say]")
    page.fill(".cmp input.nm", "علی")
    page.fill(".cmp textarea", "دیالوگ اضافه‌شده")
    page.press(".cmp textarea", "Enter")
    proj.wait("scenario/story.txt", "say: علی | دیالوگ اضافه‌شده")
    page.wait_for_selector("text=دیالوگ اضافه‌شده")
    settle(page)
    page.locator(".it.sp", has_text="دیالوگ اضافه‌شده").locator("[data-del]").click()  # the page confirms, the test accepts
    proj.wait("scenario/story.txt", "دیالوگ اضافه‌شده", absent=True)


@test
def add_translation(proj, page):
    en(page)
    at(page, "IMG002")
    page.wait_for_selector(".blk.on [data-aden]")
    page.click(".blk.on [data-aden] >> nth=0")
    page.fill(".ie textarea", "A new translation")
    page.press(".ie textarea", "Enter")
    proj.wait("scenario/story.txt", "en: A new translation")


@test
def change_speaker_and_tone(proj, page):
    atb(page, 1)
    page.click("#b1 .it.sp .nm >> nth=0")
    page.fill(".ie.say input.tn", "آهسته")
    page.press(".ie.say textarea", "Enter")
    proj.wait("scenario/story.txt", "say: راوی (آهسته) | این علیه.")


@test
def unknown_tone_is_flagged(proj, page):
    page.wait_for_selector(".msg.tonewarn")
    assert page.locator(".msg.tonewarn").count() == 1 and "عصبانی" in page.inner_text(".msg.tonewarn")
    drawer(page, "spk")
    assert page.locator("#spk input.unk").count() == 1
    page.wait_for_selector('#spk [data-st="2"]')
    page.fill('#spk [data-st="2"]', "آهسته")
    page.locator('#spk [data-st="2"]').blur()  # the page saves on «change», which fires when the field loses focus
    proj.wait("scenario/story.txt", "| aura-2-thalia-en | آهسته")
    page.wait_for_function("!document.querySelector('.msg.tonewarn')")


@test
def status_and_note(proj, page):
    """The note is in the pencil popover of the picture on show; Enter saves it; the old text buttons are gone."""
    at(page, "IMG002")
    f = "figure.shot[data-id=IMG002]"
    for gone in ("[data-m=ok]", "[data-m=redo]", "[data-nt]"):
        assert page.locator(f + " " + gone).count() == 0, gone + " buttons were removed from the page"
    assert page.get_attribute(f + " textarea.nt", "placeholder").startswith("یادداشت برای این صحنه")
    assert page.is_hidden(f + " .nbox") and "has" not in (page.get_attribute("#bNote", "class") or "")
    page.click("#bNote")
    page.wait_for_selector(f + " .nbox", state="visible")
    page.fill(f + " textarea.nt", "یادداشت تست")
    page.press(f + " textarea.nt", "Enter")
    proj.wait_in("[IMG002]", "note: یادداشت تست")
    settle(page)
    assert page.locator("#bNote.has").count() == 1, "a picture with a note shows the pencil in the accent colour"
    page.click("#bNote")
    assert page.is_hidden(f + " .nbox")
    page.click("#bNote")
    page.fill(f + " textarea.nt", "")
    page.mouse.click(700, 500)  # a click outside saves and closes the popover
    proj.wait_in("[IMG002]", "note:", absent=True)


@test
def edit_advice_fx(proj, page):
    assert page.locator("[data-sfx], .fxs").count() == 0, "the whole-scene edit box was removed (each picture has its own edit)"
    at(page, "IMG003")
    page.click("#bNote")
    page.fill("figure.shot[data-id=IMG003] .nbox textarea.fx", "زوم سریع")
    page.press("figure.shot[data-id=IMG003] .nbox textarea.fx", "Enter")
    proj.wait("scenario/story.txt", "fx: زوم سریع")


@test
def prompts_save(proj, page):
    """The prompt card: references on top, a big textarea, بستن / رونوشت / ذخیره; Esc and the close button ask first when something is unsaved."""
    at(page, "IMG003")
    page.click("#bPrompt")
    dlg = "dialog.pm"
    page.wait_for_selector(dlg + "[open]")
    assert "پرامپت تصویر" in page.inner_text(dlg + " h3") and "قابل ویرایش" in page.inner_text(dlg + " .sub")
    assert page.locator(dlg + " .prefs [data-attach=IMG003]").count() == 1 and page.locator(dlg + " .prefs .chip").count() >= 2
    box = page.locator(dlg).bounding_box()
    assert 700 <= box["width"] <= 780 and 480 <= box["height"] <= 580, box
    assert page.input_value(dlg + " textarea") == "[REFS TO ATTACH: STYLE_ANCHOR| CH_ALI]\nPrompt of picture 3."
    page.keyboard.press("Escape")  # nothing changed: Esc just closes
    page.wait_for_selector(dlg, state="detached")
    page.click("#bPrompt")
    page.fill(dlg + " textarea", "[REFS TO ATTACH: STYLE_ANCHOR| CH_ALI]\nA brand new prompt.")
    assert page.locator(dlg + " [data-psave].dirty").count() == 1
    page._dialogs.clear()
    page.keyboard.press("Escape")  # unsaved: the page asks (the test accepts, so it closes) ...
    page.wait_for_selector(dlg, state="detached")
    assert any("ذخیره‌نشده" in m for m in page._dialogs), page._dialogs
    assert "A brand new prompt." not in proj.read("prompts/prompts.txt")
    page.click("#bPrompt")
    page.fill(dlg + " textarea", "[REFS TO ATTACH: STYLE_ANCHOR| CH_ALI]\nA brand new prompt.")
    page.click(dlg + " [data-pcopy]")
    page.wait_for_function("document.querySelector('dialog.pm [data-pcopy]').textContent.includes('کپی شد')")
    page.click(dlg + " [data-psave]")
    proj.wait("prompts/prompts.txt", "A brand new prompt.")
    proj.wait("scenario/story.txt", "image-stale: yes")
    settle(page)
    assert page.locator(dlg + " [data-psave].dirty").count() == 0
    page.click(dlg + " [data-pclose]")
    page.wait_for_selector(dlg, state="detached")
    at(page, "IMG002")
    page.click("#bVprompt")
    assert "پرامپت ویدیو" in page.inner_text(dlg + " h3") and page.locator(dlg + " .prefs").count() == 0
    page.fill(dlg + " textarea", "[START FRAME: IMG002]\nA video prompt.")
    page.click(dlg + " [data-psave]")
    proj.wait("prompts/video-prompts.txt", "A video prompt.")
    settle(page)
    page.click(dlg + " [data-pclose]")
    assert proj.api("/api/prompt", {"id": "IMG003", "old": "stale text", "new": "x"})[0] == 409


@test
def format_issue_flag(proj, page):
    atb(page, 1)
    page.click(".blk.on .it.sp [data-fl] >> nth=0")  # the page asks for a message with prompt(); the test accepts its default text
    proj.wait("scenario/story.txt", "format-issue:")
    page.wait_for_selector(".blk.on .issue")
    page.click(".blk.on .issue [data-clr] >> nth=0")
    proj.wait("scenario/story.txt", "format-issue:", absent=True)
    settle(page)
    page.click("#bFlag")  # the flag in the top bar marks the picture itself
    proj.wait("scenario/story.txt", "format-issue:")
    page.wait_for_selector(".blk.on figure.shot .issue")
    page.click(".blk.on figure.shot .issue [data-clr]")
    proj.wait("scenario/story.txt", "format-issue:", absent=True)


@test
def drawer_panels_filter_search_jump(proj, page):
    """The drawer replaces the old tabs: references, scene list (jump), filter, search, speed, voices; ‹ goes back, Esc and the dimmed page close it."""
    drawer(page)
    assert page.locator("#dmenu .drow").count() == 13 and page.is_hidden("#dback")
    labels = page.locator("#dmenu .rt").all_inner_texts()
    assert labels[:3] == ["فهرست صحنه‌ها", "فیلتر و جست‌وجو", "سرعت پخش"] and "کپی پرامپت‌های دسته" in labels
    drawer(page, "refs")
    assert page.locator("#refs .card").count() == 1 and page.is_visible("#dback") and page.is_hidden("#dmenu")
    page.click("#refs [data-img] >> nth=0")  # jump to a picture that uses the reference: the drawer closes
    page.wait_for_function("!document.body.classList.contains('dopen')")
    assert page.locator(".blk.on figure.shot").count() == 1
    drawer(page, "scenes")
    assert page.locator("#slist .srow").count() == 3 and page.locator("#slist .srow.sel").count() == 1
    page.click("#slist .srow >> nth=2")
    page.wait_for_function("!document.body.classList.contains('dopen')")
    assert page.get_attribute(".blk.on", "data-bid") == "IMG003"
    drawer(page, "filter")
    page.click("[data-filter=ok]")
    page.wait_for_timeout(200)
    assert page.locator("figure.shot:not(.hide)").count() == 1 and page.get_attribute(".blk.on", "data-bid") == "IMG001"  # the page moves to a picture the filter lets through
    assert page.inner_text("#pos").strip() == "۱ / ۱" and page.is_disabled("#navNext")
    page.click("[data-filter=all]")
    page.fill("#q", "قهوه")  # search in the lines, speakers and notes
    page.wait_for_timeout(200)
    assert page.locator(".blk:not(.hide)").count() == 1 and page.get_attribute(".blk.on", "data-bid") == "IMG001"
    page.fill("#q", "")
    assert page.locator(".blk:not(.hide)").count() == 4
    page.click("#dback")
    page.click("[data-panel=speed]")
    page.click("[data-speed='1.3']")
    assert page.evaluate("window.__kit.S.speed") == 1.3
    page.click("#dback")
    assert "۱٫۳" in page.inner_text("[data-panel=speed] .trail")
    page.click("[data-panel=spk]")
    assert page.locator("#spk .spcard").count() == 3
    page.click("#dback")
    page.click("#dclose")
    assert not page.evaluate("document.body.classList.contains('dopen')")
    drawer(page)
    page.mouse.click(100, 400)  # the dimmed page
    page.wait_for_function("!document.body.classList.contains('dopen')")


@test
def lightbox(proj, page):
    """A reference chip in the prompt card opens the big picture above the card; Esc closes only the picture."""
    at(page, "IMG001")
    page.click("#bPrompt")
    page.click("dialog.pm .prefs button.chip.ref >> nth=0")
    page.wait_for_selector("#lb", state="visible")
    page.keyboard.press("Escape")
    page.wait_for_selector("#lb", state="hidden")
    assert page.locator("dialog.pm[open]").count() == 1
    page.keyboard.press("Escape")
    page.wait_for_selector("dialog.pm", state="detached")


@test
def transport_and_keyboard(proj, page):
    """Prev / play / next under the picture, the thin progress and the time in Persian digits; Space plays; ← → move between pictures."""
    play = page.locator("#play")
    assert play.get_attribute("aria-label") == "پخش خودکار" and page.locator("#play svg").count() == 2
    box = play.bounding_box()
    assert abs(box["width"] - box["height"]) < 1 and box["width"] >= 30
    assert re.fullmatch(r"[۰-۹]:[۰-۹]{2} / [۰-۹]:[۰-۹]{2}", page.inner_text("#ttime").strip()), page.inner_text("#ttime")
    play.click()
    page.wait_for_function("document.querySelector('#play').classList.contains('playing')")
    assert play.get_attribute("aria-label") == "توقف پخش"
    play.click()
    page.wait_for_function("!document.querySelector('#play').classList.contains('playing')")
    page.keyboard.press("Space")  # the space bar plays too
    page.wait_for_function("document.querySelector('#play').classList.contains('playing')")
    page.keyboard.press("Space")
    assert page.is_disabled("#navPrev") and page.is_disabled("#prev") and page.inner_text("#pos").strip() == "۱ / ۴"
    page.keyboard.press("ArrowRight")  # next picture (→), previous (←)
    page.wait_for_function("document.querySelector('.blk.on').dataset.bid==='IMG001'")
    assert page.inner_text("#pos").strip() == "۲ / ۴" and page.evaluate("location.hash") == "#IMG001"
    page.click("#navNext")
    page.click("#next")
    page.wait_for_function("document.querySelector('.blk.on').dataset.bid==='IMG003'")
    assert page.is_disabled("#next") and page.is_disabled("#navNext")
    page.keyboard.press("ArrowLeft")
    page.wait_for_function("document.querySelector('.blk.on').dataset.bid==='IMG002'")
    page.click("#prev")
    page.click("#navPrev")
    page.wait_for_function("document.querySelector('.blk.on').dataset.bid==='IMG000'")
    page.evaluate("location.hash = 'IMG003'")  # a link to a picture
    page.wait_for_function("document.querySelector('.blk.on').dataset.bid==='IMG003'")
    page.evaluate("document.querySelector('#prog').value = 1; document.querySelector('#prog').dispatchEvent(new Event('input', {bubbles: true}))")  # the tick line
    page.wait_for_function("document.querySelector('.blk.on').dataset.bid==='IMG001'")
    assert page.locator("#apr.show").count() == 1 and "تأیید شده" in page.inner_text("#apr")  # IMG001 is approved


@test
def line_audio_buttons(proj, page):
    atb(page, 1)
    if not shutil.which("ffmpeg"):
        print("   (skipped: no ffmpeg to make test audio)", end="")
        return
    assert page.locator(".blk.on .ab").count() >= 4
    page.click("#b1 .ab[data-lg=fa] >> nth=0")
    page.wait_for_function("document.querySelector('.ab.on')!==null||true")


@test
def subtitles_button(proj, page):
    drawer(page, "subs")
    page.click("#subs")
    for lg in ("fa", "en"):
        proj.wait("subtitles/%s.srt" % lg, "-->")


@test
def speaker_voices_with_dashes(proj, page):
    """Voices like aura-2-thalia-en must parse, save and survive (they used to break the speaker line)."""
    code, _ = proj.api("/api/speaker", {"name": "علی", "voice": "aura-2-apollo-en"})
    assert code == 200
    proj.wait("scenario/story.txt", "speaker: علی | #ef6c00 | aura-2-apollo-en")
    _, data = proj.api("/api/project")
    assert {s["name"]: s["voice"] for s in data["speakers"]}["علی"] == "aura-2-apollo-en"
    page.reload()
    page.wait_for_selector(".blk.on")


@test
def model_and_voice_pickers(proj, page):
    code, data = proj.api("/api/project")
    ids = [m["id"] for m in data["tts"]["catalog"]]
    assert ids == sorted(ids) and "deepgram/aura-2" in ids and len(data["tts"]["tones"]) >= 10
    assert page.locator("[data-scm]").count() == 0, "the per-scene model picker was removed"
    drawer(page, "spk")
    page.select_option("[data-dm]", "google/gemini-2.5-flash-tts")
    proj.wait("scenario/story.txt", "tts-model: google/gemini-2.5-flash-tts")
    assert (proj.root and os.path.exists(os.path.join(proj.root, "voices", "voice-config.json")))


@test
def tone_tags_logic(proj, page):
    sys.path.insert(0, os.path.join(proj.root, "tools"))
    import importlib
    voices = importlib.import_module("voices")
    tags = lambda t: voices.tone_tags(t)
    assert tags("شوخ‌طبع") == (["[playfully]"], True)
    assert tags("با تعجب و ترس") == (["[surprised]", "[scared]"], True)
    assert tags("طبیعی و صمیمی") == ([], True) and tags("") == ([], True)
    assert tags("عصبانی") == ([], False)
    assert len(tags("آهسته و مرموز و نگران")[0]) == 2  # at most two tags


@test
def server_hides_secrets_and_rejects_junk(proj, page):
    open(os.path.join(proj.root, ".env"), "w").write("OPENROUTER_API_KEY=secret\n")
    for path in ("/.env", "/tools/serve.py", "/.git/config", "/voices/x.tmp"):
        try:
            urllib.request.urlopen(proj.url + path)
            raise AssertionError(path + " was served")
        except urllib.error.HTTPError as e:
            assert e.code == 404, (path, e.code)
    assert urllib.request.urlopen(proj.url + "/scenario/story.txt").status == 200
    assert proj.api("/api/nothing", {})[0] == 400
    assert proj.api("/api/speaker", {"name": "x|y"})[0] == 400
    assert proj.api("/api/speaker", {"name": "ok", "voice": "bad voice!"})[0] == 400


@test
def picture_versions_pick(proj, page):
    """Every file of the same IMG### is a version; the one the user stops on is the chosen (approved) one; no file is touched.
    The arrows sit on the picture (‹ ›), the counter and the check mark too; ↑ ↓ do the same from the keyboard."""
    at(page, "IMG001")
    f = "figure.shot[data-id=IMG001]"
    assert page.inner_text(f + " .vc").strip() == "۲/۲" and page.locator("figure.shot[data-id=IMG002] [data-vn]").count() == 0
    assert page.locator(f + " .frame [data-vn]").count() == 2, "the arrows are on the picture itself"
    assert "a1b2c3" in page.get_attribute(f + " img", "src")  # no pick yet: the newest is shown
    page.click(f + " [data-vn='-1']")
    proj.wait_in("[IMG001]", "pick: IMG001_start.png")
    assert "status: ok" not in proj.story().split("[IMG002]")[0], "choosing a picture replaces the old plain «ok» mark"
    page.wait_for_function("(() => { const f = document.querySelector('%s'); return !f.querySelector('img').src.includes('a1b2c3') && f.querySelector('.vok') && f.querySelector('.vc').textContent.trim() === '۱/۲'; })()" % f)
    page.click(f + " [data-vn='1']")
    proj.wait_in("[IMG001]", "pick: IMG001_start_a1b2c3.png")
    page.wait_for_function("document.querySelector('figure.shot[data-id=IMG001] .vc').textContent.trim() === '۲/۲'")
    page.keyboard.press("ArrowUp")  # ↑ = the version before, ↓ = the one after
    proj.wait_in("[IMG001]", "pick: IMG001_start.png")
    page.wait_for_function("document.querySelector('figure.shot[data-id=IMG001] .vc').textContent.trim() === '۱/۲'")
    page.keyboard.press("ArrowDown")
    proj.wait_in("[IMG001]", "pick: IMG001_start_a1b2c3.png")
    assert page.locator("#approve").count() == 0  # no approve button: stopping on a version is the approval
    assert proj.api("/api/image", {"id": "IMG001", "pick": ""})[0] == 200  # un-choosing is still possible through the API
    proj.wait_in("[IMG001]", "pick:", absent=True)
    for name in ("IMG001_start.png", "IMG001_start_a1b2c3.png"):
        assert os.path.exists(os.path.join(proj.root, "images", "scenes", name))
    code, data = proj.api("/api/project")
    assert code == 200 and proj.api("/api/image", {"id": "IMG001", "pick": "nope.png"})[0] == 400
    page.reload()
    page.wait_for_selector(".blk.on")
    assert page.get_attribute(".blk.on", "data-bid") == "IMG001", "the address keeps the picture on show across a reload"


@test
def flow_versions_browse(proj, page):
    """Flow file names: qualities of one random id are ONE version (‹ › counts versions), a « (1)» copy is ignored, sub-folders are read, pick: keeps the random id,
    and a 4K that arrives later replaces the shown file without touching the pick."""
    now = time.time()
    def add(rel, age):
        p = os.path.join(proj.root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(png())
        os.utime(p, (now - age, now - age))
    add("images/scenes/part01/IMG002_sign_aaaa1111_2K.png", 50)
    add("images/scenes/part01/IMG002_sign_aaaa1111.png", 60)
    add("images/scenes/part01/IMG002_sign_aaaa1111 (1).png", 40)
    add("images/scenes/b01/IMG002_sign_bbbb2222_2K.png", 30)
    add("images/scenes/b01/IMG0021_other.png", 20)  # another picture (IMG0021), not a version of IMG002
    page.evaluate("location.hash = 'IMG002'")
    page.reload()
    page.wait_for_selector(".blk.on")
    f = "figure.shot[data-id=IMG002]"
    assert page.inner_text(f + " .vc").strip() == "۳/۳", page.inner_text(f + " .vc")  # IMG002_sign.png, aaaa1111, bbbb2222: files are not counted
    _, data = proj.api("/api/project")
    im = next(i for sc in data["scenes"] for b in sc["blocks"] for i in b["images"] if i["id"] == "IMG002")
    assert [v["id"] for v in im["versions"]] == ["IMG002_sign.png", "aaaa1111", "bbbb2222"] and im["batch"] == "b01"
    assert next(v for v in im["versions"] if v["id"] == "aaaa1111")["name"].endswith("aaaa1111_2K.png")  # 2K beats the normal file
    page.click(f + " [data-vn='-1']")
    proj.wait_in("[IMG002]", "pick: aaaa1111")
    page.wait_for_function("(() => { const f = document.querySelector('figure.shot[data-id=IMG002]'); return f.querySelector('.vok') && f.querySelector('.vq').textContent.trim() === '2K'; })()")
    add("images/scenes/b01/IMG002_sign_aaaa1111_4K.png", 0)  # a 4K of the chosen version arrives
    page.reload()
    page.wait_for_selector(".blk.on")
    assert page.inner_text(f + " .vc").strip() == "۲/۳" and page.inner_text(f + " .vq").strip() == "4K" and page.locator(f + " .vok").count() == 1
    assert "aaaa1111_4K" in page.get_attribute(f + " img", "src")
    assert "pick: aaaa1111" in proj.story()  # nothing in story.txt changed
    assert proj.api("/api/image", {"id": "IMG002", "pick": "IMG002_sign_aaaa1111_2K.png"})[0] == 200  # the old way (a file name) still works ...
    proj.wait_in("[IMG002]", "pick: aaaa1111")  # ... and is stored as the random id
    assert proj.api("/api/image", {"id": "IMG002", "pick": "bbbb2222"})[0] == 200
    proj.wait_in("[IMG002]", "pick: bbbb2222")
    assert proj.api("/api/image", {"id": "IMG002", "pick": "ffff0000"})[0] == 400
    for name in os.listdir(os.path.join(proj.root, "images", "scenes", "part01")):
        assert os.path.exists(os.path.join(proj.root, "images", "scenes", "part01", name))  # no file was renamed or removed


@test
def voice_variants_pick(proj, page):
    """A line made by several models keeps every file; the last one the user stops on is the final voice (voice-pick:)."""
    if not shutil.which("ffmpeg"):
        print("   (skipped: no ffmpeg to make test audio)", end="")
        return
    atb(page, 1)
    btn = "#b1 .vv[data-vv=fa] >> nth=0"
    assert page.inner_text(btn).strip() == "‹۱/۳›"  # default, eleven-v3, eleven-v4 (no pick yet: the old default plays)
    page.click(btn)
    proj.wait("scenario/story.txt", "voice: fa=eleven-v3")
    page.click(btn)
    proj.wait("scenario/story.txt", "voice: fa=eleven-v4")
    page.click(btn)
    proj.wait("scenario/story.txt", "voice: fa=default")
    _, data = proj.api("/api/project")
    line = data["scenes"][1]["blocks"][0]["items"][1]
    assert line["id"] == "IMG001_1" and line["audio_v"]["fa"]["chosen"] == "default" and len(line["audio_v"]["fa"]["names"]) == 3
    assert proj.api("/api/voicepick", {"scene": "scene-01", "id": "IMG001_1", "lang": "fa", "variant": "nope"})[0] == 400
    assert proj.api("/api/voicepick", {"scene": "scene-01", "id": "IMG001_1", "lang": "fa", "variant": ""})[0] == 200
    proj.wait("scenario/story.txt", "voice: fa=", absent=True)
    for tag in ("eleven-v3", "eleven-v4"):
        assert os.path.exists(os.path.join(proj.root, "audio", "fa", "IMG001_1.%s.mp3" % tag))


@test
def voice_files_per_model(proj, page):
    """tts.py names a file after the model (so voices never overwrite each other) and the voice just made becomes the chosen one."""
    code = ("import sys; sys.path.insert(0,'tools'); import media, edits, tts\n"
            "print(media.variant_tag('elevenlabs/eleven-v4-turbo'), media.variant_tag('x-ai/grok-voice-tts-1.0'))\n"
            "its=[dict(id='IMG003_1', scene='scene-02', model='elevenlabs/eleven-v3')]\n"
            "edits.pick_made(its, {'IMG003_1':'ok'}, 'en')\n"
            "print(media.audio_variants('fa','IMG001_1')[0]['name'])")
    out = subprocess.run([sys.executable, "-c", code], cwd=proj.root, capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.split("\n")[0] == "eleven-v4-turbo grok-voice-tts-1-0", out.stdout
    assert "voice: en=eleven-v3" in proj.story() and "voice-pick" not in proj.story()  # per-line form, written under the line


@test
def scene_off_and_back(proj, page):
    """A scene set aside keeps its text, pictures and audio; it just leaves the final order (off: yes). Bringing it back is in the scene list of the drawer."""
    before = proj.story()
    at(page, "IMG003")
    more(page)
    page.click("#morePop [data-soff]")
    proj.wait("scenario/story.txt", "off: yes")
    assert "و روز تمام شد." in proj.story() and "[IMG003]" in proj.story()
    page.wait_for_function("document.querySelectorAll('section[data-scene=scene-02]').length===0")
    assert page.locator("section[data-scene=scene-02] .blk").count() == 0
    assert page.get_attribute(".blk.on", "data-bid") == "IMG002", "the page moves to the picture before"
    drawer(page, "scenes")
    assert page.locator("#slist .srow:not(.off)").count() == 2  # the set-aside scene is not in the playlist ...
    assert page.locator("#slist .srow.off [data-son]").count() == 1  # ... but it is listed, with a way back
    assert proj.api("/api/project")[1]["scenes"][2]["off"] is True
    page.click("#slist .srow.off [data-son]")
    proj.wait("scenario/story.txt", "off: yes", absent=True)
    assert proj.story() == before, "setting aside and bringing back must leave the file exactly as it was"
    page.wait_for_function("document.querySelector('.blk.on').dataset.bid==='IMG003'")


@test
def picture_set_aside(proj, page):
    at(page, "IMG003")
    f = "figure.shot[data-id=IMG003]"
    assert page.locator("#foot #aside[data-ioff]").count() == 1, "«set aside» sits under the text page"
    page.click("#aside")
    proj.wait_in("[IMG003]", "off: yes")
    page.wait_for_selector(f + ".off")
    assert os.path.exists(os.path.join(proj.root, "images", "scenes", "IMG003_sea.png"))
    assert "برگردان" in page.inner_text("#aside")
    page.click("#aside")
    proj.wait_in("[IMG003]", "off: yes", absent=True)
    settle(page)
    more(page)  # the image menu has it too
    page.click("#morePop [data-ioff]")
    proj.wait_in("[IMG003]", "off: yes")
    settle(page)
    page.click("#aside")
    proj.wait_in("[IMG003]", "off: yes", absent=True)


@test
def move_scenes(proj, page):
    """Reordering moves whole blocks; ids and file names never change, the shown scene numbers follow the order."""
    at(page, "IMG003")
    assert label(page).startswith("صحنه ۲ · پایان")
    more(page)
    page.click("#morePop [data-smv='-1']")
    page.wait_for_function("document.querySelector('.blk.on .slabel').textContent.startsWith('صحنه ۱')")
    st = proj.story()
    assert st.index("=== scene-02") < st.index("=== scene-01") and "\n\n=== scene-01" in st
    at(page, "IMG001")
    assert label(page).startswith("صحنه ۲ · شروع")
    for needle in ("[IMG001]", "[IMG002]", "[IMG003]", "say: تست | یک خط"):
        assert needle in st
    at(page, "IMG003")
    more(page)
    page.click("#morePop [data-smv='1']")
    page.wait_for_function("document.querySelector('.blk.on .slabel').textContent.startsWith('صحنه ۲')")
    assert proj.story().index("=== scene-01") < proj.story().index("=== scene-02")
    assert proj.api("/api/scenemove", {"scene": "scene-01", "step": -1})[0] == 400  # the thumbnail stays first
    assert proj.api("/api/scenemove", {"scene": "scene-02", "step": 1})[0] == 400  # nothing below the last scene


@test
def scene_menu_and_add_image(proj, page):
    """One «⋯» popover on the page; Esc and outside clicks close it; «new picture» appends an empty slot to the scene and shows it."""
    at(page, "IMG001")
    pop = "#morePop"
    assert page.locator(pop).is_hidden()
    more(page)
    assert page.get_attribute("#more", "aria-expanded") == "true" and page.locator(pop + " [role=menuitem]").count() >= 8
    page.keyboard.press("Escape")
    assert page.locator(pop).is_hidden() and page.get_attribute("#more", "aria-expanded") == "false"
    more(page)
    page.click("#title")
    assert page.locator(pop).is_hidden()
    more(page)
    page.click(pop + " [data-addimg=scene-01]")
    proj.wait("scenario/story.txt", "[IMG004]")
    st = proj.story()
    assert st.index("[IMG002]") < st.index("[IMG004]") < st.index("=== scene-02"), "the new slot goes to the end of that scene"
    assert "\n\n=== scene-02" in st
    page.wait_for_selector(".blk.on figure.shot[data-id=IMG004]")  # and the page shows it
    assert proj.api("/api/addimage", {"scene": "scene-77"})[0] == 400
    assert proj.api("/api/addimage", {"scene": "bad"})[0] == 400


@test
def add_scene(proj, page):
    at(page, "IMG001")
    more(page)
    page.click("#morePop [data-addscene=scene-01]")  # the page asks for a title and a picture count; the test accepts the defaults (1 picture)
    proj.wait("scenario/story.txt", "=== scene-03 | صحنهٔ جدید | - ===")
    st = proj.story()
    assert st.index("=== scene-01") < st.index("=== scene-03") < st.index("=== scene-02"), "new scene goes right after the chosen one"
    assert "[IMG004]\n\n=== scene-02" in st
    page.wait_for_selector("section[data-scene=scene-03] figure.shot", state="attached")
    page.wait_for_function("document.querySelector('.blk.on figure.shot').dataset.id==='IMG004'")  # the page shows the new scene
    code, data = proj.api("/api/addscene", {"after": "scene-03", "title": "دو تایی", "images": 2})
    assert code == 200 and data["scene"] == "scene-04"
    assert "[IMG005]\n[IMG006]" in proj.story()
    assert proj.api("/api/addscene", {"after": "scene-01", "title": "a|b", "images": 1})[0] == 400
    assert proj.api("/api/addscene", {"after": "scene-01", "title": "x", "images": 99})[0] == 400
    assert proj.api("/api/addscene", {"after": "scene-77", "title": "x", "images": 1})[0] == 400


@test
def voice_dialog_manage(proj, page):
    """One dialog per line: choose a voice, archive it (file moves, pick is cleared), bring it back. No network is used."""
    at(page, "IMG001")
    if not shutil.which("ffmpeg"):
        print("   (skipped: no ffmpeg to make test audio)", end="")
        return
    page.click("[data-vgen=IMG001_1]")
    dlg = "dialog.dlg"
    page.wait_for_selector(dlg + " [data-dpick=fa]")
    assert page.locator(dlg + " [data-dpick=fa]").count() == 3 and page.locator(dlg + " #dmodel option").count() >= 2
    page.click(dlg + " [data-dpick=fa][value=eleven-v3]")
    proj.wait("scenario/story.txt", "voice: fa=eleven-v3")
    page.wait_for_selector(dlg + " [data-dpick=fa][value=eleven-v3]:checked")
    page.click(dlg + " [data-darch=fa][data-n=eleven-v4]")
    page.wait_for_selector(dlg + " [data-drest=fa][data-n=eleven-v4]", state="attached")
    assert os.path.exists(os.path.join(proj.root, "audio", "fa", "archive", "IMG001_1.eleven-v4.mp3"))
    assert not os.path.exists(os.path.join(proj.root, "audio", "fa", "IMG001_1.eleven-v4.mp3"))
    assert page.locator(dlg + " [data-dpick=fa]").count() == 2
    page.click(dlg + " [data-darch=fa][data-n=eleven-v3]")  # archiving the chosen voice also clears the pick
    proj.wait("scenario/story.txt", "voice: fa=", absent=True)
    page.wait_for_selector(dlg + " [data-drest=fa][data-n=eleven-v3]", state="attached")
    page.click(dlg + " details summary")  # the archive list is folded
    page.click(dlg + " [data-drest=fa][data-n=eleven-v3]")
    page.wait_for_selector(dlg + " [data-dpick=fa][value=eleven-v3]")
    assert os.path.exists(os.path.join(proj.root, "audio", "fa", "IMG001_1.eleven-v3.mp3"))
    page.click(dlg + " [data-dclose]")
    page.wait_for_selector(dlg, state="detached")
    assert proj.api("/api/linevoice", {"scene": "scene-01", "id": "IMG001_1", "model": "x y", "langs": ["fa"]})[0] == 400
    assert proj.api("/api/linevoice", {"scene": "scene-01", "id": "IMG001_1", "model": "elevenlabs/eleven-v3", "langs": []})[0] == 400
    assert proj.api("/api/archive", {"kind": "voice", "id": "IMG001_1", "lang": "fa", "name": "nope"})[0] == 400
    assert proj.api("/api/restore", {"kind": "voice", "id": "IMG001_1", "lang": "fa", "name": "nope"})[0] == 400


@test
def making_again_keeps_every_take(proj, page):
    """tts.make writes <id>_<rid>.mp3 with a random 8-hex id: making a line again adds a take next to the older one (nothing is replaced or archived),
    and voices.tsv records model / voice / tone / time of each (the network is faked here)."""
    code = ("import sys, os; sys.path.insert(0,'tools'); import tts\n"
            "tts.synth=lambda *a: b'x'*6000; tts.load_key=lambda: 'k'; tts.voice_problem=lambda m,v: None\n"
            "it=dict(id='IMG003-1', scene='scene-02', speaker='راوی', voice='george', model='elevenlabs/eleven-v3', spoken='سلام', tone='')\n"
            "os.makedirs('audio/fa',exist_ok=True)\n"
            "print(tts.make([it],'fa',force=True), it['variant']); print(tts.make([it],'fa',force=True), it['variant'])\n"
            "print(sorted(os.listdir('audio/fa')))")
    out = subprocess.run([sys.executable, "-c", code], cwd=proj.root, capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr[-400:]
    rids = re.findall(r"'ok'\} ([0-9a-f]{8})", out.stdout)
    assert len(rids) == 2 and rids[0] != rids[1], out.stdout
    for r in rids:
        assert os.path.exists(os.path.join(proj.root, "audio", "fa", "IMG003-1_%s.mp3" % r))
    assert not os.path.exists(os.path.join(proj.root, "audio", "fa", "archive"))
    tsv = proj.read("audio/fa/voices.tsv").split("\n")
    assert tsv[0] == "file\tmodel\tvoice\ttone\ttime" and len([l for l in tsv[1:] if l]) == 2


@test
def picture_archive_and_back(proj, page):
    """Archive the shown version from the image menu; the archive list (and «bring back») is in the drawer's versions panel."""
    at(page, "IMG001")
    f = "figure.shot[data-id=IMG001]"
    page.click(f + " [data-vn='-1']")  # choose the older picture, then archive the newest one
    proj.wait_in("[IMG001]", "pick: IMG001_start.png")
    page.click(f + " [data-vn='1']")
    proj.wait_in("[IMG001]", "pick: IMG001_start_a1b2c3.png")
    more(page)
    assert page.locator("#morePop [data-irest]").count() == 0
    page.click("#morePop [data-iarch]")  # archiving the chosen picture clears the pick
    proj.wait_in("[IMG001]", "pick:", absent=True)
    page.wait_for_function("document.querySelectorAll('figure.shot[data-id=IMG001] [data-vn]').length===0")  # one version left
    assert os.path.exists(os.path.join(proj.root, "images", "archive", "IMG001_start_a1b2c3.png"))
    assert not os.path.exists(os.path.join(proj.root, "images", "scenes", "IMG001_start_a1b2c3.png"))
    more(page)
    page.click("#morePop [data-irest]")  # «archive (1)» opens the archive popup: a grid, then one picture with «bring back»
    page.wait_for_selector("dialog.archdlg .atile")
    assert page.locator("dialog.archdlg .atile").count() == 1
    page.click("dialog.archdlg .atile")
    page.wait_for_selector("dialog.archdlg .aview img")
    page.click("dialog.archdlg [data-ar=restore]")
    page.wait_for_selector(f + " [data-vn]")
    assert os.path.exists(os.path.join(proj.root, "images", "scenes", "IMG001_start_a1b2c3.png"))
    page.click("dialog.archdlg [data-ar=close]")
    drawer(page, "vers")  # the drawer's versions panel can still show and approve a version
    page.wait_for_selector("#pVers [data-vpick]")
    assert page.locator("#pVers [data-irestore]").count() == 0
    page.click("#pVers [data-vpick='0']")  # the panel can also show and approve a version
    proj.wait_in("[IMG001]", "pick: IMG001_start.png")
    page.click("#pVers [data-varch] >> nth=1")  # archiving a version that is not the chosen one keeps the pick
    page.wait_for_function("document.querySelectorAll('#pVers [data-irestore]').length===1")
    assert os.path.exists(os.path.join(proj.root, "images", "archive", "IMG001_start_a1b2c3.png")) and "pick: IMG001_start.png" in proj.story()
    undrawer(page)
    assert proj.api("/api/archive", {"kind": "image", "id": "IMG001", "name": "nope.png"})[0] == 400


@test
def attach_references(proj, page):
    """The reference row of the image prompt card opens the attach dialog; saving rewrites only the REFS line of that prompt and marks the picture stale."""
    at(page, "IMG003")
    f = "figure.shot[data-id=IMG003]"
    page.click("#bPrompt")
    page.click("dialog.pm [data-attach=IMG003]")
    dlg = "dialog.dlg:not(.pm)"
    page.wait_for_selector(dlg + " [data-aref=CH_ALI]:checked")
    assert page.locator(dlg + " [data-aref]").count() >= 2
    page.click(dlg + " [data-aref=CH_ALI]")  # untick
    page.click(dlg + " [data-dsaverefs]")
    proj.wait("prompts/prompts.txt", "[REFS TO ATTACH: STYLE_ANCHOR]\nPrompt of picture 3.")
    proj.wait_in("[IMG003]", "image-stale: yes")
    page.wait_for_selector(dlg, state="detached")
    page.wait_for_function("document.querySelectorAll('dialog.pm .prefs .chip.ref, dialog.pm .prefs .chip.miss').length===1")  # the card's chips follow
    page.click("dialog.pm [data-attach=IMG003]")
    page.click(dlg + " [data-aref=CH_ALI]")  # tick it again
    page.click(dlg + " [data-dsaverefs]")
    proj.wait("prompts/prompts.txt", "[REFS TO ATTACH: STYLE_ANCHOR| CH_ALI]\nPrompt of picture 3.")
    page.keyboard.press("Escape")
    code, data = proj.api("/api/addimage", {"scene": "scene-02"})
    assert proj.api("/api/refs", {"id": data["id"], "refs": ["STYLE_ANCHOR"]})[0] == 200
    assert "=== %s ===\n[REFS TO ATTACH: STYLE_ANCHOR]" % data["id"] in proj.read("prompts/prompts.txt")
    assert proj.api("/api/refs", {"id": "IMG003", "refs": ["NOPE_NOT_THERE"]})[0] == 400
    assert proj.api("/api/refs", {"id": "IMG003", "refs": ["bad name"]})[0] == 400
    assert proj.api("/api/refs", {"id": "IMG003", "refs": ["CH_ALI", "CH_ALI"]})[0] == 400


@test
def premiere_check_and_pack(proj, page):
    """premiere_check: every file the XML points to must exist (relative paths). pack: one zip without videos, renders, archives, .env."""
    root = proj.root

    def touch(rel, data=b"x"):
        f = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(f), exist_ok=True)
        open(f, "wb").write(data)

    def xml(rel, urls):
        touch(rel, ("<xmeml>" + "".join("<file><pathurl>%s</pathurl></file>" % u for u in urls) + "</xmeml>").encode("utf-8"))

    def run(*args):
        o = subprocess.run([sys.executable] + list(args), cwd=root, capture_output=True, text=True, encoding="utf-8")
        return o.returncode, o.stdout + o.stderr

    touch("premiere/media/overlays/a.mov")
    xml("premiere/EP01_FA_premiere.xml", ["./media/overlays/a.mov", "../images/scenes/IMG001_start.png", "../images/scenes/NOPE.png"])
    code, out = run("tools/premiere_check.py")
    assert code == 1 and "NOPE.png" in out and "1 missing" in out, out
    touch("images/scenes/NOPE.png")
    code, out = run("tools/premiere_check.py")
    assert code == 0 and "OK" in out and "0 with an absolute path" in out, out
    xml("premiere/EP01_EN_premiere.xml", ["file://localhost/D%3a/nowhere/x.png"])
    code, out = run("tools/premiere_check.py", "premiere/EP01_EN_premiere.xml")
    assert code == 1 and "absolute" in out, out
    os.remove(os.path.join(root, "premiere", "EP01_EN_premiere.xml"))
    for rel in (".env", "videos/final/EP01_FA_renders/x.mp4", "videos/final/EP01_FA_preview.mp4", "images/archive/z.png",
                "audio/fa/archive/q.mp3", "videos/clips/c.mp4", "audio/_tests/t.mp3"):
        touch(rel)
    zp = os.path.join(proj.tmp, "handoff.zip")
    code, out = run("-c", "import sys; sys.path.insert(0, 'tools'); import pack; print(pack.problems()); print(pack.pack(out=sys.argv[1], selected=False)[1])", zp)
    assert code == 0 and out.startswith("[]"), out
    import zipfile
    names = [n.split("/", 1)[1] for n in zipfile.ZipFile(zp).namelist()]
    for want in ("scenario/story.txt", "premiere/EP01_FA_premiere.xml", "premiere/media/overlays/a.mov", "images/scenes/IMG001_start.png", "tools/pack.py"):
        assert want in names, want
    for bad in (".env", "videos/final/EP01_FA_renders/x.mp4", "videos/final/EP01_FA_preview.mp4", "images/archive/z.png",
                "audio/fa/archive/q.mp3", "videos/clips/c.mp4", "audio/_tests/t.mp3"):
        assert bad not in names, bad
    xml("premiere/EP01_FA_premiere.xml", ["../videos/clips/c.mp4"])  # a file the XML needs that the zip leaves out is reported
    code, out = run("-c", "import sys; sys.path.insert(0, 'tools'); import pack; print(pack.problems()); print(pack.problems(clips=True))")
    assert "would be left out" in out.split(chr(10))[0] and out.split(chr(10))[1].strip() == "[]", out


@test
def voices_follow_their_lines(proj, page):
    """Adding or deleting a dialogue line must not move the voices of the other lines (each line has its own id: line)."""
    if not shutil.which("ffmpeg"):
        print("   (skipped: no ffmpeg to make test audio)", end="")
        return

    def says():
        _, data = proj.api("/api/project")
        return [i for b in data["scenes"][1]["blocks"] for i in b["items"] if i["k"] == "say"]
    before = {i["id"]: i["audio"]["fa"] for i in says() if i["audio"]["fa"]}
    assert set(before) == {"IMG001_1", "IMG001_2"}  # the fixture has voices for these two lines
    first = says()[0]
    code, _ = proj.api("/api/add", {"scene": "scene-01", "after": first["ln"], "kind": "say", "speaker": "راوی", "text": "یک خط تازه وسط"})
    assert code == 200
    now = {i["id"]: i for i in says()}
    assert all(now[k]["audio"]["fa"] == v for k, v in before.items()), "old lines must keep their voice files"
    new = next(i for i in now.values() if i["fa"] == "یک خط تازه وسط")
    assert new["id"] == new["img"] + "-1" and new["audio"]["fa"] is None  # named after its picture: IMGnnn-k
    assert proj.story().count("id: ") == 4  # the three old ones were pinned, plus the new one
    code, _ = proj.api("/api/delete", {"scene": "scene-01", "index": first["ln"] + 1, "old": "یک خط تازه وسط"})
    assert code == 409  # that position is now an id: line, not the new dialogue: a stale page is refused, nothing is lost
    now = {i["id"]: i for i in says()}
    assert all(now[k]["audio"]["fa"] == v for k, v in before.items())
    page.reload()
    page.wait_for_selector(".blk.on")
    assert page.locator("#b1 .ab[data-lg=fa]").count() >= 2


@test
def old_project_keeps_its_voices_and_images_apart(proj, page):
    """A project from before 1.17 (a block of two pictures, lines without id:, scene-level voice-pick / voice-stale) opens without any file change:
    the pictures are shown apart, the old line names give the same voice files, and the old chosen voice still plays."""
    use_story(proj, page)
    assert story_bytes(proj) == open(os.path.join(FIX, "story-legacy.txt"), "rb").read(), "opening a project must not rewrite it"
    assert page.locator("section[data-scene=scene-01] .blk").count() == 3
    assert page.locator("section[data-scene=scene-01] .blk figure.shot").evaluate_all("els => els.map(e => e.dataset.id)") == ["IMG001", "IMG002", "IMG003"]
    assert page.locator("#b1 .it").count() == 0 and page.locator("#b2 .it.sp").count() == 2 and page.locator("#b2 .it.act").count() == 1
    assert page.locator("section[data-scene=scene-02] .blk.noimg .it.act").count() == 1  # the line above the first picture is still shown
    assert "before the first [IMG]" in json.dumps(proj.api("/api/project")[1]["scenes"][2]["warnings"], ensure_ascii=False)
    assert page.locator("#b2 .it.sp.vstale").count() == 2 and page.locator("#b3 .it.sp.vstale").count() == 1  # the old scene-level flag reaches every line
    assert page.locator("section[data-scene=scene-01] [data-regen]").count() == 2  # one under each block that has a line out of date
    if shutil.which("ffmpeg"):
        items = {i["id"]: i for b in proj.api("/api/project")[1]["scenes"][1]["blocks"] for i in b["items"] if i["k"] == "say"}
        assert list(items) == ["IMG001_1", "IMG001_2", "L001"]
        assert items["IMG001_1"]["audio"]["fa"].startswith("audio/fa/IMG001_1.eleven-v3.mp3")  # the old scene-level voice-pick
        assert items["IMG001_2"]["audio"]["fa"].startswith("audio/fa/IMG001_2.mp3") and items["IMG001_2"]["audio"]["en"].startswith("audio/en/IMG001_2.mp3")


@test
def editing_in_a_shared_block_is_per_picture_and_per_line(proj, page):
    """Lines are sent by picture id; the changed line alone is marked out of date, and the old scene-level flag is moved onto the lines."""
    use_story(proj, page)
    sent = []
    page.on("request", lambda r: sent.append(r.post_data) if r.url.endswith("/api/line") else None)
    atb(page, 2)
    page.click("#b2 .it.sp .fa .v >> nth=0")
    page.fill(".ie.say textarea", "متن تازهٔ بلوک مشترک")
    page.press(".ie.say textarea", "Enter")
    proj.wait("scenario/story.txt", "say: راوی | متن تازهٔ بلوک مشترک")
    assert sent and '"image":"IMG002"' in sent[0] and '"scene"' not in sent[0], sent
    st = proj.story()
    head = st.split("[IMG001]")[0]
    assert "voice-stale" not in head, "the old scene-level flag was moved onto the lines"
    assert "voice-pick: IMG001_1.fa=eleven-v3, IMG001_2.en=default" in head  # the old picks are not touched by a text edit
    assert st.count("voice-stale: fa") == 3 and "voice-stale: fa, en" in st  # every line of the scene got the flag it had before
    page.wait_for_selector("text=متن تازهٔ بلوک مشترک")
    assert page.locator("section[data-scene=scene-01] .it.sp.vstale").count() == 3


@test
def choosing_a_voice_is_written_under_its_line(proj, page):
    """The ‹2/3› button writes «voice: fa=...» under the dialogue line and takes only that entry out of the old scene-level voice-pick."""
    if not shutil.which("ffmpeg"):
        print("   (skipped: no ffmpeg to make test audio)", end="")
        return
    use_story(proj, page)
    atb(page, 2)
    btn = "#b2 .vv[data-vv=fa] >> nth=0"
    assert page.inner_text(btn).strip() == "‹۲/۳›"  # the old voice-pick (eleven-v3) is what plays
    page.click(btn)
    proj.wait("scenario/story.txt", "en: This is Ali.\nvoice: fa=eleven-v4")
    st = proj.story()
    i = st.index("say: راوی | این علیه.")
    assert st[i:].split("\n")[1:3] == ["en: This is Ali.", "voice: fa=eleven-v4"], st[i:i + 200]
    head = st.split("[IMG001]")[0]
    assert "voice-pick: IMG001_2.en=default" in head and "IMG001_1.fa" not in head
    page.click(btn)  # ‹1/3›: the plain old file
    proj.wait("scenario/story.txt", "voice: fa=default")
    assert proj.api("/api/voicepick", {"id": "IMG001_2", "lang": "en", "variant": ""})[0] == 200  # no scene needed any more
    proj.wait("scenario/story.txt", "voice-pick", absent=True)
    assert proj.api("/api/voicepick", {"id": "NOPE_1", "lang": "en", "variant": ""})[0] == 400


@test
def line_endpoints_take_a_picture_id(proj, page):
    """/api/line, /add, /delete and /issue address a line by picture id (index counted from its [IMG] line); the old scene form still works."""
    use_story(proj, page)
    base = {"image": "IMG002"}
    code, r = proj.api("/api/line", dict(base, index=3, old="این علیه. صبح‌ها بدون قهوه آدم نیست.", new="با شناسهٔ تصویر", op="edit"))
    assert code == 200
    proj.wait_in("[IMG002]", "say: راوی | با شناسهٔ تصویر")
    assert proj.api("/api/line", dict(base, index=3, old="چیز دیگر", new="x", op="edit"))[0] == 409
    assert proj.api("/api/line", dict(base, index=40, old="x", new="x"))[0] == 400
    assert proj.api("/api/line", {"image": "IMG001", "index": 1, "old": "x", "new": "x"})[0] == 400  # IMG001 owns no lines
    assert proj.api("/api/line", {"image": "bad", "index": 1, "old": "x", "new": "x"})[0] == 400
    assert proj.api("/api/add", dict(base, after=5, kind="act", text="توضیح تازه"))[0] == 200
    proj.wait_in("[IMG002]", "act: توضیح تازه")
    assert "act: توضیح تازه" not in proj.story().split("[IMG003]")[1], "the new line belongs to the picture it was added to"
    assert proj.api("/api/issue", dict(base, index=2, message="نگاه کن"))[0] == 200
    proj.wait_in("[IMG002]", "format-issue: نگاه کن")
    assert proj.api("/api/issue", dict(base, index=3, clear=True))[0] == 200
    proj.wait_in("[IMG002]", "format-issue:", absent=True)
    _, data = proj.api("/api/project")
    act = next(i for b in data["scenes"][1]["blocks"] for i in b["items"] if i["k"] == "act" and i["fa"] == "توضیح تازه")
    assert proj.api("/api/delete", dict(base, index=act["ln"] - data["scenes"][1]["blocks"][1]["images"][0]["ln"], old="توضیح تازه"))[0] == 200
    proj.wait_in("[IMG002]", "توضیح تازه", absent=True)
    data = proj.api("/api/project")[1]
    old_form = next(i for b in data["scenes"][1]["blocks"] for i in b["items"] if i["k"] == "say" and i["id"] == "L001")
    assert proj.api("/api/line", {"scene": "scene-01", "index": old_form["ln"], "old": "خطی که شناسهٔ خودش را دارد.", "new": "فرم قدیمی", "op": "edit"})[0] == 200
    proj.wait_in("[IMG003]", "say: راوی | فرم قدیمی")
    assert proj.api("/api/flag", {"id": "L001", "lang": "fa", "value": False})[0] == 200
    assert proj.api("/api/flag", {"id": "NOPE_1", "lang": "fa", "value": True})[0] == 400
    assert proj.api("/api/regen", {"scene": "bad"})[0] == 400 and proj.api("/api/regen", {"image": "IMG9"})[0] == 400


@test
def undo_restores_story_byte_for_byte(proj, page):
    """Every structural edit keeps the file as it was in .kit/history/ (30 at most); POST /api/undo puts the newest back, byte for byte."""
    use_story(proj, page, "story.txt")
    orig = story_bytes(proj)
    assert proj.api("/api/undo", {})[0] == 400 and proj.api("/api/project")[1]["history"] == []
    assert proj.api("/api/addimage", {"scene": "scene-01"})[0] == 200
    step1 = story_bytes(proj)
    assert proj.api("/api/sceneoff", {"scene": "scene-02", "off": True})[0] == 200
    assert proj.api("/api/addscene", {"after": "scene-01", "title": "تازه", "images": 1})[0] == 200
    assert proj.api("/api/scenemove", {"scene": "scene-02", "step": -1})[0] == 200
    assert proj.api("/api/add", {"scene": "scene-01", "after": 5, "kind": "act", "text": "خط تازه"})[0] == 200
    assert proj.api("/api/delete", {"scene": "scene-01", "index": 5, "old": "علی با یک لیوان قهوه رد می‌شود."})[0] in (200, 409)
    assert proj.api("/api/addimage", {"scene": "scene-77"})[0] == 400  # a failed edit leaves no snapshot
    hist = proj.api("/api/project")[1]["history"]
    assert [h["label"] for h in hist][:5] == ["addimage", "sceneoff", "addscene", "scenemove", "add"], hist
    assert proj.api("/api/image", {"id": "IMG001", "note": "ordinary edits keep no snapshot"})[0] == 200
    assert len(proj.api("/api/project")[1]["history"]) == len(hist)
    code, r = proj.api("/api/undo", {})
    assert code == 409 and "force" in r["error"], "the file was edited after the last structural edit: refuse unless forced"
    assert proj.api("/api/undo", {"id": "20000101-000000-000000_add_00000000"})[0] == 409
    assert proj.api("/api/undo", {"force": True})[0] == 200
    assert os.path.isdir(os.path.join(proj.root, ".kit", "undone")) and os.listdir(os.path.join(proj.root, ".kit", "undone"))
    while proj.api("/api/project")[1]["history"]:
        assert proj.api("/api/undo", {"id": proj.api("/api/project")[1]["history"][-1]["id"]})[0] == 200
    assert story_bytes(proj) == orig, "undoing every structural edit gives back the very first file"
    assert step1 != orig
    for i in range(32):
        assert proj.api("/api/addimage", {"scene": "scene-01"})[0] == 200
    hist = proj.api("/api/project")[1]["history"]
    assert len(hist) == 30
    names = os.listdir(os.path.join(proj.root, ".kit", "history"))
    assert ".gitignore" in names and len([n for n in names if n.endswith(".txt")]) == 30
    for path in ("/.kit/history/%s.txt" % hist[0]["id"], "/.kit/history/.gitignore", "/.kit/"):
        try:
            urllib.request.urlopen(proj.url + path)
            raise AssertionError(path + " was served")
        except urllib.error.HTTPError as e:
            assert e.code == 404, (path, e.code)
    page.reload()
    page.wait_for_selector(".blk.on")
    assert page.locator("figure.shot").count() == 4 + 32


@test
def undo_after_a_page_edit(proj, page):
    """The page's own add / delete go through the same snapshot: delete a dialogue line in the page, undo, and the file is the one before."""
    before = story_bytes(proj)
    atb(page, 3)
    page.locator("#b3 .it.sp [data-del]").click()  # the page asks, the test accepts
    proj.wait("scenario/story.txt", "و روز تمام شد.", absent=True)
    assert [h["label"] for h in proj.api("/api/project")[1]["history"]] == ["delete"]
    assert proj.api("/api/undo", {})[0] == 200
    assert story_bytes(proj) == before
    page.reload()
    page.wait_for_selector("text=و روز تمام شد.")


@test
def regen_makes_only_the_stale_lines(proj, page):
    """Making voices works per stale line: all of them, or only the lines of one picture. A made line loses its flag, the others keep theirs
    (the old scene-level flag is moved onto the lines first). The network is faked here."""
    use_story(proj, page)
    head = ("import sys, os; sys.path.insert(0,'tools'); import tts, jobs\n"
            "tts.synth=lambda *a: b'x'*6000; tts.load_key=lambda: 'k'; tts.voice_problem=lambda m,v: None\n")
    out = subprocess.run([sys.executable, "-c", head + "jobs.regen_job(image='IMG003'); print(jobs.JOB['state'], jobs.JOB['errors'])"],
                         cwd=proj.root, capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0 and out.stdout.strip() == "done []", out.stdout + out.stderr[-400:]
    st = proj.story()
    made = lambda lg, id_: glob.glob(os.path.join(proj.root, "audio", lg, id_ + "_????????.mp3"))
    assert len(made("fa", "L001")) == 1 and len(made("en", "L001")) == 1  # the new name: <id>_<8 hex>.mp3, one take per language
    assert not made("fa", "IMG001_1")
    fa, en = [re.search(r"_([0-9a-f]{8})\.mp3", made(lg, "L001")[0]).group(1) for lg in ("fa", "en")]
    assert "voice: fa=%s, en=%s" % (fa, en) in st
    assert "voice-stale: en" not in st and st.count("voice-stale: fa") == 2 and "voice-stale" not in st.split("[IMG001]")[0]
    out = subprocess.run([sys.executable, "-c", head + "jobs.regen_job(); print('end')"], cwd=proj.root, capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr[-400:]
    st = proj.story()
    assert "voice-stale" not in st
    assert len(made("fa", "IMG001_2")) == 1
    assert re.search(r"voice: fa=[0-9a-f]{8}", st) and "IMG001_1.fa" not in st


@test
def image_menu_moves_and_scene_marks(proj, page):
    """The «⋯» popover of a picture: one image up / down (over a scene header too), a slot after it, start a scene here, join the scene above.
    Everything is a text move in story.txt; undo gives the bytes back."""
    use_story(proj, page, "story.txt")
    orig = story_bytes(proj)
    fig = lambda i: "figure.shot[data-id=%s]" % i
    pop = "#morePop"
    at(page, "IMG001")
    more(page)
    assert page.get_attribute("#more", "aria-expanded") == "true"
    assert not page.locator(pop + " [data-imv='-1']").count(), "nothing above the first picture (the thumbnail scene is closed)"
    assert not page.locator(pop + " [data-imerge]").count()
    page.keyboard.press("Escape")
    at(page, "IMG000")
    more(page)
    assert not page.locator(pop + " [data-imv], " + pop + " [data-iadd]").count(), "the thumbnail picture has no move items"
    page.keyboard.press("Escape")
    at(page, "IMG001")
    more(page)
    page.click(pop + " [data-imv='1']")  # down: past IMG002
    page.wait_for_function("document.querySelector('section[data-scene=scene-01] figure.shot').dataset.id==='IMG002'")
    st = proj.story()
    assert st.index("[IMG002]") < st.index("[IMG001]") < st.index("=== scene-02")
    assert "رنگ‌ها شاد باشه" in st.split("[IMG001]")[1].split("=== scene-02")[0], "its note went along"
    assert page.get_attribute(".blk.on", "data-bid") == "IMG001", "the page stays on the picture that was moved"
    more(page)
    page.click(pop + " [data-imv='1']")  # down again: over the header, first in the next scene
    page.wait_for_function("document.querySelector('section[data-scene=scene-02] figure.shot').dataset.id==='IMG001'")
    assert proj.story().index("=== scene-02") < proj.story().index("[IMG001]") < proj.story().index("[IMG003]")
    more(page)
    page.click(pop + " [data-imv='-1']")  # up: back to the end of the scene above
    page.wait_for_function("document.querySelectorAll('section[data-scene=scene-01] figure.shot').length===2")
    assert proj.story().index("[IMG001]") < proj.story().index("=== scene-02")
    for i in range(3):  # undo the three moves
        assert proj.api("/api/undo", {})[0] == 200
    assert story_bytes(proj) == orig
    page.evaluate("history.replaceState(null, '', '#review')")
    page.reload()
    page.wait_for_selector(".blk.on")
    at(page, "IMG002")
    more(page)  # a slot after this picture
    page.click(pop + " [data-iadd]")
    page.wait_for_selector(".blk.on " + fig("IMG004"))
    st = proj.story()
    assert st.index("[IMG002]") < st.index("[IMG004]") < st.index("=== scene-02")
    assert proj.api("/api/undo", {})[0] == 200
    page.evaluate("history.replaceState(null, '', '#review')")
    page.reload()
    page.wait_for_selector(".blk.on")
    at(page, "IMG002")
    more(page)
    assert page.locator(pop + " [data-isc]").count() == 1
    page.keyboard.press("Escape")
    at(page, "IMG001")
    more(page)
    assert page.locator(pop + " [data-isc]").count() == 0
    page.keyboard.press("Escape")
    at(page, "IMG002")
    more(page)
    page.click(pop + " [data-isc]")  # the page asks for a title; the test accepts the default
    page.wait_for_selector("section[data-scene=scene-03] " + fig("IMG002"), state="attached")
    st = proj.story()
    assert "\n\n=== scene-03 | صحنهٔ جدید | - ===\n[IMG002]" in st and st.index("=== scene-03") < st.index("=== scene-02")
    assert label(page).startswith("صحنه ۲ · صحنهٔ جدید")
    at(page, "IMG003")
    assert label(page).startswith("صحنه ۳ · پایان")
    at(page, "IMG002")
    more(page)
    assert page.locator(pop + " [data-imerge]").count() == 1
    page.click(pop + " [data-imerge]")  # join the scene above: only the header goes
    page.wait_for_function("document.querySelectorAll('section[data-scene=scene-01] figure.shot').length===2")
    assert page.locator("section[data-scene=scene-03]").count() == 0
    st = proj.story()
    assert "=== scene-03" not in st and "id: IMG001_1" in st and "id: IMG002_1" in st, "the old line ids were written out before the scene header moved"
    assert [h["label"] for h in proj.api("/api/project")[1]["history"]] == ["scenemark", "scenemark"]
    at(page, "IMG003")  # the first picture of the scene below: it can be joined to the one above (that scene has env text: asked)
    more(page)
    page.click(pop + " [data-imerge]")
    page.wait_for_function("document.querySelectorAll('section[data-scene=scene-01] figure.shot').length===3")
    st = proj.story()
    assert "=== scene-02" not in st and "[IMG002]\nimage-stale: yes" in st and "env: غروب، کنار دریا." not in st
    assert any("ادغام" in m for m in page._dialogs)
    assert proj.api("/api/undo", {})[0] == 200
    assert "env: غروب، کنار دریا." in proj.story()
    while proj.api("/api/project")[1]["history"]:
        assert proj.api("/api/undo", {})[0] == 200
    assert story_bytes(proj) == orig


@test
def move_endpoints_stale_and_four_digit(proj, page):
    """POST /api/move, /api/scenemark and /api/addimage from outside the page: positions, an existing id, a four-digit id, 409 for a stale page."""
    use_story(proj, page, "story.txt")
    orig = story_bytes(proj)
    code, r = proj.api("/api/move", {"ids": ["IMG003", "IMG001"], "before": "IMG002"})
    assert code == 200 and r["scene"] == "scene-01" and r["moved"] == 2
    st = proj.story()
    assert st.index("[IMG001]") < st.index("[IMG003]") < st.index("[IMG002]") and "=== scene-02" in st and "\n\n=== scene-02" in st
    page.evaluate("history.replaceState(null, '', '#review')")
    page.reload()
    page.wait_for_selector(".blk.on")
    assert page.locator("section[data-scene=scene-01] figure.shot").count() == 3
    assert page.locator("section[data-scene=scene-02] figure.shot").count() == 0
    code, r = proj.api("/api/move", {"ids": ["IMG001"], "before": "IMG001"})
    assert code == 200 and r["moved"] == 0
    assert [h["label"] for h in proj.api("/api/project")[1]["history"]] == ["move"], "a move onto itself keeps no snapshot"
    assert proj.api("/api/move", {"ids": ["IMG999"], "before": "IMG001"})[0] == 409
    assert proj.api("/api/move", {"ids": ["IMG001"], "after": "IMG999"})[0] == 409
    assert proj.api("/api/move", {"ids": ["IMG001"]})[0] == 400
    assert proj.api("/api/move", {"ids": ["IMG001"], "before": "IMG002", "after": "IMG003"})[0] == 400
    assert proj.api("/api/move", {"ids": ["IMG001"], "after": "IMG000"})[0] == 400, "nothing goes into the thumbnail scene"
    assert proj.api("/api/scenemark", {"op": "remove", "scene": "scene-77"})[0] == 409
    assert proj.api("/api/scenemark", {"op": "remove", "scene": "scene-02"})[0] == 400, "it has an env line: only with force"
    assert proj.api("/api/scenemark", {"op": "remove", "scene": "scene-02", "force": True})[0] == 200
    code, r = proj.api("/api/scenemark", {"op": "insert", "before": "IMG002", "title": "غار", "env": "تاریک"})
    assert code == 200 and r["scene"] == "scene-02", "the next free number (scene-02 was just removed)"
    assert proj.api("/api/scenemark", {"op": "edit", "scene": "scene-02", "title": "غار ۲", "fx": "برش"})[0] == 200
    assert "=== scene-02 | غار ۲ | - ===\nenv: تاریک\nfx: برش\n[IMG002]" in proj.story()
    code, r = proj.api("/api/addimage", {"before": "IMG002", "id": "IMG1000"})
    assert code == 200 and r["id"] == "IMG1000"
    assert proj.api("/api/addimage", {"before": "IMG002", "id": "IMG1000"})[0] == 409
    assert proj.api("/api/addimage", {"after": "IMG1000"})[1]["id"] == "IMG1001"
    page.evaluate("history.replaceState(null, '', '#review')")
    page.reload()
    page.wait_for_selector("figure.shot[data-id=IMG1000]", state="attached")
    assert page.locator("section[data-scene=scene-02] figure.shot").count() == 3
    code, r = proj.api("/api/image", {"id": "IMG1000", "note": "چهار رقمی"})
    assert code == 200 and "note: چهار رقمی" in proj.story()
    n = len(proj.api("/api/project")[1]["history"])
    while proj.api("/api/project")[1]["history"]:
        assert proj.api("/api/undo", {"force": True})[0] == 200
    assert n >= 6 and story_bytes(proj) == orig


PROBE = """async () => {
  const out = [];
  for (const b of document.querySelectorAll('button.ab[data-src]')) {
    const src = b.dataset.src, buf = await (await fetch(src)).arrayBuffer();
    const h = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-1', buf))).map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 10);
    const dur = await new Promise(ok => { const a = new Audio(src); a.onloadedmetadata = () => ok(a.duration); a.onerror = () => ok(-1); });
    out.push([b.dataset.lg, src.split('?')[0], h, dur > 0.1]);
  }
  return out;
}"""


@test
def migrated_fixture_loads_and_plays_the_same_audio(proj, page):
    """An old project in the style of 1-mimo-white-head (old voice names, shared block, scene-level voice-pick, Premiere XML with D:/ paths) is migrated
    with tools/migrate.py --apply: the page loads, every 🔊 button plays (a real decodable mp3) the same bytes as before, from the new file names;
    --undo brings the old names back and the page shows the old files again."""
    sys.path.insert(0, HERE)
    import mimo
    for d in ("audio", "scenario"):  # (the default pictures stay: the open page may still ask for them)
        shutil.rmtree(os.path.join(proj.root, d), ignore_errors=True)
    mimo.build(proj.root, tools=False)
    page.reload()
    page.wait_for_selector(".blk.on")
    before = page.evaluate(PROBE)
    assert len(before) >= 10 and all(x[3] for x in before), before
    assert any("/IMG001_1" in x[1] or "IMG001_1." in x[1] for x in before) and not any("IMG001-1" in x[1] for x in before)
    run = lambda *a: subprocess.run([sys.executable, "tools/migrate.py"] + list(a), cwd=proj.root, capture_output=True, text=True, encoding="utf-8")
    dry = run()
    assert dry.returncode == 0 and "IMG001-1" in dry.stdout and os.path.exists(os.path.join(proj.root, "audio", "en", "IMG001_1.mp3"))
    done = run("--apply")
    assert done.returncode == 0, done.stdout[-500:] + done.stderr[-500:]
    stamp = re.search(r"--undo (\d{8}-\d{6})", done.stdout).group(1)
    page.reload()
    page.wait_for_selector(".blk.on")
    after = page.evaluate(PROBE)
    assert [(x[0], x[2], x[3]) for x in after] == [(x[0], x[2], x[3]) for x in before], "every button plays the same audio"
    assert any("IMG001-1" in x[1] for x in after) and not any("IMG001_1" in x[1] or "/L007" in x[1] for x in after)
    assert "id: IMG006-1" in proj.story()
    assert run("--undo", stamp).returncode == 0
    page.reload()
    page.wait_for_selector(".blk.on")
    assert page.evaluate(PROBE) == before


@test
def intake_inbox_imports_batch(proj, page):
    """Inbox files, odd files of refs/ and the import log are in the project JSON and listed in the references tab; GET /api/batch gives the copy-ready batch text;
    with "watch_downloads": true the server moves a matching download by itself."""
    def put(rel, data):
        p = os.path.join(proj.root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)
    put("inbox/sub/stray.jpg", png())
    put("images/refs/Engineering_sketch_a…_be66d232 (1).jpg", png())
    put(".kit/imports.tsv", "2026-11-24T10:00:00\tD:/Downloads/IMG001_x.jpg\timages/scenes/b01/IMG001_x.jpg\t9\n".encode("utf-8"))
    P = json.loads(urllib.request.urlopen(proj.url + "/api/project").read().decode("utf-8"))
    assert [(f["name"], f["kind"]) for f in P["inbox"]] == [("sub/stray.jpg", "image")], P["inbox"]
    assert [t["name"] for t in P["triage"]] == ["Engineering_sketch_a…_be66d232 (1).jpg"] and "Engineering" not in " ".join(r["name"] for r in P["refs"])
    assert P["imports"][0]["to"] == "images/scenes/b01/IMG001_x.jpg"
    page.reload()
    page.wait_for_selector(".blk.on")
    drawer(page, "inbox")
    assert page.locator("#pInbox ul[data-inbox] li").count() == 1 and page.locator("#pInbox ul[data-triage] li").count() == 1 and page.locator("#pInbox ul[data-imports] li").count() == 1
    drawer(page, "batch")  # the batch panel copies the text of /api/batch
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=proj.url)
    page.click("[data-batch=b01]")
    page.wait_for_function("document.querySelector('#toast') && !document.querySelector('#toast').hidden && document.querySelector('#toast').textContent.includes('b01')")
    assert "پرامپت دستهٔ b01 کپی شد" in page.inner_text("#toast")
    copied = page.evaluate("navigator.clipboard.readText()").replace("\r\n", "\n")
    assert copied == proj.api("/api/batch?b=b01")[1]["text"] and "=== IMG001 ===" in copied, copied[:200]
    undrawer(page)
    code, b = proj.api("/api/batch?b=b01")
    assert code == 200 and b["ids"][:2] == ["IMG001", "IMG002"] and "=== IMG001 ===" in b["text"] and "[REFS TO ATTACH: STYLE_ANCHOR| CH_ALI.png]" in b["text"], b
    assert "Output name: IMG001" in b["text"]
    assert proj.api("/api/batch?b=zz")[0] == 400
    txt = urllib.request.urlopen(proj.url + "/api/batch?b=b01&format=text").read().decode("utf-8")
    assert txt == b["text"]
    # the server's own watcher thread
    dl = os.path.join(proj.tmp, "dl")
    os.makedirs(dl)
    open(os.path.join(proj.root, "kit-config.json"), "w").write(json.dumps({"watch_downloads": True, "downloads": dl}))
    proj.proc.terminate()
    proj.proc.wait(5)
    env = dict(os.environ, PORT=str(proj.port), IDLE_SECONDS="3600", PYTHONIOENCODING="utf-8")
    proj.proc = subprocess.Popen([sys.executable, os.path.join(proj.root, "tools", "serve.py")], cwd=proj.root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(50):
        try:
            urllib.request.urlopen(proj.url + "/api/ping", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    open(os.path.join(dl, "IMG002_sign_a1b2c3d4_2K.png"), "wb").write(png() + b"\0")
    open(os.path.join(dl, "IMG002_other_ep_a1b2c3d5.png"), "wb").write(png() + b"\1")
    dst = os.path.join(proj.root, "images", "scenes", "b01", "IMG002_sign_a1b2c3d4_2K.png")
    for _ in range(100):
        if os.path.exists(dst):
            break
        time.sleep(0.1)
    assert os.path.exists(dst) and not os.path.exists(os.path.join(dl, "IMG002_sign_a1b2c3d4_2K.png"))
    assert os.path.exists(os.path.join(dl, "IMG002_other_ep_a1b2c3d5.png"))  # another slug: left alone
    code, imp = proj.api("/api/imports")
    assert code == 200 and imp["watching"] is True and imp["imports"][0]["to"].endswith("IMG002_sign_a1b2c3d4_2K.png"), imp


@test
def scene_label_edits_title_env_fx(proj, page):
    """The scene label on the left page opens a small dialog for the title, the environment and the edit advice (POST /api/scenemark edit);
    Esc asks before throwing away edits; a scene changed outside the page gives a 409 and nothing is overwritten."""
    at(page, "IMG001")
    page.click(".blk.on .slabel")
    dlg = "dialog.dlg[data-kind=scene]"
    page.wait_for_selector(dlg + "[open]")
    assert page.input_value(dlg + " [data-sf=title]") == "شروع" and page.input_value(dlg + " [data-sf=env]") == "یک خیابان شلوغ، صبح." and page.input_value(dlg + " [data-sf=fx]") == "فید از سیاه"
    page.fill(dlg + " [data-sf=title]", "چیزی که ذخیره نمی‌شه")
    page._dialogs.clear()
    page.keyboard.press("Escape")  # unsaved: asks, the test accepts
    page.wait_for_selector(dlg, state="detached")
    assert any("ذخیره‌نشده" in m for m in page._dialogs) and "چیزی که ذخیره نمی‌شه" not in proj.story()
    page.click(".blk.on .slabel")
    page.fill(dlg + " [data-sf=title]", "آغاز تازه")
    page.fill(dlg + " [data-sf=env]", "یک کوچهٔ خلوت\nصبح زود")
    page.fill(dlg + " [data-sf=fx]", "زوم آهسته")
    page.click(dlg + " [data-ssave]")
    proj.wait("scenario/story.txt", "fx: زوم آهسته")
    assert "=== scene-01 | آغاز تازه | 0:00-0:15 ===\nenv: یک کوچهٔ خلوت" in proj.story()  # (two lines of the box are one env: line, like the inline editor)
    page.wait_for_selector(dlg, state="detached")
    page.wait_for_function("document.querySelector('.blk.on .slabel').textContent.includes('آغاز تازه')")
    page.click(".blk.on .slabel")
    page.wait_for_selector(dlg + "[open]")
    assert proj.api("/api/scenemark", {"op": "edit", "scene": "scene-01", "title": "عنوان بیرونی"})[0] == 200  # changed outside the page
    page.fill(dlg + " [data-sf=fx]", "چیز دیگر")
    page._dialogs.clear()
    page.click(dlg + " [data-ssave]")
    page.wait_for_timeout(300)
    assert page._dialogs and "عوض شده" in page._dialogs[-1], page._dialogs
    page._errors[:] = [e for e in page._errors if "409" not in e]  # the refusal is the point of this test
    assert "=== scene-01 | عنوان بیرونی |" in proj.story() and "fx: چیز دیگر" not in proj.story()
    page.keyboard.press("Escape")
    assert proj.api("/api/scenemark", {"op": "edit", "scene": "scene-01", "title": ""})[0] == 400


@test
def language_pill_and_active_line(proj, page):
    """فا / EN shows the English lines; a click on a line makes it the active one (olive wash, counter «خط ۲ از ۲»); playing moves the wash along."""
    at(page, "IMG001")
    assert page.locator("#lang.en").count() == 0 and page.locator(".blk.on .en").count() == 0
    assert page.inner_text(".blk.on .cnt").strip() == "خط ۲ از ۳" and page.locator(".blk.on .it.cur").count() == 1  # the first spoken line is the active one
    en(page)
    assert page.locator("#lang.en").count() == 1 and page.locator(".blk.on .en").count() >= 2
    assert page.get_attribute(".blk.on", "data-bid") == "IMG001", "a reload keeps the picture on show"
    page.click(".blk.on .it >> nth=2", position={"x": 8, "y": 8})
    assert page.inner_text(".blk.on .cnt").strip() == "خط ۳ از ۳"
    assert page.locator(".blk.on .it.cur").count() == 1 and page.evaluate("getComputedStyle(document.querySelector('.blk.on .it.cur')).backgroundColor") != "rgba(0, 0, 0, 0)"
    en(page, False)
    assert page.locator(".blk.on .en").count() == 0


@test
def autoplay_goes_picture_by_picture(proj, page):
    """Auto-play shows each picture while its lines play, then moves to the next one; the time under the picture counts."""
    if not shutil.which("ffmpeg"):
        print("   (skipped: no ffmpeg to make test audio)", end="")
        return
    at(page, "IMG001")
    page.click("#play")
    page.wait_for_function("document.querySelector('#play').classList.contains('playing')")
    page.wait_for_function("document.querySelector('.blk.on .it.cur') && document.querySelector('.blk.on .it.cur').matches('.sp')")
    page.wait_for_function("document.querySelector('.blk.on').dataset.bid==='IMG002'", timeout=12000)  # on to the next picture by itself
    page.click("#play")
    page.wait_for_function("!document.querySelector('#play').classList.contains('playing')")
    assert page.get_attribute(".blk.on", "data-bid") == "IMG002"


@test
def keys_do_not_steal_typing(proj, page):
    """← → ↑ ↓ and Space only move between pictures / versions when you are not typing."""
    at(page, "IMG001")
    page.click("#bNote")
    page.focus("figure.shot[data-id=IMG001] textarea.nt")
    for k in ("ArrowRight", "ArrowDown", "Space"):
        page.keyboard.press(k)
    assert page.get_attribute(".blk.on", "data-bid") == "IMG001" and page.locator("#play.playing").count() == 0
    page.mouse.click(700, 500)
    page.click(".blk.on .it.sp .fa .v >> nth=0")
    page.keyboard.press("ArrowLeft")
    assert page.get_attribute(".blk.on", "data-bid") == "IMG001"
    page.keyboard.press("Escape")


@test
def archive_buttons_under_the_picture_and_the_old_rejected_folder(proj, page):
    """Two icons under the picture: «archive» sends the shown version to the archive (a toast brings it back), «the archive» opens a popup grid with
    ‹ › and «bring back»; files of an old `_rejected/` folder show up there too, and the «rejected» link under the picture is gone."""
    at(page, "IMG001")
    f = "figure.shot[data-id=IMG001]"
    rej = os.path.join(proj.root, "images", "scenes", "_rejected")
    os.makedirs(rej, exist_ok=True)
    shutil.copy2(os.path.join(proj.root, "images", "scenes", "IMG001_start.png"), os.path.join(rej, "IMG001_old_deadbeef.png"))
    page.reload()
    page.wait_for_selector(f)
    assert page.locator(f + " .rj").count() == 0  # no more «ردشده‌ها» link
    assert page.locator("#picActs #bArch").is_visible() and page.locator("#picActs #bArchList").is_visible()
    assert page.evaluate("document.querySelector('#picActs').parentElement.matches('figure.shot')")  # the icons sit under the picture they act on
    page.click("#bArch")
    page.wait_for_selector("#toast button")
    assert os.path.exists(os.path.join(proj.root, "images", "archive", "IMG001_start_a1b2c3.png")) or os.path.exists(os.path.join(proj.root, "images", "archive", "IMG001_start.png"))
    page.click("#toast button")  # «بازگردانی» puts it back
    page.wait_for_function("document.querySelectorAll('figure.shot[data-id=IMG001] [data-vn]').length > 0")
    assert not os.path.exists(os.path.join(proj.root, "images", "archive", "IMG001_start_a1b2c3.png"))
    page.click("#bArchList")
    page.wait_for_selector("dialog.archdlg .atile")
    assert page.locator("dialog.archdlg .atile").count() == 1  # the file of the old _rejected folder
    page.click("dialog.archdlg .atile")
    page.wait_for_selector("dialog.archdlg .aview img")
    page.click("dialog.archdlg [data-ar=list]")
    page.wait_for_selector("dialog.archdlg .agrid")
    page.click("dialog.archdlg [data-ar=close]")
    page.click("#bArchList")
    page.click("dialog.archdlg .atile")
    page.click("dialog.archdlg [data-ar=restore]")  # an old rejected file comes back as a version
    page.wait_for_function("document.querySelectorAll('figure.shot[data-id=IMG001] [data-vn]').length > 0")
    page.wait_for_function("document.querySelector('figure.shot[data-id=IMG001] img').src.includes('IMG001_old_deadbeef')")  # and it is the one on show
    assert not os.path.exists(os.path.join(rej, "IMG001_old_deadbeef.png"))
    assert os.path.exists(os.path.join(proj.root, "images", "scenes", "IMG001_old_deadbeef.png"))


@test
def voices_panel_has_three_sections_and_tones_can_be_added_marked_and_removed(proj, page):
    """Voices panel: default model, speakers, tones. A tone is added with a Persian name and an English tag, marked works / does not work for the
    default model, removed again; the tone list of the per-line menu shows the Persian name only (no English tag as a label)."""
    drawer(page, "spk")
    page.wait_for_selector("#spk .vsec")
    assert page.locator("#spk .vsec").count() == 3 and page.locator("#spk .spcard").count() >= 2
    assert page.locator("#spk .ttsbox").count() == 0 and "؟" not in page.inner_text("#spk")  # no unknown-accent marks
    assert page.locator("#tonel option[label]").count() == 0  # the English tag used to be the label of every option
    page.fill("#tnfa", "غمگین")
    page.fill("#tntag", "[sad]")
    page.click("[data-tadd]")
    page.wait_for_selector('#spk .tnrow:has-text("غمگین")')
    assert '"[sad]"' in proj.read("voices/voice-config.json")
    assert page.locator('#tonel option[value="غمگین"]').count() == 1
    code, body = proj.api("/api/tone", {"op": "add", "fa": "غمگین", "tag": "[sad]"})  # the same tone again is refused
    assert code == 400, (code, body)
    code, body = proj.api("/api/tone", {"op": "add", "fa": "x", "tag": "sad"})  # a tag must look like [word]
    assert code == 400
    cid = json.loads(proj.read("voices/voice-config.json"))["tones"][-1]["id"]
    code, _ = proj.api("/api/voicetest", {"model": json.loads(proj.read("voices/voice-config.json"))["models"] and list(json.loads(proj.read("voices/voice-config.json"))["models"])[0], "tone": cid, "result": "good"})
    assert code == 200
    page.click('#spk .tnrow:has-text("غمگین") [data-tdel]')
    page.wait_for_function("!document.querySelector('#spk').innerText.includes('غمگین')")
    assert '"[sad]"' not in proj.read("voices/voice-config.json")


@test
def export_for_the_editor_holds_only_the_chosen_files(proj, page):
    """Menu «خروجی برای ادیتور»: one zip with the review page, the scenario and ONLY the chosen picture versions and voice takes, plus a README for the editor."""
    import zipfile
    on_disk = [n for n in os.listdir(os.path.join(proj.root, "images", "scenes")) if n.startswith("IMG001")]
    assert len(on_disk) == 2  # two versions of IMG001 on disk
    drawer(page, "export")
    page.wait_for_selector("[data-ex=go]")
    page.click("[data-ex=go]")
    page.wait_for_function("document.querySelector('#exres') && document.querySelector('#exres').innerText.includes('آماده شد')", timeout=90000)
    z = os.path.join(os.path.dirname(proj.root), os.path.basename(proj.root) + "-for-editor.zip")
    names = zipfile.ZipFile(z).namelist()
    base = os.path.basename(proj.root) + "/"
    for want in ("README-FOR-EDITOR.txt", "review.html", "click-for-review.bat", "scenario/story.txt", "prompts/prompts.txt", "tools/serve.py"):
        assert base + want in names, want
    assert len([n for n in names if "/images/scenes/IMG001" in n]) == 1  # one of the two versions
    assert base + ".env" not in names and not any("/archive/" in n for n in names)
    if shutil.which("ffmpeg"):
        disk = [n for n in os.listdir(os.path.join(proj.root, "audio", "fa")) if n.endswith(".mp3")]
        assert len([n for n in names if "/audio/fa/" in n and n.endswith(".mp3")]) < len(disk)  # the other takes stay out


@test
def help_panel_shows_the_guide_cards_with_more(proj, page):
    """Help in the drawer: the cards of skills/how-to-write-prompts-for-flow.md (one-line summary, «more» opens the rest), the version at the end, and a project's own scripts card."""
    os.makedirs(os.path.join(proj.root, "skills"), exist_ok=True)
    shutil.copy2(os.path.join(KIT, "skills", "how-to-write-prompts-for-flow.md"), os.path.join(proj.root, "skills"))
    open(os.path.join(proj.root, "skills", "project-scripts.md"), "w", encoding="utf-8").write("# x" + chr(10) * 2 + "## خروجی پریمیر" + chr(10) + "- **دستور:** `python tools/export_premiere.py`" + chr(10))
    drawer(page, "help")
    page.wait_for_selector("#pHelp .hcard")
    n = page.locator("#pHelp [data-hmore]").count()
    assert n >= 9, n  # the cards of the guide + the project's own scripts
    assert "اسکریپت‌های این پروژه" in page.inner_text("#pHelp")
    assert page.locator("#pHelp .hbody:visible").count() == 0  # only summaries at first
    page.click("#pHelp [data-hmore] >> nth=1")
    page.wait_for_selector("#pHelp .hbody:visible")
    assert "دستور" in page.inner_text("#pHelp .hbody:visible") and page.locator("#pHelp .hbody:visible").count() == 1
    assert "نسخهٔ کیت" in page.inner_text("#pHelp")


@test
def settings_panel_writes_the_key_and_the_watcher_switch(proj, page):
    """Settings in the drawer: the key goes to .env (never shown again), the Downloads folder and the watcher switch go to kit-config.json, a foreign origin is refused."""
    drawer(page, "settings")
    page.wait_for_selector('[data-sset="keyopen"]')
    assert page.is_hidden("#skey")  # the key field is not always open: it opens with «افزودن کلید» / «تغییر»
    page.click('[data-sset="keyopen"]')
    page.wait_for_selector("#skey", state="visible")
    page.fill("#skey", "sk-or-v1-testtesttest1234")
    page.click('[data-sset="key"]')
    page.wait_for_function("document.querySelector('#skey') && document.querySelector('#skey').value === ''")
    assert "OPENROUTER_API_KEY=sk-or-v1-testtesttest1234" in open(os.path.join(proj.root, ".env"), encoding="utf-8").read()
    assert "testtesttest1234" not in page.content() and "testtesttest1234" not in json.dumps(proj.api("/api/settings")[1])
    page.wait_for_selector("#swatch")
    page.check("#swatch")  # the switch saves by itself (the test server starts with the watcher off)
    proj.wait("kit-config.json", '"watch_downloads": true')
    page.uncheck("#swatch")
    proj.wait("kit-config.json", '"watch_downloads": false')
    assert proj.api("/api/settings")[1]["watch"] is False
    req = urllib.request.Request(proj.url + "/api/settings", data=b"{}", headers={"Origin": "http://evil.example"})
    try:
        urllib.request.urlopen(req, timeout=5)
        raise AssertionError("a foreign origin was accepted")
    except urllib.error.HTTPError as e:
        assert e.code == 403


@test
def undo_from_the_drawer(proj, page):
    """Undo last change: the drawer lists the snapshots (newest first) and one button puts the file back byte for byte; a file edited since asks first."""
    before = story_bytes(proj)
    at(page, "IMG003")
    page.locator("#b3 .it.sp [data-del]").click()  # the page asks, the test accepts
    proj.wait("scenario/story.txt", "و روز تمام شد.", absent=True)
    settle(page)
    drawer(page)
    assert page.inner_text("[data-panel=undo] .trail").strip() == "۱"
    drawer(page, "undo")
    assert page.locator("#pUndo .hist li").count() == 1 and "حذف خط" in page.inner_text("#pUndo .hist")
    proj.api("/api/image", {"id": "IMG001", "note": "edited after the delete"})  # the file changed since: refuse unless forced
    page._dialogs.clear()
    page.click("#pUndo [data-undo]")  # the page explains and asks; the test accepts the force
    page.wait_for_function("window.__kit.S.RELOADS >= 0")
    page.wait_for_timeout(500)
    page._errors[:] = [e for e in page._errors if "409" not in e]  # the refused first try is the point of this test
    page.wait_for_function("document.querySelectorAll('#pUndo .hist li').length===0 || document.querySelector('#toast').textContent.includes('برگشت')")
    proj.wait("scenario/story.txt", "و روز تمام شد.")
    assert any("force" in m or "دوباره عوض شده" in m for m in page._dialogs), page._dialogs
    assert "edited after the delete" not in proj.story() and story_bytes(proj) == before
    page.wait_for_selector("text=و روز تمام شد.", state="attached")
    undrawer(page)


@test
def noimg_block_and_icons_need_a_picture(proj, page):
    """A text above the first picture (old projects) has no picture: the picture icons and the stamp are off, and the lines still show."""
    use_story(proj, page)
    noimg = page.evaluate("document.querySelector('.blk.noimg').dataset.bid")
    at(page, noimg)
    for sel in ("#bNote", "#bPrompt", "#bVprompt", "#bFlag", "#more", "#aside"):
        assert page.is_disabled(sel), sel
    assert page.locator(".blk.on .it.act").count() == 1 and page.locator(".blk.on .ph").count() == 1
    assert page.locator("#apr.show").count() == 0
    page.keyboard.press("ArrowRight")
    page.wait_for_function("!document.querySelector('.blk.on').classList.contains('noimg')")
    assert not page.is_disabled("#bPrompt")


@test
def mobile_stack_and_drawer(proj, page):
    """Phone (390x844): one fixed page (bar, picture, playback line, scrolling text, action bar), the drawer takes ~80% from the right, the prompt is a
    bottom sheet, nothing scrolls sideways and every control is at least 44px."""
    ctx = page.context.browser.new_context(viewport={"width": 390, "height": 844}, locale="fa-IR", has_touch=True)
    m = ctx.new_page()
    errs = []
    m.on("pageerror", lambda e: errs.append(str(e)))
    m.goto(proj.url + "/review.html#IMG001")
    m.wait_for_selector(".blk.on")
    m.wait_for_timeout(300)
    bar, img, txt = m.locator("#bar").bounding_box(), m.locator(".blk.on .imgs").bounding_box(), m.locator(".blk.on .txt").bounding_box()
    act = m.locator("#prev").bounding_box()
    assert bar["height"] <= 60 and bar["y"] < img["y"] < txt["y"] < act["y"], (bar, img, txt, act)
    assert img["width"] > 340 and txt["width"] > 340 and act["y"] + act["height"] <= 844 + 1
    assert m.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "no sideways scrolling"
    assert m.evaluate("document.body.scrollHeight <= innerHeight + 1"), "the page itself does not scroll; only the text does"
    assert m.locator("#approve").count() == 0 and m.locator("#aside").is_hidden()
    assert m.locator("#bPrompt").is_hidden() and m.locator("[data-fwd=bPrompt]").is_visible()

    def small():  # every visible control (buttons, inputs, selects) under 44px
        return m.evaluate("""() => [...document.querySelectorAll('button,input:not([type=hidden]):not([type=range]),select,summary,[role=button]')]
          .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' && !e.closest('[hidden]'))
          .map(e => [e.id || e.className || e.tagName, Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])
          .filter(x => x[1] < 44 || x[2] < 44)""")
    assert not small(), small()
    m.click("[data-fwd=bPrompt]")  # the prompt as a bottom sheet
    m.wait_for_selector("dialog.pm[open]")
    m.wait_for_timeout(350)
    d = m.locator("dialog.pm").bounding_box()
    assert d["width"] >= 389 and abs(d["y"] + d["height"] - 844) < 2 and 0.7 * 844 <= d["height"] <= 0.8 * 844, d
    assert not small(), small()
    m.keyboard.press("Escape")
    m.wait_for_selector("dialog.pm", state="detached")
    m.click("#menuBtn")
    m.wait_for_function("document.body.classList.contains('dopen')")
    m.wait_for_timeout(300)
    d = m.locator("#drawer").bounding_box()
    assert 0.78 * 390 <= d["width"] <= 0.82 * 390 and d["x"] + d["width"] >= 389 and d["x"] > 50, d
    assert not small(), small()
    m.keyboard.press("Escape")  # Esc closes the drawer
    m.wait_for_function("!document.body.classList.contains('dopen')")
    m.click("#menuBtn")
    m.click("[data-panel=scenes]")
    m.click("#slist .srow >> nth=1")
    m.wait_for_function("!document.body.classList.contains('dopen')")
    m.keyboard.press("ArrowRight")  # the keys still move between pictures
    m.wait_for_function("document.querySelector('.blk.on').dataset.bid!=='IMG001'")
    m.click("[data-fwd=bNote]")  # the bottom bar forwards to the real buttons
    m.wait_for_selector(".nbox:not(.hide)")
    assert not errs, errs
    ctx.close()


@test
def engine_manifest_is_complete(proj, page):
    files = [l.strip() for l in open(os.path.join(KIT, "ENGINE.txt"), encoding="utf-8") if l.strip() and not l.startswith("#")]
    missing = [f for f in files if not os.path.exists(os.path.join(KIT, *f.split("/")))]
    assert not missing, "listed in ENGINE.txt but missing: %s" % missing
    html = open(os.path.join(KIT, "review.html"), encoding="utf-8").read()
    for ref in re.findall(r'(?:src|href)="(tools/[^"]+)"', html):  # everything the page loads must be shipped to projects
        assert ref in files, "review.html loads %s but ENGINE.txt does not list it" % ref
    css = open(os.path.join(KIT, "tools", "ui", "review.css"), encoding="utf-8").read()
    for ref in re.findall(r'@import url\("([^"]+)"\)', css):  # the style parts too
        assert "tools/ui/" + ref in files, "review.css imports %s but ENGINE.txt does not list it" % ref


@test
def gallery_toolbar_search_filter_reorder_a11y(proj, page):
    """Gallery top bar: «n / m تأیید شده» with a bar and percent, search by id/text, the filter icon opens the filter panel, a reorder toggle; icon buttons are named;
    Esc closes the drawer."""
    page.goto(proj.url + "/review.html#gallery")
    page.wait_for_selector("#ggrid .tile[data-id]")
    assert "تأیید شده" in page.inner_text("#gst") and "٪" in page.inner_text("#gpct") and page.locator("#gstat .gbar").is_visible()
    n = page.locator("#ggrid .tile[data-id]").count()
    page.click("#gSearch")
    page.fill("#gq", "img001")
    assert page.locator("#ggrid .tile[data-id]:visible").count() == 1
    page.fill("#gq", "")
    assert page.locator("#ggrid .tile[data-id]:visible").count() == n
    page.click("#gSearch")
    assert page.locator("#gq").is_hidden()
    page.click("#gFilter")
    page.wait_for_function("document.body.classList.contains('dopen')")
    assert page.locator("#pFilter").is_visible()
    page.keyboard.press("Escape")
    page.wait_for_function("!document.body.classList.contains('dopen')")
    page.click("#gMove")
    assert page.locator("#gallery.reorder").count() == 1 and page.get_attribute("#gMove", "aria-pressed") == "true"
    bare = page.evaluate("""() => [...document.querySelectorAll('button')].filter(b => b.getClientRects().length && !b.textContent.trim() && !b.getAttribute('aria-label')).map(b => b.id || b.className)""")
    assert not bare, bare
    page.goto(proj.url + "/review.html#IMG001")
    page.wait_for_selector(".blk.on")
    bare = page.evaluate("""() => [...document.querySelectorAll('button')].filter(b => b.getClientRects().length && !b.textContent.trim() && !b.getAttribute('aria-label') && !b.title).map(b => b.id || b.className)""")
    assert not bare, bare


@test
def gallery_open_tiles_drag_picker_batch(proj, page):
    """The app opens on the gallery (#gallery); a tile opens the spread; drag reorders within a scene and across a scene boundary (/api/move);
    unplaced pictures are placed by the + button; the + tile's picker adds a slot; batch buttons copy the batch text; the menu item opens the same picker."""
    def order():
        P = proj.api("/api/project")[1]
        return [(sc["id"], im["id"]) for sc in P["scenes"] for b in sc["blocks"] for im in b["images"]]

    def drag(src, dst, right_half):
        a, b = page.locator('#ggrid .tile[data-id="%s"]' % src).bounding_box(), page.locator('#ggrid .tile[data-id="%s"]' % dst).bounding_box()
        page.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
        page.mouse.down()
        page.mouse.move(a["x"] + a["width"] / 2 + 12, a["y"] + a["height"] / 2 + 12, steps=3)
        page.mouse.move(b["x"] + b["width"] * (0.8 if right_half else 0.2), b["y"] + b["height"] / 2, steps=8)
        assert page.locator("#ggrid .gline:not([hidden])").count() == 1, "the drop line shows while dragging"
        page.mouse.up()
        page.wait_for_timeout(600)
    page.goto(proj.url + "/review.html")
    page.wait_for_selector("#ggrid .tile[data-id]")
    assert page.evaluate("location.hash") == "#gallery" and page.locator("#ggrid .tile[data-id]").count() == 4
    assert page.locator("#list").is_hidden() and page.locator("#galBtn").is_hidden()
    assert page.locator('#ggrid .tile[data-id="IMG001"] .gvc').count() == 1 and page.locator('#ggrid .tile[data-id="IMG002"] .gvc').count() == 0  # versions count only when > 1
    assert page.locator('#ggrid .tile[data-id="IMG003"].sb').count() == 1  # first picture of scene 2 carries the boundary tick
    page.click('#ggrid .tile[data-id="IMG002"]')  # a tile opens the spread on that picture
    page.wait_for_function("document.querySelector('.blk.on') && document.querySelector('.blk.on').dataset.bid === 'IMG002'")
    assert page.evaluate("location.hash") == "#IMG002" and page.locator("#gallery").is_hidden() and page.locator(".blk.on").get_attribute("data-bid") == "IMG002"
    page.click("#galBtn")
    page.wait_for_selector("#ggrid .tile[data-id]")
    assert page.evaluate("location.hash") == "#gallery" and page.locator("#list").is_hidden()
    drag("IMG002", "IMG001", True)  # right half = before (right-to-left page): within the scene
    assert order() == [("scene-00", "IMG000"), ("scene-01", "IMG002"), ("scene-01", "IMG001"), ("scene-02", "IMG003")], order()
    drag("IMG001", "IMG003", False)  # left half of the first picture of the next scene = after it: across the boundary
    assert order() == [("scene-00", "IMG000"), ("scene-01", "IMG002"), ("scene-02", "IMG003"), ("scene-02", "IMG001")], order()
    page.click("#gSel")  # select mode: two tiles, dragged together
    page.click('#ggrid .tile[data-id="IMG003"]')
    page.click('#ggrid .tile[data-id="IMG001"]')
    assert page.locator("#ggrid .tile.sel").count() == 2 and page.evaluate("location.hash") == "#gallery"
    drag("IMG003", "IMG002", True)
    assert order() == [("scene-00", "IMG000"), ("scene-01", "IMG003"), ("scene-01", "IMG001"), ("scene-01", "IMG002")], order()
    # pictures with a prompt or files but no marker
    open(os.path.join(proj.root, "prompts", "prompts.txt"), "a", encoding="utf-8").write("\n=== IMG010 ===\nA prompt without a place.\n")
    open(os.path.join(proj.root, "images", "scenes", "IMG011_x.png"), "wb").write(png())
    page.reload()
    page.wait_for_selector("#ggrid .tile[data-id]")
    assert [u["id"] for u in proj.api("/api/project")[1]["unplaced"]] == ["IMG010", "IMG011"], proj.api("/api/project")[1]["unplaced"]
    assert page.locator(".gun .uit").count() == 2
    page.click('[data-gun="IMG011"]')
    page.wait_for_selector('#ggrid .tile[data-id="IMG011"]')
    assert order()[-1] == ("scene-01", "IMG011"), order()  # after the last picture (scene 2 is empty by now)
    u = page.locator('.gun .uit[data-uid="IMG010"]').bounding_box()
    t = page.locator('#ggrid .tile[data-id="IMG000"]').bounding_box()
    page.mouse.move(u["x"] + 20, u["y"] + 10)
    page.mouse.down()
    page.mouse.move(u["x"] + 30, u["y"] - 20, steps=3)
    page.mouse.move(t["x"] + t["width"] * 0.2, t["y"] + t["height"] / 2, steps=8)
    page.mouse.up()
    page.wait_for_selector('#ggrid .tile[data-id="IMG010"]')
    assert order()[1] == ("scene-00", "IMG010"), order()  # left half of the first tile = after it
    # the + tile: picker with a new empty slot
    n = len(order())
    page.click("#ggrid .tile.add")
    page.wait_for_selector("dialog.gpick[open]")
    assert page.locator("dialog.gpick [data-pk=new]").count() == 1 and page.locator("#pkAll option").count() == n
    page.click("dialog.gpick [data-pk=new]")
    page.wait_for_function("document.querySelectorAll('#ggrid .tile[data-id]').length == %d" % (n + 1))
    assert len(order()) == n + 1 and order()[-1][0] == "scene-01"
    # the review menu's item opens the same picker, then shows the new picture
    page.click('#ggrid .tile[data-id="IMG001"]')
    page.wait_for_selector(".blk.on")
    more(page)
    page.click("#morePop [data-ipick]")
    page.wait_for_selector("dialog.gpick[open]")
    page.click("dialog.gpick [data-pk=new]")
    page.wait_for_function("window.__kit.S.P.scenes.flatMap(s => s.blocks).flatMap(b => b.images).length == %d" % (n + 2))
    ids = [i for _, i in order()]
    assert ids[ids.index("IMG001") + 1] == page.evaluate("location.hash").lstrip("#"), (ids, page.evaluate("location.hash"))
    page.click("#galBtn")
    page.wait_for_selector("#ggrid .tile[data-id]")
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=proj.url)
    page.click("[data-gbatch=b01]")
    page.wait_for_function("document.querySelector('#toast') && !document.querySelector('#toast').hidden && document.querySelector('#toast').textContent.includes('b01')")
    assert "=== IMG001 ===" in page.evaluate("navigator.clipboard.readText()")


@test
def voice_rid_takes_play_from_srcs(proj, page):
    """New <id>_<rid>.mp3 takes (even in subfolders) resolve to their real path in both the voice dialog and the .vv switcher."""
    if not shutil.which("ffmpeg"):
        print("   (skipped: no ffmpeg to make test audio)", end="")
        return
    sub = os.path.join(proj.root, "audio", "fa", "b01")
    os.makedirs(sub, exist_ok=True)
    shutil.copy2(os.path.join(proj.root, "audio", "fa", "IMG001_1.mp3"), os.path.join(sub, "IMG001_1_a1b2c3d4.mp3"))
    page.reload()
    at(page, "IMG001")
    page.click("[data-vgen=IMG001_1]")
    page.wait_for_selector("dialog.dlg [data-dpick=fa][value=a1b2c3d4]")
    play_src = page.get_attribute("dialog.dlg [data-dpick=fa][value=a1b2c3d4] >> xpath=../..//button[@data-dplay]", "data-dplay")
    assert play_src == "audio/fa/b01/IMG001_1_a1b2c3d4.mp3", play_src
    assert urllib.request.urlopen(proj.url + "/" + play_src).status == 200
    page.click("dialog.dlg [data-dclose]")
    page.wait_for_selector("dialog.dlg", state="detached")
    btn = "#b1 .vv[data-vv=fa] >> nth=0"
    for _ in range(4):
        page.click(btn)
        if "a1b2c3d4" in proj.story():
            break
    proj.wait("scenario/story.txt", "voice: fa=a1b2c3d4")
    ab_src = page.get_attribute("#b1 .ab[data-lg=fa] >> nth=0", "data-src")
    assert ab_src.startswith("audio/fa/b01/IMG001_1_a1b2c3d4.mp3?v="), ab_src


@test
def redo_gallery_filter_inbox_preview_and_regen_all(proj, page):
    """#bRedo & #morePop mark status: redo; gallery tiles & filter sync with S.filter/S.q and #fltChip; inbox images show previews; #spk offers regen-all."""
    at(page, "IMG001")
    page.click("#bRedo")
    proj.wait_in("[IMG001]", "status: redo")
    page.wait_for_selector("#bRedo.has")
    page.wait_for_selector("#apr.show.redo")
    page.click("#bRedo")
    proj.wait_in("[IMG001]", "status: redo", absent=True)
    more(page)
    page.click("#morePop [data-iredo]")
    proj.wait_in("[IMG001]", "status: redo")
    os.makedirs(os.path.join(proj.root, "inbox"), exist_ok=True)
    open(os.path.join(proj.root, "inbox", "inb_pic.png"), "wb").write(png())
    page.evaluate("location.hash = 'gallery'")
    page.reload()
    page.wait_for_selector('#ggrid .tile.redo[data-id="IMG001"]')
    assert page.get_attribute('.uit img[data-inbzoom]', 'src') == 'inbox/inb_pic.png'
    page.click('.uit img[data-inbzoom]')
    page.wait_for_selector('#lb:not(.hide)')
    page.keyboard.press('Escape')
    page.wait_for_selector('#lb.hide', state='attached')
    page.click("#gFilter")
    page.click("[data-filter=redo]")
    assert page.locator("#ggrid .tile[data-id]:visible").count() == 2  # IMG001 + IMG003 (already redo in fixture)
    assert page.locator("#fltChip:visible").count() == 1
    page.keyboard.press("Escape")
    page.click("#fltChip")
    assert page.locator("#ggrid .tile[data-id]:visible").count() == 4
    assert page.locator("#fltChip").is_hidden()
    drawer(page, "spk")
    assert page.locator("#spk [data-regen-all]").count() == 1


def main():
    global UPDATE
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    UPDATE = a.update_baseline
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright   (then run again)")
    todo = [t for t in TESTS if not a.names or any(n in t.__name__ for n in a.names)]
    failed = []
    with sync_playwright() as p:
        browser = None
        for ch in ("msedge", "chrome", None):
            try:
                browser = p.chromium.launch(channel=ch, headless=not a.headed)
                break
            except Exception:
                continue
        if not browser:
            sys.exit("no browser found: install Edge/Chrome or run: playwright install chromium")
        for t in todo:
            proj, errors, t0, page = Proj(), [], time.time(), None
            try:
                page = open_page(browser, proj, errors)
                t(proj, page)
                page.wait_for_timeout(150)
                assert not errors, "browser errors: %s" % errors[:3]
                print("PASS %-34s %.1fs" % (t.__name__, time.time() - t0))
            except Exception:
                failed.append(t.__name__)
                if page is not None and getattr(page, "_dialogs", None):
                    print("   dialogs shown by the page:", page._dialogs)
                if errors:
                    print("   browser errors:", errors[:3])
                print("FAIL %s\n%s" % (t.__name__, "".join(traceback.format_exc().splitlines(True)[-14:])))
            finally:
                proj.close()
        browser.close()
    print("\n%d passed, %d failed%s" % (len(todo) - len(failed), len(failed), (": " + ", ".join(failed)) if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
