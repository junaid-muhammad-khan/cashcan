"""Servo lids for the bin: a can opens the cans lid, no can leaves it shut.

Hobby servos (SG90, MG90S, MG996R...) want a 50 Hz pulse train whose pulse width sets the angle (about 0.5 ms = 0 degrees,
2.4 ms = 180 degrees). This talks to the board's *hardware* PWM through the standard Linux sysfs interface, so the same code runs
on the Radxa ROCK 5C Lite and on a Raspberry Pi, with no GPIO library. The kernel keeps the pulses going after this program exits,
which is exactly what a lid needs: it stays where you put it.

Use it three ways:
  1. inside the bin:   python -m cashcan_pi --classify --servos cans=0:0,organics=0:1,waste=1:0 ...        (bin=chip:channel)
  2. from lids.json:   {"cans": {"open": "python3 -m cashcan_pi.servo open --chip 0 --channel 0", "close": "... close ..."}}
  3. by hand:          python3 -m cashcan_pi.servo test --chip 0 --channel 0
Wiring and setup: SERVO.md. Not yet tried on the real hardware: the numbers (angles, pulse range) will need adjusting to your servo and lid.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

PERIOD_NS = 20_000_000          # 50 Hz
DEFAULT_ROOT = "/sys/class/pwm"
MIN_US, MAX_US = 500, 2400      # pulse width at 0 and at 180 degrees; SG90-class servos. Some want 1000-2000.


class PwmError(RuntimeError):
    pass


class SysfsPwm:
    """One hardware PWM channel: /sys/class/pwm/pwmchip<chip>/pwm<channel>."""

    def __init__(self, chip: int = 0, channel: int = 0, root: str = DEFAULT_ROOT, wait: float = 1.0):
        self.chip_dir = os.path.join(root, f"pwmchip{chip}")
        self.dir = os.path.join(self.chip_dir, f"pwm{channel}")
        self.channel, self.wait = channel, wait

    def _write(self, name: str, value: int | str) -> None:
        try:
            with open(os.path.join(self.dir, name), "w") as f:
                f.write(str(value))
        except PermissionError as e:
            raise PwmError(f"No permission to write {self.dir}/{name}. Run with sudo, or give your user access to /sys/class/pwm (see SERVO.md).") from e

    def _ready(self) -> None:
        if os.path.isdir(self.dir):
            return
        if not os.path.isdir(self.chip_dir):
            raise PwmError(f"{self.chip_dir} does not exist. Enable a PWM overlay for your board and check `ls /sys/class/pwm` (see SERVO.md).")
        try:
            with open(os.path.join(self.chip_dir, "export"), "w") as f:
                f.write(str(self.channel))
        except PermissionError as e:
            raise PwmError(f"No permission to export PWM channel {self.channel}. Run with sudo (see SERVO.md).") from e
        end = time.monotonic() + self.wait
        while not os.path.isdir(self.dir):          # the kernel creates the folder a moment after export
            if time.monotonic() > end:
                raise PwmError(f"PWM channel {self.channel} did not appear under {self.chip_dir} after export. Is that channel wired to a pin?")
            time.sleep(0.02)

    def pulse(self, microseconds: float) -> None:
        """Send pulses of this width, 50 times a second, until told otherwise (also after this program exits)."""
        self._ready()
        self._write("period", PERIOD_NS)
        self._write("duty_cycle", int(round(microseconds * 1000)))
        self._write("enable", 1)

    def stop(self) -> None:
        """No signal at all: the servo goes limp and stops humming."""
        if os.path.isdir(self.dir):
            self._write("enable", 0)


class PrintPwm:
    """Stand-in that only prints, for trying the logic on a laptop (--dry-run)."""

    def __init__(self, name: str = "servo", out=sys.stderr):
        self.name, self.out, self.log = name, out, []

    def pulse(self, microseconds: float) -> None:
        self.log.append(microseconds)
        print(f"[servo {self.name}] pulse {microseconds:.0f} us", file=self.out, flush=True)

    def stop(self) -> None:
        self.log.append(None)
        print(f"[servo {self.name}] released", file=self.out, flush=True)


class Servo:
    def __init__(self, pwm, min_us: float = MIN_US, max_us: float = MAX_US):
        self.pwm, self.min_us, self.max_us = pwm, min_us, max_us

    def pulse_for(self, angle: float) -> float:
        angle = max(0.0, min(180.0, float(angle)))
        return self.min_us + (self.max_us - self.min_us) * angle / 180.0

    def move(self, angle: float) -> None:
        self.pwm.pulse(self.pulse_for(angle))

    def release(self) -> None:
        self.pwm.stop()


class ServoLid:
    """The lid driver the bin controller talks to (set_open per bin). A bin with no servo is ignored, so you can start with just the cans lid."""

    def __init__(self, servos: dict[str, Servo], open_angle: float = 90, closed_angle: float = 0, start_closed: bool = True):
        self.servos, self.open_angle, self.closed_angle = servos, open_angle, closed_angle
        if start_closed:
            for s in servos.values():
                s.move(closed_angle)

    def set_open(self, bin_name: str, is_open: bool) -> None:
        s = self.servos.get(bin_name)
        if s:
            s.move(self.open_angle if is_open else self.closed_angle)

    def release_all(self) -> None:
        for s in self.servos.values():
            s.release()


def parse_servos(spec: str) -> dict[str, tuple[int, int]]:
    """'cans=0:0,organics=0:1' -> {'cans': (0, 0), 'organics': (0, 1)}  (bin = pwmchip:channel)."""
    out: dict[str, tuple[int, int]] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            name, where = part.split("=")
            chip, channel = where.split(":")
            out[name.strip()] = (int(chip), int(channel))
        except ValueError:
            raise ValueError(f"'{part}' is not bin=chip:channel, for example cans=0:0") from None
    if not out:
        raise ValueError("no servos given; use bin=chip:channel, for example cans=0:0,waste=0:1")
    return out


def make_lid(spec: str, open_angle: float = 90, closed_angle: float = 0, root: str = DEFAULT_ROOT,
             min_us: float = MIN_US, max_us: float = MAX_US, dry_run: bool = False) -> ServoLid:
    servos = {}
    for name, (chip, channel) in parse_servos(spec).items():
        pwm = PrintPwm(name) if dry_run else SysfsPwm(chip, channel, root)
        servos[name] = Servo(pwm, min_us, max_us)
    return ServoLid(servos, open_angle, closed_angle)


# ---------------------------------------------------------------------------------------------- command line
def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--chip", type=int, default=0, help="the pwmchip number (ls /sys/class/pwm)")
    p.add_argument("--channel", type=int, default=0, help="the channel on that chip")
    p.add_argument("--open-angle", type=float, default=90)
    p.add_argument("--closed-angle", type=float, default=0)
    p.add_argument("--min-us", type=float, default=MIN_US, help="pulse width at 0 degrees")
    p.add_argument("--max-us", type=float, default=MAX_US, help="pulse width at 180 degrees")
    p.add_argument("--root", default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    p.add_argument("--dry-run", action="store_true", help="only print what would be sent")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m cashcan_pi.servo", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("open", "open the lid and leave it open"), ("close", "close the lid and leave it closed"),
                           ("release", "stop sending pulses (servo goes limp)"), ("test", "close, open, close again: checks wiring and direction")):
        _add_common(sub.add_parser(name, help=helptext))
    m = sub.add_parser("move", help="go to an angle (0-180) and stay there")
    _add_common(m)
    m.add_argument("--angle", type=float, required=True)
    d = sub.add_parser("demo", help="what the bin does: 'can' opens the cans lid for a few seconds, 'none' leaves it shut")
    _add_common(d)
    d.add_argument("what", choices=["can", "none"])
    d.add_argument("--hold", type=float, default=4.0, help="seconds the lid stays open")
    a = ap.parse_args(argv)

    pwm = PrintPwm(f"pwm{a.chip}.{a.channel}") if a.dry_run else SysfsPwm(a.chip, a.channel, a.root)
    servo = Servo(pwm, a.min_us, a.max_us)
    try:
        if a.cmd == "open":
            servo.move(a.open_angle)
        elif a.cmd == "close":
            servo.move(a.closed_angle)
        elif a.cmd == "move":
            servo.move(a.angle)
        elif a.cmd == "release":
            servo.release()
        elif a.cmd == "test":
            for label, angle in (("closed", a.closed_angle), ("open", a.open_angle), ("closed", a.closed_angle)):
                print(f"servo: {label} ({angle:g} degrees)", file=sys.stderr)
                servo.move(angle)
                time.sleep(1.2)
        elif a.cmd == "demo":
            if a.what == "none":
                servo.move(a.closed_angle)
                print("servo: no can, the lid stays closed", file=sys.stderr)
            else:
                servo.move(a.open_angle)
                print(f"servo: can! lid open for {a.hold:g} s", file=sys.stderr)
                time.sleep(a.hold)
                servo.move(a.closed_angle)
                print("servo: lid closed again", file=sys.stderr)
    except PwmError as e:
        print(f"servo: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
