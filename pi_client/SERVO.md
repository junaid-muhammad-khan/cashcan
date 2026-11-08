# Servo lids

A can in front of the camera opens the **cans** lid for `--lid-seconds`, then it closes. No can (or nothing recognised) leaves the lid shut.
The code is `cashcan_pi/servo.py`. It drives the board's hardware PWM through `/sys/class/pwm`, so it needs no GPIO library and works on the
Radxa ROCK 5C Lite and on a Raspberry Pi. **It has not been run on the real hardware yet**; expect to adjust the angles and pulse range.

## Wiring (hobby servo, e.g. SG90 / MG90S)
- Servo **red** to an external 5 V supply (not the board's 3.3 V pin; a servo can brown the board out).
- Servo **brown/black** to that supply's ground **and** a board ground pin (grounds must be shared).
- Servo **orange/yellow** (signal) to a PWM-capable pin.

## One-time setup
1. Enable PWM for that pin (Radxa: `sudo rsetup`, Overlays; Raspberry Pi: add `dtoverlay=pwm,pin=18,func=2` to `/boot/firmware/config.txt`, reboot).
2. `ls /sys/class/pwm` shows `pwmchipN`. The channel is usually 0. Writing there needs root, so use `sudo` (or a udev rule).

## Try it by hand
```bash
sudo python3 -m cashcan_pi.servo test --chip 0 --channel 0        # closed, open, closed
sudo python3 -m cashcan_pi.servo demo can --chip 0 --channel 0    # opens for 4 s, then closes
sudo python3 -m cashcan_pi.servo demo none --chip 0 --channel 0   # stays shut
sudo python3 -m cashcan_pi.servo open --chip 0 --channel 0        # stays open (the signal keeps running after the command exits)
```
No hardware? Add `--dry-run` to print the pulses instead.

If the lid moves the wrong way, swap `--open-angle` / `--closed-angle`. If it buzzes at the end stops, narrow them (e.g. 10 and 80), or tune `--min-us` / `--max-us` (some servos want 1000 to 2000).

## In the bin
```bash
sudo python3 -m cashcan_pi --classify --servos cans=0:0 --servo-open-angle 90 --servo-closed-angle 0 ...
```
`bin=chip:channel`, comma separated: `cans=0:0,organics=0:1,waste=1:0`. A bin without a servo is ignored, so you can start with the cans lid alone.
`--servo-dry-run` prints pulses only. `--servos` and `--lids` cannot be combined (use `--lids` if you would rather call your own shell commands).

## Open when the camera sees a can (simplest mode)
```bash
sudo python3 -m cashcan_pi.canwatch --camera 0 --chip 0 --channel 0 --show
```
The lid opens after the camera sees a can on 3 looks in a row, stays open while the can is there, and closes 3 s after it is gone (`--hold`). No can: it stays shut.
`--threshold` (default 0.6) is how sure the camera must be, `--confirm` the looks in a row, `--dry-run` prints pulses without moving the servo.
