"""Status feedback for the person at the bin. Console by default, LEDs if gpiozero is installed."""
from __future__ import annotations

import sys

STATES = ("idle", "scanning", "matched", "denied", "error")


class ConsoleIndicator:
    def __init__(self, out=sys.stderr):
        self._out, self._last = out, None

    def set(self, state: str, message: str = "") -> None:
        key = (state, message)
        if key != self._last:
            self._last = key
            print(f"[indicator] {state}" + (f": {message}" if message else ""), file=self._out)


class GpioIndicator(ConsoleIndicator):
    """green = matched, red = denied/error, amber = scanning. Pins are BCM numbers."""

    def __init__(self, green: int, red: int, amber: int, **kw):
        super().__init__(**kw)
        from gpiozero import LED  # only exists on the Pi

        self._leds = {"green": LED(green), "red": LED(red), "amber": LED(amber)}

    def set(self, state: str, message: str = "") -> None:
        super().set(state, message)
        on = {"matched": "green", "denied": "red", "error": "red", "scanning": "amber"}.get(state)
        for name, led in self._leds.items():
            led.on() if name == on else led.off()
