import os
import resource
import shutil
import subprocess
from dataclasses import dataclass


class SandboxUnavailable(Exception):
    pass


@dataclass
class Result:
    code: int
    output: str
    timed_out: bool = False


def _tail(b, n=20000):
    s = b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")
    return s[-n:]


class DockerSandbox:
    isolated = True

    def __init__(self, cfg):
        self.cfg = cfg

    def run(self, cmd, workdir, network=False, timeout=None):
        timeout = timeout or self.cfg.sandbox_timeout
        name = "ghostide-" + os.urandom(6).hex()
        args = ["docker", "run", "--rm", "--name", name, "-v", "%s:/app" % os.path.abspath(workdir), "-w", "/app",
                "--memory", self.cfg.sandbox_mem, "--cpus", str(self.cfg.sandbox_cpus),
                "--pids-limit", str(self.cfg.sandbox_pids), "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--read-only", "--tmpfs", "/tmp:size=64m",
                "-e", "PYTHONDONTWRITEBYTECODE=1", "--network", "bridge" if network else "none", self.cfg.sandbox_image, "sh", "-c", cmd]
        try:
            p = subprocess.run(args, capture_output=True, timeout=timeout)
            return Result(p.returncode, _tail(p.stdout + p.stderr))
        except subprocess.TimeoutExpired as e:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            return Result(124, _tail(e.stdout or b""), True)


class LocalUnsafeSandbox:
    """NOT isolated. rlimits + timeout only. Dev/test use; needs explicit opt-in."""
    isolated = False

    def __init__(self, cfg):
        self.cfg = cfg

    def run(self, cmd, workdir, network=False, timeout=None):
        timeout = timeout or self.cfg.sandbox_timeout

        def limits():
            os.setsid()
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
            resource.setrlimit(resource.RLIMIT_FSIZE, (50 << 20, 50 << 20))

        env = {"PATH": os.environ["PATH"], "HOME": workdir, "PYTHONDONTWRITEBYTECODE": "1"}  # no secrets inherited
        try:
            p = subprocess.run(["sh", "-c", cmd], cwd=workdir, env=env, capture_output=True,
                               timeout=timeout, preexec_fn=limits)
            return Result(p.returncode, _tail(p.stdout + p.stderr))
        except subprocess.TimeoutExpired as e:
            return Result(124, _tail(e.stdout or b""), True)


def get_sandbox(cfg):
    if shutil.which("docker"):
        return DockerSandbox(cfg)
    if cfg.allow_unsafe_local:
        return LocalUnsafeSandbox(cfg)
    raise SandboxUnavailable("Docker not found; refusing to run generated code on the host. "
                             "Install Docker (or set GHOSTIDE_ALLOW_UNSAFE_LOCAL=1 for dev only).")
