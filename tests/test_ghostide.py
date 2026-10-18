import json
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from unittest import mock

from ghostide.bot import Bot
from ghostide.builder import Builder, BuildError, parse_manifest, write_files
from ghostide.config import Config
from ghostide.dashboard import make_server
from ghostide.redact import redact, register
from ghostide.sandbox import LocalUnsafeSandbox, SandboxUnavailable, get_sandbox
from ghostide.store import Store

GOOD = {"name": "Hello App", "files": {"app.py": "def add(a,b):\n    return a+b\n",
        "test_app.py": "import unittest\nfrom app import add\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1,2),3)\n"},
        "install": "", "test": "python3 -m unittest discover -p 'test_*.py'",
        "smoke": "python3 -c 'import app; assert app.add(2,2)==4'"}
BAD = dict(GOOD, files=dict(GOOD["files"], **{"app.py": "def add(a,b):\n    return a-b\n"}))


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return "```json\n" + json.dumps(self.replies.pop(0)) + "\n```"


class FakeApi:
    def __init__(self):
        self.sent = []

    def __call__(self, method, params=None, files=None):
        self.sent.append((method, params, files))


class T(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name
        self.cfg = Config(data_dir=d.name, allow_unsafe_local=True, sandbox_timeout=20, max_repairs=2, allowed_users=(1,))
        self.store = Store(d.name + "/db")
        self.sb = LocalUnsafeSandbox(self.cfg)

    def test_build_success_and_zip(self):
        pid = self.store.add_project(1, "p", "spec")
        bid = Builder(self.cfg, FakeLLM(GOOD), self.sb, self.store).build(pid, "spec")
        b = self.store.get_build(bid)
        self.assertEqual(b[2], "success")
        self.assertIn("app.py", zipfile.ZipFile(b[4]).namelist())

    def test_repair_loop_fixes_failure(self):
        pid = self.store.add_project(1, "p", "spec")
        llm = FakeLLM(BAD, GOOD)
        bid = Builder(self.cfg, llm, self.sb, self.store).build(pid, "spec")
        self.assertEqual(self.store.get_build(bid)[2], "success")
        self.assertEqual(llm.calls, 2)
        self.assertTrue(any("Repair attempt 1" in l for l in self.store.logs(bid)))

    def test_never_reports_success_when_tests_fail(self):
        pid = self.store.add_project(1, "p", "spec")
        bid = Builder(self.cfg, FakeLLM(BAD, BAD, BAD), self.sb, self.store).build(pid, "spec")
        b = self.store.get_build(bid)
        self.assertEqual(b[2], "failed")
        self.assertIsNone(b[4])

    def test_path_traversal_rejected(self):
        with self.assertRaises(BuildError):
            write_files(self.dir + "/w", {"../evil.py": "x"})
        with self.assertRaises(BuildError):
            write_files(self.dir, {"/etc/evil": "x"})

    def test_manifest_requires_tests(self):
        with self.assertRaises(BuildError):
            parse_manifest(json.dumps({"files": {"a": "b"}, "test": "", "smoke": "x"}))

    def test_timeout(self):
        self.assertTrue(self.sb.run("sleep 30", self.dir, timeout=1).timed_out)

    def test_sandbox_does_not_leak_env(self):
        with mock.patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "secretvalue"}):
            self.assertNotIn("secretvalue", self.sb.run("env", self.dir).output)

    def test_refuses_host_execution_without_optin(self):
        with mock.patch("shutil.which", lambda n: None):
            with self.assertRaises(SandboxUnavailable):
                get_sandbox(Config())

    def test_redaction(self):
        register("my-super-secret")
        self.assertNotIn("my-super-secret", redact("x my-super-secret y"))
        self.assertNotIn("123456789:", redact("tok 123456789:" + "A" * 35))

    def test_bot_auth_and_flow(self):
        api = FakeApi()
        bot = Bot(self.cfg, Builder(self.cfg, FakeLLM(GOOD), self.sb, self.store), self.store, api)
        bot.handle({"chat": {"id": 9}, "from": {"id": 2}, "text": "build me x"})
        self.assertIn("Not authorized", api.sent[-1][1]["text"])
        self.assertFalse(self.store.projects())
        bot._run(9, self.store.add_project(1, "p", "s"), "s")
        self.assertIn("VERIFIED", api.sent[-1][1]["text"])
        bot.handle({"chat": {"id": 9}, "from": {"id": 1}, "text": "/get 1"})
        self.assertEqual(api.sent[-1][0], "sendDocument")
        bot.handle({"chat": {"id": 9}, "from": {"id": 3}, "text": "/get 1"})
        self.assertIn("Not authorized", api.sent[-1][1]["text"])

    def test_dashboard_auth_and_data(self):
        pid = self.store.add_project(1, "p", "s")
        bid = self.store.add_build(pid)
        self.store.log(bid, "hello")
        srv = make_server(self.store, "tok", port=0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        with self.assertRaises(Exception):
            urllib.request.urlopen(base + "/api/projects")
        req = urllib.request.Request(base + "/api/builds/%d/logs" % bid, headers={"Authorization": "Bearer tok"})
        self.assertEqual(json.load(urllib.request.urlopen(req)), ["hello"])
        self.assertTrue(json.load(urllib.request.urlopen(base + "/health"))["ok"])


if __name__ == "__main__":
    unittest.main()
