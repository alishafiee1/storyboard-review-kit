# -*- coding: utf-8 -*-
"""Review server for review.html. Reads and edits two plain-text files:
  scenario/story.txt     (scenes, dialogue FA + optional en: lines, notes, flags, format-issue notes)
  prompts/prompts.txt    (one complete Flow prompt per image / reference)
Run:  python tools/serve.py   (or double-click click-for-review.bat)  ->  http://127.0.0.1:8765/review.html
Listens on 127.0.0.1 only and stops by itself ~90 s after the page is closed.
This file is only the HTTP layer; the logic lives in kitcore / story / media / edits / jobs / project (see docs/ARCHITECTURE.md)."""
import functools, http.server, json, os, sys, threading, time, urllib.parse
from kitcore import Conflict, HIDDEN, IDLE, LOCK, PORT, ROOT
from api import handle
from jobs import JOB, SLOW
from project import project
import batch, watch
import settings as kitsettings  # (the star imports below bring in another name «settings»)
from flowname import config

# Older project scripts do «from serve import ROOT, spoken_lines, ...» (serve.py used to hold everything). Keep those names importable from here.
from kitcore import *  # noqa: F401,F403,E402
from story import *  # noqa: F401,F403,E402
from media import *  # noqa: F401,F403,E402
from edits import *  # noqa: F401,F403,E402
from lineedits import *  # noqa: F401,F403,E402
from promptedits import *  # noqa: F401,F403,E402

last_ping, seen_ping = [time.time()], [False]
WATCHING = [False]  # True while the Downloads watcher thread runs (on by default; the settings panel or kit-config.json "watch_downloads": false switches it)


class H(http.server.SimpleHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/project":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            book = (q.get("book") or ["story"])[0]
            if book not in ("story", "refs"):
                book = "story"
            return self._json(200, project(book=book))
        if p == "/api/imports":
            return self._json(200, dict(imports=watch.recent_imports(), watching=WATCHING[0], downloads=watch.downloads_dir()))
        if p == "/api/batch":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                r = batch.batch_text((q.get("b") or [""])[0])
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            if (q.get("format") or [""])[0] == "text":
                b = r["text"].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            return self._json(200, r)
        if p == "/api/settings":
            return self._json(200, dict(kitsettings.get(), watching=WATCHING[0]))
        if p == "/api/job":
            return self._json(200, JOB)
        if p == "/api/ping":
            last_ping[0], seen_ping[0] = time.time(), True
            return self._json(200, {"ok": True})
        if HIDDEN.search(urllib.parse.unquote(p)):  # never serve .env, .git, .engine-backup, the server's own sources or temp files
            return self._json(404, {"error": "not found"})
        if p == "/":
            self.send_response(302)
            self.send_header("Location", "/review.html")
            self.end_headers()
            return
        return super().do_GET()

    def do_POST(self):
        o = self.headers.get("Origin")  # a web page of another site must not write to the project (the key, the folders)
        if o and urllib.parse.urlparse(o).hostname not in ("127.0.0.1", "localhost", "::1"):
            return self._json(403, {"error": "forbidden origin"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 200000:
            return self._json(400, {"error": "bad size"})
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            if self.path in SLOW:
                return self._json(200, SLOW[self.path](d))
            with LOCK:
                return self._json(200, handle(self.path, d))
        except Conflict as e:
            return self._json(409, {"error": str(e)})
        except (ValueError, KeyError, TypeError) as e:
            return self._json(400, {"error": str(e)})

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=ROOT))
    print(f"http://127.0.0.1:{PORT}/review.html", flush=True)

    def watchdog():  # page pings every 5 s; background tabs are slowed down, so wait IDLE s (3x before the first ping)
        while True:
            time.sleep(2)
            if time.time() - last_ping[0] > (IDLE if seen_ping[0] else IDLE * 3):
                srv.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()

    def watcher():  # the page can switch it on and off, so look at the setting on every pass
        while True:
            try:
                WATCHING[0] = kitsettings.watch_enabled()
                if WATCHING[0]:
                    watch.run_once(settle=1.0)
            except Exception as e:  # a bad file or a busy disk must not stop the watcher
                print("watch:", e, file=sys.stderr, flush=True)
            time.sleep(3.0)

    threading.Thread(target=watcher, daemon=True).start()
    srv.serve_forever()
    print("stopped (page closed)", flush=True)
