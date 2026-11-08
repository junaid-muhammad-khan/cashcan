import os

import pytest

from cashcan_pi import servo
from cashcan_pi.lid import LidController
from cashcan_pi.servo import PrintPwm, PwmError, Servo, ServoLid, SysfsPwm, make_lid, parse_servos


def fake_chip(tmp_path, channel=0, exported=True):
    chip = tmp_path / "pwmchip0"
    chip.mkdir()
    (chip / "export").write_text("")
    if exported:
        d = chip / f"pwm{channel}"
        d.mkdir()
        for n in ("period", "duty_cycle", "enable"):
            (d / n).write_text("")
    return tmp_path


def read(tmp_path, name):
    return (tmp_path / "pwmchip0" / "pwm0" / name).read_text()


def test_angle_maps_to_pulse_width():
    s = Servo(PrintPwm(out=open(os.devnull, "w")))
    assert s.pulse_for(0) == 500 and s.pulse_for(180) == 2400 and s.pulse_for(90) == 1450
    assert s.pulse_for(-20) == 500 and s.pulse_for(999) == 2400


def test_sysfs_writes_period_duty_and_enable(tmp_path):
    root = fake_chip(tmp_path)
    Servo(SysfsPwm(0, 0, str(root))).move(90)
    assert read(root, "period") == "20000000" and read(root, "duty_cycle") == "1450000" and read(root, "enable") == "1"


def test_release_turns_the_signal_off(tmp_path):
    root = fake_chip(tmp_path)
    s = Servo(SysfsPwm(0, 0, str(root)))
    s.move(0)
    s.release()
    assert read(root, "enable") == "0"


def test_missing_chip_gives_a_helpful_error(tmp_path):
    with pytest.raises(PwmError, match="does not exist"):
        SysfsPwm(0, 0, str(tmp_path)).pulse(1000)


def test_a_can_opens_the_lid_and_no_can_keeps_it_shut():
    pwms = {"cans": PrintPwm("cans", out=open(os.devnull, "w")), "waste": PrintPwm("waste", out=open(os.devnull, "w"))}
    lid = ServoLid({k: Servo(v) for k, v in pwms.items()}, open_angle=90, closed_angle=0)
    assert pwms["cans"].log == [500] and pwms["waste"].log == [500]          # both start shut
    ctl = LidController(lid, hold=2.0)
    ctl.open("cans", now=0.0)
    assert pwms["cans"].log[-1] == 1450 and pwms["waste"].log[-1] == 500      # can: cans lid open, others shut
    ctl.tick(now=3.0)
    assert pwms["cans"].log[-1] == 500                                        # closes again after the hold
    n = len(pwms["cans"].log)
    ctl.tick(now=10.0)                                                        # no can: nothing moves
    assert len(pwms["cans"].log) == n


def test_bins_without_a_servo_are_ignored():
    lid = ServoLid({"cans": Servo(PrintPwm(out=open(os.devnull, "w")))})
    lid.set_open("organics", True)


def test_parse_servos():
    assert parse_servos("cans=0:0, waste=1:2") == {"cans": (0, 0), "waste": (1, 2)}
    for bad in ("", "cans", "cans=1", "cans=a:b"):
        with pytest.raises(ValueError):
            parse_servos(bad)


def test_make_lid_dry_run():
    assert isinstance(make_lid("cans=0:0", dry_run=True), ServoLid)


def test_cli_open_close_on_a_fake_chip(tmp_path):
    root = fake_chip(tmp_path)
    assert servo.main(["open", "--root", str(root)]) == 0
    assert read(root, "duty_cycle") == "1450000"
    assert servo.main(["close", "--root", str(root)]) == 0
    assert read(root, "duty_cycle") == "500000"


def test_cli_demo_none_stays_closed_and_can_opens(tmp_path):
    root = fake_chip(tmp_path)
    assert servo.main(["demo", "none", "--root", str(root)]) == 0
    assert read(root, "duty_cycle") == "500000"
    assert servo.main(["demo", "can", "--hold", "0", "--root", str(root)]) == 0
    assert read(root, "duty_cycle") == "500000"     # opened, held, closed again


def test_cli_reports_a_missing_chip(tmp_path):
    assert servo.main(["open", "--root", str(tmp_path)]) == 1
