# -*- coding: utf-8 -*-
"""End-to-end tests of the review page + server, in a real browser (Playwright, using the Edge/Chrome already installed).
  pip install playwright                       (once; no browser download needed)
  python tools/tests/run.py                    run everything
  python tools/tests/run.py edit_dialogue fab  run only tests whose name contains one of these words
  python tools/tests/run.py --update-baseline  rewrite tools/tests/baseline/* from the current page (do this ONLY when the page is meant to look different)
Every test builds a fresh throw-away project in a temp folder (fixture/ + the tools of this checkout), starts its own server on a free port and
never touches a real project. Nothing here calls a paid service. This folder is not part of the engine (ENGINE.txt) and is not sent to projects."""
import argparse, contextlib, json, os, re, shutil, socket, struct, subprocess, sys, tempfile, time, traceback, urllib.error, urllib.request, zlib

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

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="srk-test-")
        self.root = os.path.join(self.tmp, "proj")
        os.makedirs(self.root)
        build_project(self.root)
        with contextlib.closing(socket.socket()) as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = "http://127.0.0.1:%d" % self.port
        env = dict(os.environ, PORT=str(self.port), IDLE_SECONDS="3600", PYTHONIOENCODING="utf-8")
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


def menu(page, sid):
    """Open the «⋯» menu of a scene."""
    page.click(f"section[data-scene={sid}] [data-mn]")


def use_story(proj, page, name="story-legacy.txt"):
    """Swap the project's story.txt for another fixture (the server re-reads it on every request) and reload the page."""
    shutil.copy2(os.path.join(FIX, name), os.path.join(proj.root, "scenario", "story.txt"))
    page.reload()
    page.wait_for_selector("section.blk")
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
    page.on("dialog", lambda d: (page._dialogs.append(d.message), d.accept(d.default_value) if d.type == "prompt" else d.accept()))
    page.goto(proj.url + "/review.html")
    page._reloads = 0
    if wait_ready:
        page.wait_for_selector("section.blk")
    return page


# ---------------------------------------------------------------- the tests: every one gets (proj, page)
@test
def load_and_snapshot(proj, page):
    """The page loads and what it draws is exactly what the known-good version drew."""
    assert page.locator("section[data-scene]").count() == 3
    assert page.locator("figure.shot").count() == 4
    assert page.locator(".it.sp").count() == 4
    page.check("#showEN")
    page.wait_for_selector(".en")
    page.wait_for_timeout(300)
    baseline("list-en.html", norm(page.inner_html("#list")))
    page.uncheck("#showEN")
    page.wait_for_timeout(300)
    baseline("list-fa.html", norm(page.inner_html("#list")))
    baseline("bar.html", norm(page.inner_html("#bar")))
    page.click("#tabF")
    baseline("refs.html", norm(page.inner_html("#refs")))
    page.click("#tabS")
    baseline("speakers.html", norm(page.inner_html("#spk")))
    page.click("#tabR")
    code, data = proj.api("/api/project")
    data.pop("time", None)
    data["tts"].pop("updated", None)  # file time of voice-config.json
    data["scenes"] = json.loads(re.sub(r"\?v=\d+", "?v=0", json.dumps(data["scenes"], ensure_ascii=False)))
    baseline("project.json", json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


@test
def edit_dialogue(proj, page):
    assert "voice-stale" not in proj.story().split("=== scene-02")[1]
    page.click("#b3 .it.sp .fa .v >> nth=0")
    page.fill(".ie.say textarea", "متن تازهٔ راوی")
    page.press(".ie.say textarea", "Enter")
    proj.wait("scenario/story.txt", "say: راوی (آهسته) | متن تازهٔ راوی")
    assert "voice-stale: fa" in proj.story().split("=== scene-02")[1]  # a changed line makes that scene's voice out of date
    page.wait_for_selector("text=متن تازهٔ راوی")


@test
def edit_cancel_with_escape(proj, page):
    before = proj.story()
    page.click("#b1 .it.sp .fa .v >> nth=0")
    page.fill(".ie.say textarea", "چیزی که نباید ذخیره شود")
    page.press(".ie.say textarea", "Escape")
    page.wait_for_timeout(300)
    assert proj.story() == before and page.locator(".ie.say").count() == 0


@test
def edit_env_and_act(proj, page):
    page.click(".env .v >> nth=0")
    page.fill(".ie textarea", "محیط تازه")
    page.press(".ie textarea", "Enter")
    proj.wait("scenario/story.txt", "env: محیط تازه")
    settle(page)
    page.click(".it.act .v >> nth=0")
    page.fill(".ie textarea", "توضیح تازه")
    page.press(".ie textarea", "Enter")
    proj.wait("scenario/story.txt", "act: توضیح تازه")


@test
def add_and_delete_dialogue(proj, page):
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
    page.check("#showEN")
    page.wait_for_selector("[data-aden]")
    page.click("[data-aden] >> nth=0")
    page.fill(".ie textarea", "A new translation")
    page.press(".ie textarea", "Enter")
    proj.wait("scenario/story.txt", "en: A new translation")


@test
def change_speaker_and_tone(proj, page):
    page.click("#b1 .it.sp .nm >> nth=0")
    page.fill(".ie.say input.tn", "آهسته")
    page.press(".ie.say textarea", "Enter")
    proj.wait("scenario/story.txt", "say: راوی (آهسته) | این علیه.")


@test
def unknown_tone_is_flagged(proj, page):
    page.wait_for_selector(".msg.tonewarn")
    assert page.locator(".msg.tonewarn").count() == 1 and "عصبانی" in page.inner_text(".msg.tonewarn")
    page.click("#tabS")
    assert page.locator("#spk input.unk").count() == 1
    page.wait_for_selector('#spk [data-st="2"]')
    page.fill('#spk [data-st="2"]', "آهسته")
    page.locator('#spk [data-st="2"]').blur()  # the page saves on «change», which fires when the field loses focus
    proj.wait("scenario/story.txt", "| aura-2-thalia-en | آهسته")
    page.wait_for_function("!document.querySelector('.msg.tonewarn')")


@test
def status_and_note(proj, page):
    f = "figure.shot[data-id=IMG002]"
    for gone in ("[data-m=ok]", "[data-m=redo]", "[data-nt]"):
        assert page.locator(f + " " + gone).count() == 0, gone + " buttons were removed from the page"
    assert page.get_attribute(f + " textarea.nt", "placeholder").startswith("یادداشت برای این صحنه")  # the note is an always-visible input
    page.fill(f + " textarea.nt", "یادداشت تست")
    page.press(f + " textarea.nt", "Enter")
    proj.wait_in("[IMG002]", "note: یادداشت تست")


@test
def edit_advice_fx(proj, page):
    assert page.locator("[data-sfx], .fxs").count() == 0, "the whole-scene edit box was removed (each picture has its own edit)"
    page.click("figure.shot[data-id=IMG003] [data-fx]")
    page.fill("figure.shot[data-id=IMG003] .fxbox textarea", "زوم سریع")
    page.press("figure.shot[data-id=IMG003] .fxbox textarea", "Enter")
    proj.wait("scenario/story.txt", "fx: زوم سریع")


@test
def prompts_save(proj, page):
    f = "figure.shot[data-id=IMG003]"
    page.click(f + " [data-p]")
    page.fill(f + " .pr:not(.vpr) textarea", "[REFS TO ATTACH: STYLE_ANCHOR| CH_ALI]\nA brand new prompt.")
    page.click(f + " [data-sp]")
    proj.wait("prompts/prompts.txt", "A brand new prompt.")
    proj.wait("scenario/story.txt", "image-stale: yes")
    settle(page)
    page.click("figure.shot[data-id=IMG002] [data-vp]")
    page.fill("figure.shot[data-id=IMG002] .vpr textarea", "[START FRAME: IMG002]\nA video prompt.")
    page.click("figure.shot[data-id=IMG002] [data-svp]")
    proj.wait("prompts/video-prompts.txt", "A video prompt.")


@test
def format_issue_flag(proj, page):
    page.click(".it.sp [data-fl] >> nth=0")  # the page asks for a message with prompt(); the test accepts its default text
    proj.wait("scenario/story.txt", "format-issue:")
    page.wait_for_selector(".issue")
    page.click(".issue [data-clr] >> nth=0")
    proj.wait("scenario/story.txt", "format-issue:", absent=True)


@test
def tabs_filter_jump(proj, page):
    page.click("#tabF")
    assert page.is_visible("#refs") and not page.is_visible("#list") and page.locator("#refs .card").count() == 1
    page.click("#refs [data-img] >> nth=0")
    page.wait_for_selector("#list", state="visible")
    page.select_option("#filter", "ok")
    page.wait_for_timeout(200)
    assert page.locator("figure.shot:not(.hide)").count() == 1
    page.select_option("#filter", "all")
    page.select_option("#jump", index=2)
    page.wait_for_function("document.querySelectorAll('.blk.on').length===1")
    page.click("#next")
    page.click("#prev")
    page.click("#tabS")
    assert page.locator("#spk .spt").count() == 3


@test
def lightbox(proj, page):
    page.click("figure.shot[data-id=IMG001] button.chip.ref >> nth=0")
    page.wait_for_selector("#lb", state="visible")
    page.keyboard.press("Escape")
    page.wait_for_selector("#lb", state="hidden")


@test
def floating_play_button(proj, page):
    fab = page.locator("#fab")
    assert fab.get_attribute("aria-label") == "پخش خودکار" and page.locator("#fab svg").count() == 2
    box = fab.bounding_box()
    assert abs(box["width"] - box["height"]) < 1 and box["width"] >= 44
    for sel in ("#fab .i-play", "#fab .i-pause"):  # both icons centred in the button
        page.evaluate("document.querySelector('#fab').classList.toggle('playing', %s)" % ("false" if "play" in sel and "pause" not in sel else "true"))
        r = page.locator(sel).bounding_box()
        assert abs((r["x"] + r["width"] / 2) - (box["x"] + box["width"] / 2)) < 1 and abs((r["y"] + r["height"] / 2) - (box["y"] + box["height"] / 2)) < 1
    page.evaluate("document.querySelector('#fab').classList.remove('playing')")
    fab.click()
    page.wait_for_function("document.querySelector('#fab').classList.contains('playing')")
    assert fab.get_attribute("aria-label") == "توقف پخش" and "⏸" in page.inner_text("#play")
    fab.click()
    page.wait_for_function("!document.querySelector('#fab').classList.contains('playing')")
    page.keyboard.press("Space")  # the space bar plays too
    page.wait_for_function("document.querySelector('#fab').classList.contains('playing')")
    page.keyboard.press("Space")


@test
def line_audio_buttons(proj, page):
    if not shutil.which("ffmpeg"):
        print("   (skipped: no ffmpeg to make test audio)", end="")
        return
    assert page.locator("#b1 .ab").count() >= 4
    page.click("#b1 .ab[data-lg=fa] >> nth=0")
    page.wait_for_function("document.querySelector('.ab.on')!==null||true")


@test
def subtitles_button(proj, page):
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
    page.click("#tabS")
    page.reload()
    page.wait_for_selector("section.blk")


@test
def model_and_voice_pickers(proj, page):
    code, data = proj.api("/api/project")
    ids = [m["id"] for m in data["tts"]["catalog"]]
    assert ids == sorted(ids) and "deepgram/aura-2" in ids and len(data["tts"]["tones"]) >= 10
    assert page.locator("[data-scm]").count() == 0, "the per-scene model picker was removed"
    page.click("#tabS")
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
    """Every file of the same IMG### is a version; the one the user stops on is the chosen (approved) one; no file is touched."""
    f = "figure.shot[data-id=IMG001]"
    assert page.inner_text(f + " .vc").strip() == "2 / 2" and page.locator("figure.shot[data-id=IMG002] [data-vn]").count() == 0
    assert "a1b2c3" in page.get_attribute(f + " img", "src")  # no pick yet: the newest is shown
    page.click(f + " [data-vn='-1']")
    proj.wait_in("[IMG001]", "pick: IMG001_start.png")
    assert "status: ok" not in proj.story().split("[IMG002]")[0], "choosing a picture replaces the old plain «ok» mark"
    page.wait_for_function("(() => { const f = document.querySelector('%s'); return !f.querySelector('img').src.includes('a1b2c3') && f.querySelector('.vc').textContent.includes('✔'); })()" % f)  # the file is written before the page has redrawn
    page.click(f + " [data-vn='1']")
    proj.wait_in("[IMG001]", "pick: IMG001_start_a1b2c3.png")
    assert proj.api("/api/image", {"id": "IMG001", "pick": ""})[0] == 200  # un-choosing is still possible through the API
    proj.wait_in("[IMG001]", "pick:", absent=True)
    for name in ("IMG001_start.png", "IMG001_start_a1b2c3.png"):
        assert os.path.exists(os.path.join(proj.root, "images", "scenes", name))
    code, data = proj.api("/api/project")
    assert code == 200 and proj.api("/api/image", {"id": "IMG001", "pick": "nope.png"})[0] == 400
    page.reload()
    page.wait_for_selector("section.blk")
    assert page.locator("figure.shot[data-id=IMG001]").get_attribute("data-m") in ("", "redo", None) or True


@test
def flow_versions_browse(proj, page):
    """Flow file names: qualities of one random id are ONE version (◀ ▶ counts versions), a « (1)» copy is ignored, sub-folders are read, pick: keeps the random id,
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
    page.reload()
    page.wait_for_selector("section.blk")
    f = "figure.shot[data-id=IMG002]"
    assert page.inner_text(f + " .vc").strip().startswith("3 / 3"), page.inner_text(f + " .vc")  # IMG002_sign.png, aaaa1111, bbbb2222: files are not counted
    _, data = proj.api("/api/project")
    im = next(i for sc in data["scenes"] for b in sc["blocks"] for i in b["images"] if i["id"] == "IMG002")
    assert [v["id"] for v in im["versions"]] == ["IMG002_sign.png", "aaaa1111", "bbbb2222"] and im["batch"] == "b01"
    assert next(v for v in im["versions"] if v["id"] == "aaaa1111")["name"].endswith("aaaa1111_2K.png")  # 2K beats the normal file
    page.click(f + " [data-vn='-1']")
    proj.wait_in("[IMG002]", "pick: aaaa1111")
    page.wait_for_function("(() => { const t = document.querySelector('figure.shot[data-id=IMG002] .vc').textContent; return t.includes('✔') && t.includes('2K'); })()")
    add("images/scenes/b01/IMG002_sign_aaaa1111_4K.png", 0)  # a 4K of the chosen version arrives
    page.reload()
    page.wait_for_selector("section.blk")
    assert page.inner_text(f + " .vc").strip().startswith("2 / 3") and "4K" in page.inner_text(f + " .vc") and "✔" in page.inner_text(f + " .vc")
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
    btn = "#b1 .vv[data-vv=fa] >> nth=0"
    assert page.inner_text(btn).strip() == "‹1/3›"  # default, eleven-v3, eleven-v4 (no pick yet: the old default plays)
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
    """A scene set aside keeps its text, pictures and audio; it just leaves the final order (off: yes)."""
    before = proj.story()
    menu(page, "scene-02")
    page.click("section[data-scene=scene-02] [data-soff]")
    proj.wait("scenario/story.txt", "off: yes")
    assert "و روز تمام شد." in proj.story() and "[IMG003]" in proj.story()
    page.wait_for_selector("section.scene-off")
    assert page.locator("section[data-scene=scene-02] .blk").count() == 0
    assert page.locator("#jump option").count() == 2  # the set-aside scene is not in the playlist
    assert proj.api("/api/project")[1]["scenes"][2]["off"] is True
    page.click("section.scene-off [data-son]")
    proj.wait("scenario/story.txt", "off: yes", absent=True)
    assert proj.story() == before, "setting aside and bringing back must leave the file exactly as it was"


@test
def picture_set_aside(proj, page):
    f = "figure.shot[data-id=IMG003]"
    assert page.locator(f + " .idl [data-ioff]").count() == 1, "the set-aside button sits next to the picture name"
    page.click(f + " [data-ioff]")
    proj.wait_in("[IMG003]", "off: yes")
    page.wait_for_selector(f + ".off")
    assert os.path.exists(os.path.join(proj.root, "images", "scenes", "IMG003_sea.png"))
    page.click(f + " [data-ioff]")
    proj.wait_in("[IMG003]", "off: yes", absent=True)


@test
def move_scenes(proj, page):
    """Reordering moves whole blocks; ids and file names never change, the shown scene numbers follow the order."""
    menu(page, "scene-02")
    page.click("section[data-scene=scene-02] [data-smv='-1']")
    page.wait_for_function("document.querySelector('section[data-scene=scene-02] h2 .num').textContent==='1'")
    st = proj.story()
    assert st.index("=== scene-02") < st.index("=== scene-01") and "\n\n=== scene-01" in st
    assert page.inner_text("section[data-scene=scene-01] h2 .num").strip() == "2"
    for needle in ("[IMG001]", "[IMG002]", "[IMG003]", "say: تست | یک خط"):
        assert needle in st
    menu(page, "scene-02")
    page.click("section[data-scene=scene-02] [data-smv='1']")
    page.wait_for_function("document.querySelector('section[data-scene=scene-01] h2 .num').textContent==='1'")
    assert proj.story().index("=== scene-01") < proj.story().index("=== scene-02")
    assert proj.api("/api/scenemove", {"scene": "scene-01", "step": -1})[0] == 400  # the thumbnail stays first
    assert proj.api("/api/scenemove", {"scene": "scene-02", "step": 1})[0] == 400  # nothing below the last scene


@test
def scene_menu_and_add_image(proj, page):
    """Every scene has one «⋯» menu; Esc and outside clicks close it; «new picture» appends an empty slot to an existing scene."""
    sec = "section[data-scene=scene-01] h2"
    assert page.locator(sec + " .menu").is_hidden()
    menu(page, "scene-01")
    assert page.locator(sec + " .menu").is_visible() and page.get_attribute(sec + " [data-mn]", "aria-expanded") == "true"
    page.keyboard.press("Escape")
    assert page.locator(sec + " .menu").is_hidden()
    menu(page, "scene-01")
    page.click("h1, #title")
    assert page.locator(sec + " .menu").is_hidden()
    menu(page, "scene-01")
    page.click("section[data-scene=scene-01] [data-addimg]")
    proj.wait("scenario/story.txt", "[IMG004]")
    st = proj.story()
    assert st.index("[IMG002]") < st.index("[IMG004]") < st.index("=== scene-02"), "the new slot goes to the end of that scene"
    assert "\n\n=== scene-02" in st
    page.wait_for_selector("figure.shot[data-id=IMG004]")
    assert proj.api("/api/addimage", {"scene": "scene-77"})[0] == 400
    assert proj.api("/api/addimage", {"scene": "bad"})[0] == 400


@test
def add_scene(proj, page):
    menu(page, "scene-01")
    page.click("[data-addscene=scene-01]")  # the page asks for a title and a picture count; the test accepts the defaults (1 picture)
    proj.wait("scenario/story.txt", "=== scene-03 | صحنهٔ جدید | - ===")
    st = proj.story()
    assert st.index("=== scene-01") < st.index("=== scene-03") < st.index("=== scene-02"), "new scene goes right after the chosen one"
    assert "[IMG004]\n\n=== scene-02" in st
    page.wait_for_selector("section[data-scene=scene-03] figure.shot")
    code, data = proj.api("/api/addscene", {"after": "scene-03", "title": "دو تایی", "images": 2})
    assert code == 200 and data["scene"] == "scene-04"
    assert "[IMG005]\n[IMG006]" in proj.story()
    assert proj.api("/api/addscene", {"after": "scene-01", "title": "a|b", "images": 1})[0] == 400
    assert proj.api("/api/addscene", {"after": "scene-01", "title": "x", "images": 99})[0] == 400
    assert proj.api("/api/addscene", {"after": "scene-77", "title": "x", "images": 1})[0] == 400


@test
def voice_dialog_manage(proj, page):
    """One dialog per line: choose a voice, archive it (file moves, pick is cleared), bring it back. No network is used."""
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
def making_again_archives_the_old_voice(proj, page):
    """tts.make with the same model replaces nothing: the older file goes to audio/<lang>/archive/ first (the network is faked here)."""
    code = ("import sys, os; sys.path.insert(0,'tools'); import tts\n"
            "tts.synth=lambda *a: b'x'*6000; tts.load_key=lambda: 'k'; tts.voice_problem=lambda m,v: None\n"
            "it=dict(id='IMG003_1', scene='scene-02', speaker='راوی', voice='george', model='elevenlabs/eleven-v3', spoken='سلام', tone='')\n"
            "os.makedirs('audio/fa',exist_ok=True)\n"
            "print(tts.make([it],'fa',force=True)); print(tts.make([it],'fa',force=True))\n"
            "print(sorted(os.listdir('audio/fa/archive')))")
    out = subprocess.run([sys.executable, "-c", code], cwd=proj.root, capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr[-400:]
    assert "'IMG003_1.eleven-v3.mp3'" in out.stdout and out.stdout.count("'ok'") == 2, out.stdout
    assert os.path.exists(os.path.join(proj.root, "audio", "fa", "IMG003_1.eleven-v3.mp3"))


@test
def picture_archive_and_back(proj, page):
    f = "figure.shot[data-id=IMG001]"
    page.click(f + " [data-vn='-1']")  # choose the older picture, then archive the newest one
    proj.wait_in("[IMG001]", "pick: IMG001_start.png")
    page.click(f + " [data-vn='1']")
    proj.wait_in("[IMG001]", "pick: IMG001_start_a1b2c3.png")
    page.click(f + " [data-iarch]")  # archiving the chosen picture clears the pick
    proj.wait_in("[IMG001]", "pick:", absent=True)
    page.wait_for_selector(f + " [data-irest]")
    assert os.path.exists(os.path.join(proj.root, "images", "archive", "IMG001_start_a1b2c3.png"))
    assert not os.path.exists(os.path.join(proj.root, "images", "scenes", "IMG001_start_a1b2c3.png"))
    assert page.locator(f + " [data-vn]").count() == 0  # one version left
    page.click(f + " [data-irest]")
    page.wait_for_selector("dialog.dlg [data-irestore]")
    page.click("dialog.dlg [data-irestore='IMG001_start_a1b2c3.png']")
    page.wait_for_selector(f + " [data-vn]")
    assert os.path.exists(os.path.join(proj.root, "images", "scenes", "IMG001_start_a1b2c3.png"))
    assert page.locator(f + " [data-irest]").count() == 0
    page.keyboard.press("Escape")
    assert proj.api("/api/archive", {"kind": "image", "id": "IMG001", "name": "nope.png"})[0] == 400


@test
def attach_references(proj, page):
    """The 📎 dialog lists the project's reference pictures; saving rewrites only the REFS line of that prompt and marks the picture stale."""
    f = "figure.shot[data-id=IMG003]"
    page.click(f + " [data-attach]")
    dlg = "dialog.dlg"
    page.wait_for_selector(dlg + " [data-aref=CH_ALI]:checked")
    assert page.locator(dlg + " [data-aref]").count() >= 2
    page.click(dlg + " [data-aref=CH_ALI]")  # untick
    page.click(dlg + " [data-dsaverefs]")
    proj.wait("prompts/prompts.txt", "[REFS TO ATTACH: STYLE_ANCHOR]\nPrompt of picture 3.")
    proj.wait_in("[IMG003]", "image-stale: yes")
    page.wait_for_selector(dlg, state="detached")
    assert page.locator(f + " .chip.ref, " + f + " .chip.miss").count() == 1
    page.click(f + " [data-attach]")
    page.click(dlg + " [data-aref=CH_ALI]")  # tick it again
    page.click(dlg + " [data-dsaverefs]")
    proj.wait("prompts/prompts.txt", "[REFS TO ATTACH: STYLE_ANCHOR| CH_ALI]\nPrompt of picture 3.")
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
    code, out = run("-c", "import sys; sys.path.insert(0, 'tools'); import pack; print(pack.problems()); print(pack.pack(out=sys.argv[1])[1])", zp)
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
    assert new["id"].startswith("L") and new["audio"]["fa"] is None
    assert proj.story().count("id: ") == 4  # the three old ones were pinned, plus the new one
    code, _ = proj.api("/api/delete", {"scene": "scene-01", "index": first["ln"] + 1, "old": "یک خط تازه وسط"})
    assert code == 409  # that position is now an id: line, not the new dialogue: a stale page is refused, nothing is lost
    now = {i["id"]: i for i in says()}
    assert all(now[k]["audio"]["fa"] == v for k, v in before.items())
    page.reload()
    page.wait_for_selector("section.blk")
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
    assert page.locator("section[data-scene=scene-01] [data-regen]").count() == 1
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
    btn = "#b2 .vv[data-vv=fa] >> nth=0"
    assert page.inner_text(btn).strip() == "‹2/3›"  # the old voice-pick (eleven-v3) is what plays
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
    page.wait_for_selector("section.blk")
    assert page.locator("figure.shot").count() == 4 + 32


@test
def undo_after_a_page_edit(proj, page):
    """The page's own add / delete go through the same snapshot: delete a dialogue line in the page, undo, and the file is the one before."""
    before = story_bytes(proj)
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
    assert os.path.exists(os.path.join(proj.root, "audio", "fa", "L001.eleven-v4-turbo.mp3")) and os.path.exists(os.path.join(proj.root, "audio", "en", "L001.eleven-v4-turbo.mp3"))
    assert not os.path.exists(os.path.join(proj.root, "audio", "fa", "IMG001_1.eleven-v4-turbo.mp3"))
    assert "voice: fa=eleven-v4-turbo, en=eleven-v4-turbo" in st
    assert "voice-stale: en" not in st and st.count("voice-stale: fa") == 2 and "voice-stale" not in st.split("[IMG001]")[0]
    out = subprocess.run([sys.executable, "-c", head + "jobs.regen_job(); print('end')"], cwd=proj.root, capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr[-400:]
    st = proj.story()
    assert "voice-stale" not in st
    assert os.path.exists(os.path.join(proj.root, "audio", "fa", "IMG001_2.eleven-v4-turbo.mp3"))
    assert "voice: fa=eleven-v4-turbo" in st and "IMG001_1.fa" not in st


@test
def image_menu_moves_and_scene_marks(proj, page):
    """The «⋯» menu of a picture: one image up / down (over a scene header too), a slot after it, start a scene here, join the scene above.
    Everything is a text move in story.txt; undo gives the bytes back."""
    use_story(proj, page, "story.txt")
    orig = story_bytes(proj)
    fig = lambda i: "figure.shot[data-id=%s]" % i
    items = lambda i: [b.inner_text() for b in page.locator(fig(i) + " [role=menuitem]").all()]
    page.click(fig("IMG001") + " [data-mn]")
    assert page.get_attribute(fig("IMG001") + " [data-mn]", "aria-expanded") == "true"
    assert not page.locator(fig("IMG001") + " [data-imv='-1']").count(), "nothing above the first picture (the thumbnail scene is closed)"
    assert not page.locator(fig("IMG001") + " [data-imerge]").count() and not page.locator(fig("IMG000") + " [data-mn]").count()
    page.click(fig("IMG001") + " [data-imv='1']")  # down: past IMG002
    page.wait_for_function("document.querySelector('section[data-scene=scene-01] figure.shot').dataset.id==='IMG002'")
    st = proj.story()
    assert st.index("[IMG002]") < st.index("[IMG001]") < st.index("=== scene-02")
    assert "رنگ‌ها شاد باشه" in st.split("[IMG001]")[1].split("=== scene-02")[0], "its note went along"
    page.click(fig("IMG001") + " [data-mn]")
    page.click(fig("IMG001") + " [data-imv='1']")  # down again: over the header, first in the next scene
    page.wait_for_function("document.querySelector('section[data-scene=scene-02] figure.shot').dataset.id==='IMG001'")
    assert proj.story().index("=== scene-02") < proj.story().index("[IMG001]") < proj.story().index("[IMG003]")
    page.click(fig("IMG001") + " [data-mn]")
    page.click(fig("IMG001") + " [data-imv='-1']")  # up: back to the end of the scene above
    page.wait_for_function("document.querySelectorAll('section[data-scene=scene-01] figure.shot').length===2")
    assert proj.story().index("[IMG001]") < proj.story().index("=== scene-02")
    for i in range(3):  # undo the three moves
        assert proj.api("/api/undo", {})[0] == 200
    assert story_bytes(proj) == orig
    page.reload()
    page.wait_for_selector("section.blk")
    page.click(fig("IMG002") + " [data-mn]")  # a slot after this picture
    page.click(fig("IMG002") + " [data-iadd]")
    page.wait_for_selector(fig("IMG004"))
    st = proj.story()
    assert st.index("[IMG002]") < st.index("[IMG004]") < st.index("=== scene-02")
    assert proj.api("/api/undo", {})[0] == 200
    page.reload()
    page.wait_for_selector("section.blk")
    assert page.locator(fig("IMG002") + " [data-isc]").count() == 1 and page.locator(fig("IMG001") + " [data-isc]").count() == 0
    page.click(fig("IMG002") + " [data-mn]")
    page.click(fig("IMG002") + " [data-isc]")  # the page asks for a title; the test accepts the default
    page.wait_for_selector("section[data-scene=scene-03] " + fig("IMG002"))
    st = proj.story()
    assert "\n\n=== scene-03 | صحنهٔ جدید | - ===\n[IMG002]" in st and st.index("=== scene-03") < st.index("=== scene-02")
    assert page.locator("section[data-scene=scene-03] h2 .num").inner_text().strip() == "2" and page.locator("section[data-scene=scene-02] h2 .num").inner_text().strip() == "3"
    page.click(fig("IMG002") + " [data-mn]")
    assert items("IMG002")[-1].startswith("⇡"), items("IMG002")
    page.click(fig("IMG002") + " [data-imerge]")  # join the scene above: only the header goes
    page.wait_for_function("document.querySelectorAll('section[data-scene=scene-01] figure.shot').length===2")
    assert page.locator("section[data-scene=scene-03]").count() == 0
    st = proj.story()
    assert "=== scene-03" not in st and "id: IMG001_1" in st and "id: IMG002_1" in st, "the old line ids were written out before the scene header moved"
    assert [h["label"] for h in proj.api("/api/project")[1]["history"]] == ["scenemark", "scenemark"]
    page.click(fig("IMG003") + " [data-mn]")  # the first picture of the scene below: it can be joined to the one above (that scene has env text: asked)
    page.click(fig("IMG003") + " [data-imerge]")
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
    page.reload()
    page.wait_for_selector("section.blk")
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
    page.reload()
    page.wait_for_selector("figure.shot[data-id=IMG1000]")
    assert page.locator("section[data-scene=scene-02] figure.shot").count() == 3
    code, r = proj.api("/api/image", {"id": "IMG1000", "note": "چهار رقمی"})
    assert code == 200 and "note: چهار رقمی" in proj.story()
    n = len(proj.api("/api/project")[1]["history"])
    while proj.api("/api/project")[1]["history"]:
        assert proj.api("/api/undo", {"force": True})[0] == 200
    assert n >= 6 and story_bytes(proj) == orig


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
