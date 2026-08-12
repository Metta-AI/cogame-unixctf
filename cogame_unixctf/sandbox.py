"""A persistent shell session.

The paper's agent issues shell commands into a live container where state — the
current directory, exported variables, sourced functions — persists across
turns. A fresh ``subprocess.run`` per command would lose that, so we keep one
long-lived ``bash`` and drive it with a sentinel marker to frame each command's
output and exit code.

Isolation note: commands run with ``cwd`` inside the episode's throwaway
directory but are NOT OS-sandboxed. The paper uses fresh containers; for
untrusted policies you should run this inside one too. Here the planted content
is benign and the intended commands are read-only recoveries.
"""

from __future__ import annotations

import os
import select
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass


@dataclass
class CommandResult:
    output: str
    exit_code: int
    timed_out: bool


class Shell:
    def __init__(self, cwd: str, env: dict | None = None, default_timeout: float = 10.0):
        self.default_timeout = default_timeout
        self._marker = f"__UNIXCTF_DONE_{uuid.uuid4().hex}__"
        base_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": cwd,
            "TERM": "dumb",
            "PS1": "",
            "LC_ALL": "C",
        }
        if env:
            base_env.update(env)
        self._proc = subprocess.Popen(
            ["bash", "--noprofile", "--norc"],
            cwd=cwd,
            env=base_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            bufsize=0,
        )
        self.alive = True

    def run(self, command: str, timeout: float | None = None) -> CommandResult:
        if not self.alive:
            return CommandResult("[shell terminated]", 137, True)
        timeout = self.default_timeout if timeout is None else timeout
        # Run the command, then echo the marker plus the exit code on its own line.
        payload = f"{command}\nprintf '\\n%s %s\\n' {self._marker} \"$?\"\n"
        try:
            self._proc.stdin.write(payload.encode())
            self._proc.stdin.flush()
        except BrokenPipeError:
            self.alive = False
            return CommandResult("[shell terminated]", 137, True)

        buf = bytearray()
        deadline = time.time() + timeout
        fd = self._proc.stdout.fileno()
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                self._kill()
                text = buf.decode(errors="replace")
                return CommandResult(text + "\n[timed out]", 124, True)
            r, _, _ = select.select([fd], [], [], min(0.2, remaining))
            if r:
                chunk = os.read(fd, 65536)
                if not chunk:
                    self.alive = False
                    break
                buf.extend(chunk)
                idx = buf.find(self._marker.encode())
                if idx != -1:
                    # Find end of the marker line to read the exit code.
                    end = buf.find(b"\n", idx)
                    if end == -1:
                        continue
                    marker_line = buf[idx:end].decode(errors="replace").strip()
                    try:
                        exit_code = int(marker_line.split()[-1])
                    except (ValueError, IndexError):
                        exit_code = -1
                    # Output is everything before the marker's own leading newline.
                    pre = bytes(buf[:idx]).rstrip(b"\n")
                    return CommandResult(pre.decode(errors="replace"), exit_code, False)
        return CommandResult(buf.decode(errors="replace"), -1, False)

    def _kill(self):
        self.alive = False
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def close(self):
        if self._proc.poll() is None:
            self._kill()
        try:
            self._proc.stdin.close()
        except Exception:
            pass
