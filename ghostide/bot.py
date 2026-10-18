import json
import logging
import threading
import time
import urllib.parse
import urllib.request

from .redact import redact

log = logging.getLogger("ghostide.bot")
HELP = ("GhostIDE: send a software idea, instructions, or a pasted ChatGPT conversation and I will build, "
        "test and zip it.\n/projects - list builds\n/get <build_id> - download zip\n/logs <build_id>\n/help")


class Bot:
    def __init__(self, cfg, builder, store, api=None):
        self.cfg, self.builder, self.store = cfg, builder, store
        self.api = api or self._api
        self.offset = 0

    def _api(self, method, params=None, files=None):
        url = "https://api.telegram.org/bot%s/%s" % (self.cfg.telegram_token, method)
        if files:
            b = "----ghost"
            body = b"".join(
                [("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode() for k, v in (params or {}).items()] +
                [("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n\r\n" % (b, k, n)).encode() + c + b"\r\n" for k, (n, c) in files.items()] +
                [("--%s--\r\n" % b).encode()])
            req = urllib.request.Request(url, body, {"Content-Type": "multipart/form-data; boundary=" + b})
        else:
            req = urllib.request.Request(url, urllib.parse.urlencode(params or {}).encode())
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.load(r)

    def send(self, chat, text):
        self.api("sendMessage", {"chat_id": chat, "text": text[:4000]})

    def handle(self, msg):
        chat, uid, text = msg["chat"]["id"], msg.get("from", {}).get("id"), (msg.get("text") or "").strip()
        if not text:
            return
        if uid not in self.cfg.allowed_users:
            self.send(chat, "Not authorized. Your Telegram id is %s; ask the owner to add it to GHOSTIDE_ALLOWED_USERS." % uid)
            return
        if text in ("/start", "/help"):
            return self.send(chat, HELP)
        if text == "/projects":
            rows = [(p[0], p[1]) for p in self.store.projects(uid)]
            lines = []
            for pid, name in rows:
                for b in self.store.builds(pid):
                    lines.append("build %s [%s] %s" % (b[0], b[1], name))
            return self.send(chat, "\n".join(lines) or "No builds yet.")
        if text.startswith("/get") or text.startswith("/logs"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                return self.send(chat, "Usage: /get <build_id> or /logs <build_id>")
            b = self.store.get_build(int(parts[1]))
            owned = b and any(p[0] == b[1] for p in self.store.projects(uid))
            if not owned:
                return self.send(chat, "Build not found.")
            if parts[0] == "/logs":
                return self.send(chat, redact("\n".join(self.store.logs(b[0]))[-3900:]) or "(empty)")
            if b[2] != "success" or not b[4]:
                return self.send(chat, "Build %s is %s; no verified zip available." % (b[0], b[2]))
            with open(b[4], "rb") as f:
                self.api("sendDocument", {"chat_id": chat}, {"document": (b[4].split("/")[-1], f.read())})
            return
        if text.startswith("/"):
            return self.send(chat, "Unknown command. /help")
        pid = self.store.add_project(uid, text[:40].replace("\n", " "), text)
        self.send(chat, "Building project %s... (this can take several minutes)" % pid)
        threading.Thread(target=self._run, args=(chat, pid, text), daemon=True).start()

    def _run(self, chat, pid, text):
        try:
            bid = self.builder.build(pid, text)
            b = self.store.get_build(bid)
            if b[2] == "success":
                self.send(chat, "Build %s VERIFIED: %s\nUse /get %s for the zip." % (bid, b[3], bid))
            else:
                self.send(chat, "Build %s FAILED (not verified).\n%s" % (bid, redact(b[3])))
        except Exception as e:
            log.exception("run failed")
            self.send(chat, "Internal error: %s" % type(e).__name__)

    def poll_forever(self):
        while True:
            try:
                r = self.api("getUpdates", {"offset": self.offset, "timeout": 50})
                for u in r.get("result", []):
                    self.offset = u["update_id"] + 1
                    if "message" in u:
                        self.handle(u["message"])
            except Exception as e:
                log.error("poll error: %s", type(e).__name__)
                time.sleep(5)
