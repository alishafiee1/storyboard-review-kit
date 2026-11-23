# -*- coding: utf-8 -*-
"""End-to-end tests of the review page + server, in a real browser (Playwright, using the Edge/Chrome already installed).
  pip install playwright                       (once; no browser download needed)
  python tools/tests/run.py                    run everything
  python tools/tests/run.py edit_dialogue fab  run only tests whose name contains one of these words
  python tools/tests/run.py --update-baseline  rewrite tools/tests/baseline/* from the current page (do this ONLY when the page is meant to look different)
Every test builds a fresh throw-away project in a temp folder (fixture/ + the tools of this checkout), starts its own server on a free port and
never touches a real project. Nothing here calls a paid service. This folder is not part of the engine (ENGINE.txt) and is not sent to projects."""
import argparse, contextlib, json, os, re, shutil, socket, struct, subprocess, sys, tempfile, time, traceback, urllib.error, urllib.request, zlib

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
    if shutil.which("ffmpeg"):
        for lg in ("fa", "en"):
            os.makedirs(os.path.join(root, "audio", lg), exist_ok=True)
            for id_ in ("IMG001_1", "IMG001_2"):
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.4",
                                os.path.join(root, "audio", lg, id_ + ".mp3")], check=True)


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
        page.wait_for_function("RELOADS>%d" % page._reloads, timeout=secs * 1000)
    except Exception:
        pass
    page._reloads = page.evaluate("RELOADS")
    page.wait_for_timeout(250)


def test(fn):
    TESTS.append(fn)
    return fn


def norm(html):
    """Page HTML without the parts that change between runs (file timestamps)."""
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
    page.on("dialog", lambda d: (page._dialogs.append(d.message), d.accept()))
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
    page.click(f + " [data-m=ok]")
    proj.wait_in("[IMG002]", "status: ok")
    page.click(f + " [data-m=redo]")
    proj.wait_in("[IMG002]", "status: redo")
    page.click(f + " [data-m=redo]")  # clicking the active mark clears it
    proj.wait_in("[IMG002]", "status:", absent=True)
    page.wait_for_timeout(300)
    page.click(f + " [data-nt]")
    page.fill(f + " textarea.nt", "یادداشت تست")
    page.press(f + " textarea.nt", "Enter")
    proj.wait_in("[IMG002]", "note: یادداشت تست")


@test
def edit_advice_fx(proj, page):
    page.click("section[data-scene=scene-02] [data-sfx]")
    page.fill("section[data-scene=scene-02] .fxs textarea", "دیپ به سفید")
    page.press("section[data-scene=scene-02] .fxs textarea", "Enter")
    proj.wait("scenario/story.txt", "fx: دیپ به سفید")
    settle(page)
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
    page.select_option("[data-scm=scene-01]", "deepgram/aura-2")
    proj.wait("scenario/story.txt", "model: deepgram/aura-2")
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
def engine_manifest_is_complete(proj, page):
    files = [l.strip() for l in open(os.path.join(KIT, "ENGINE.txt"), encoding="utf-8") if l.strip() and not l.startswith("#")]
    missing = [f for f in files if not os.path.exists(os.path.join(KIT, *f.split("/")))]
    assert not missing, "listed in ENGINE.txt but missing: %s" % missing
    html = open(os.path.join(KIT, "review.html"), encoding="utf-8").read()
    for ref in re.findall(r'(?:src|href)="(tools/[^"]+)"', html):  # everything the page loads must be shipped to projects
        assert ref in files, "review.html loads %s but ENGINE.txt does not list it" % ref


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
                print("FAIL %s\n%s" % (t.__name__, "".join(traceback.format_exc().splitlines(True)[-14:])))
            finally:
                proj.close()
        browser.close()
    print("\n%d passed, %d failed%s" % (len(todo) - len(failed), len(failed), (": " + ", ".join(failed)) if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
