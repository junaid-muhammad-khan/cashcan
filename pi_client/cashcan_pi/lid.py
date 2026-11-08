"""Opening the right lid. The hardware (servo, relay, solenoid) is not decided yet, so this is an interface plus two drivers:
SimulatedLid (prints, for development) and CommandLid (runs a shell command you configure per bin and per action, e.g. a gpioset
or servo script on the Radxa). LidController adds the timing: open, hold, close, one lid at a time."""
from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Callable, Protocol


class LidDriver(Protocol):
    def set_open(self, bin_name: str, is_open: bool) -> None: ...


class SimulatedLid:
    def __init__(self, out=sys.stderr):
        self.out, self.log = out, []

    def set_open(self, bin_name: str, is_open: bool) -> None:
        self.log.append((bin_name, is_open))
        print(f"[lid] {bin_name} {'OPEN' if is_open else 'closed'}", file=self.out, flush=True)


class CommandLid:
    """cmds: {"cans": {"open": "...", "close": "..."}, ...}; each value is a shell-style command line (no shell is invoked)."""

    def __init__(self, cmds: dict[str, dict[str, str]], runner: Callable[[list[str]], None] | None = None):
        self.cmds = cmds
        self._run = runner or (lambda argv: subprocess.run(argv, check=False, timeout=5))

    def set_open(self, bin_name: str, is_open: bool) -> None:
        cmd = self.cmds.get(bin_name, {}).get("open" if is_open else "close")
        if cmd:
            self._run(shlex.split(cmd))


class LidController:
    def __init__(self, driver: LidDriver, hold: float = 6.0):
        self.driver, self.hold = driver, hold
        self._open: str | None = None
        self._until = 0.0

    @property
    def open_bin(self) -> str | None:
        return self._open

    def open(self, bin_name: str, now: float) -> None:
        if self._open and self._open != bin_name:   # never two lids at once
            self.driver.set_open(self._open, False)
        if self._open != bin_name:
            self.driver.set_open(bin_name, True)
        self._open, self._until = bin_name, now + self.hold

    def tick(self, now: float) -> None:
        if self._open and now >= self._until:
            self.driver.set_open(self._open, False)
            self._open = None

    def close_all(self) -> None:
        if self._open:
            self.driver.set_open(self._open, False)
            self._open = None
