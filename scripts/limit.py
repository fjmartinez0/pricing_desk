"""Run a command with a time limit; on expiry stop it and everything it started (D57).

macOS has no `timeout` command. launchd never starts a run while the previous one is still going, so one
step that never returns stops every later run without a sound (19–22 Nov 2026: seven runs lost). Every
step of run_daily.sh goes through this.

Usage: python3 scripts/limit.py SECONDS COMMAND [ARGS…]
Exit code: the command's own, or 124 when the time limit stopped it (as GNU timeout).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys

TIMED_OUT = 124


def descendants(root: int) -> list[int]:
    """Every process started under root. Playwright puts Chromium in its own process group, so stopping
    the step's group alone would leave the browser running."""
    out = subprocess.run(["ps", "-ax", "-o", "pid=,ppid="], capture_output=True, text=True).stdout
    kids: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            kids.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, todo = [], [root]
    while todo:
        for pid in kids.get(todo.pop(), []):
            found.append(pid)
            todo.append(pid)
    return found


def _signal(pids: list[int], group: int, sig: int) -> None:
    try:
        os.killpg(group, sig)
    except ProcessLookupError:
        pass
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def run(seconds: float, cmd: list[str]) -> int:
    proc = subprocess.Popen(cmd, start_new_session=True)       # own process group: we can stop all of it
    try:
        return proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        print(f"TIME LIMIT: {' '.join(cmd)[:120]} still running after {seconds:.0f} s; stopping it", flush=True)
        tree = descendants(proc.pid)          # before anything dies and its children lose their parent
        _signal(tree, proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        _signal(tree, proc.pid, signal.SIGKILL)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return TIMED_OUT


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    return run(float(argv[0]), argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
