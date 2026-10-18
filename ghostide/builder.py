import json
import logging
import os
import re
import shutil
import zipfile

log = logging.getLogger("ghostide.builder")

SYSTEM = """You are GhostIDE, an autonomous software engineer. Reply with ONLY one JSON object:
{"name": "short-slug", "files": {"relative/path": "full file content"},
 "install": "shell command or empty", "test": "shell command running automated tests",
 "smoke": "shell command that starts the app, checks real behaviour end-to-end, then exits 0 on success"}
Rules: complete working code, include real tests, no placeholders, no secrets. Runs in a python:3.11-slim container."""


class BuildError(Exception):
    pass


def parse_manifest(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise BuildError("model reply contained no JSON")
    try:
        d = json.loads(m.group(0))
    except ValueError as e:
        raise BuildError("invalid JSON from model: %s" % e)
    if not isinstance(d.get("files"), dict) or not d["files"]:
        raise BuildError("manifest has no files")
    for k in ("install", "test", "smoke"):
        d[k] = d.get(k) or ""
    if not d["test"] or not d["smoke"]:
        raise BuildError("manifest must define test and smoke commands")
    d["name"] = re.sub(r"[^a-z0-9-]+", "-", str(d.get("name", "app")).lower()).strip("-") or "app"
    return d


def write_files(root, files):
    root = os.path.realpath(root)
    for rel in files:
        p = os.path.realpath(os.path.join(root, rel))
        if os.path.isabs(rel) or not p.startswith(root + os.sep):
            raise BuildError("unsafe file path rejected: %r" % rel)
    for name in os.listdir(root) if os.path.isdir(root) else []:  # clean slate: no stale files/bytecode
        full = os.path.join(root, name)
        shutil.rmtree(full) if os.path.isdir(full) and not os.path.islink(full) else os.remove(full)
    os.makedirs(root, exist_ok=True)
    for rel, content in files.items():
        p = os.path.realpath(os.path.join(root, rel))
        if os.path.isabs(rel) or not p.startswith(root + os.sep):
            raise BuildError("unsafe file path rejected: %r" % rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(str(content))


def make_zip(root, dest):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, fs in os.walk(root):
            dirs[:] = [x for x in dirs if x not in ("__pycache__", ".git", "node_modules", ".venv")]
            for f in fs:
                full = os.path.join(d, f)
                z.write(full, os.path.relpath(full, root))


class Builder:
    def __init__(self, cfg, llm, sandbox, store):
        self.cfg, self.llm, self.sandbox, self.store = cfg, llm, sandbox, store

    def build(self, pid, spec, progress=lambda m: None):
        bid = self.store.add_build(pid)

        def say(m):
            self.store.log(bid, m)
            progress(m)

        try:
            root = os.path.join(self.cfg.data_dir, "workspaces", str(pid), str(bid))
            os.makedirs(root, exist_ok=True)
            say("Generating project...")
            manifest = parse_manifest(self.llm.complete(SYSTEM, spec))
            attempt = 0
            while True:
                write_files(root, manifest["files"])
                ok, report = self._verify(root, manifest, say)
                if ok:
                    break
                if attempt >= self.cfg.max_repairs:
                    self.store.finish(bid, "failed", "Verification failed after %d repair attempts.\n%s" % (attempt, report[-1500:]))
                    return bid
                attempt += 1
                say("Repair attempt %d..." % attempt)
                prompt = "Spec:\n%s\n\nCurrent manifest:\n%s\n\nFailure:\n%s\n\nReturn the full corrected manifest JSON." % (
                    spec, json.dumps(manifest), report)
                manifest = parse_manifest(self.llm.complete(SYSTEM, prompt))
            zp = os.path.join(self.cfg.data_dir, "zips", "%s-%d.zip" % (manifest["name"], bid))
            os.makedirs(os.path.dirname(zp), exist_ok=True)
            make_zip(root, zp)
            self.store.finish(bid, "success", "Install, tests and smoke check all passed.", zp)
        except Exception as e:
            log.exception("build failed")
            self.store.finish(bid, "failed", "Build error: %s" % type(e).__name__ + ": " + str(e)[:500])
        return bid

    def _verify(self, root, m, say):
        for stage, net in (("install", True), ("test", False), ("smoke", False)):
            cmd = m[stage]
            if not cmd:
                continue
            say("Running %s: %s" % (stage, cmd))
            r = self.sandbox.run(cmd, root, network=net)
            if r.code != 0:
                say("%s FAILED (exit %s%s)" % (stage, r.code, ", timeout" if r.timed_out else ""))
                return False, "%s failed (exit %s)\n%s" % (stage, r.code, r.output)
            say("%s passed" % stage)
        return True, ""
