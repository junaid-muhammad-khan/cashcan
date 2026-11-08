"""Live preview window: what the bin sees and decides, drawn on the camera frame. For testing on a laptop; the Pi runs without it.

Top left: who is verified. Middle: the item region and what the classifier last decided. Bottom: the three lids, the open one lit.
"""
from __future__ import annotations

import cv2
import numpy as np

GREEN, RED, AMBER, GREY, WHITE = (60, 170, 70), (60, 60, 200), (0, 170, 230), (110, 110, 110), (255, 255, 255)
LIDS = ("organics", "cans", "waste")
SHOWN = {"cans": "recycle"}   # the bin people call the recycle bin; the model's class is still "cans"


def _text(img, s, org, color=WHITE, scale=0.6, bold=1):
    """Text on a solid dark label, so it stays readable over any camera picture."""
    (tw, th), base = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, scale, bold)
    x, y = org
    cv2.rectangle(img, (x - 5, y - th - 5), (x + tw + 5, y + base + 3), (25, 25, 25), -1)
    cv2.putText(img, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, bold, cv2.LINE_AA)


def draw(frame: np.ndarray, status: dict, indicator_state: str, indicator_msg: str, roi) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]
    x1, y1, x2, y2 = roi
    cv2.rectangle(out, (int(x1 * w), int(y1 * h)), (int(x2 * w) - 1, int(y2 * h) - 1),
                  AMBER if status["gate"] == "present" else GREY, 2)
    _text(out, "item region", (int(x1 * w) + 6, int(y1 * h) + 20), GREY, 0.5)

    who = status["user_id"]
    if who:
        _text(out, f"VERIFIED: {who[:12]}", (12, 28), GREEN, 0.7, 2)
    else:
        label = {"challenge": "turn your head as asked", "scanning": "looking for your face", "denied": "not recognised",
                 "error": "cannot reach server"}.get(indicator_state, "no one verified")
        _text(out, f"NOT VERIFIED - {label}", (12, 28), AMBER if indicator_state in ("challenge", "scanning") else RED, 0.7, 2)
    if indicator_msg:
        _text(out, indicator_msg[:70], (12, 54), WHITE, 0.5)

    item = status["last_item"]
    if status["collecting_looks"]:
        _text(out, "classifying...", (12, 84), AMBER, 0.7, 2)
    elif item:
        pay = f"reward {item['reward_lamports'] / 1e9:g} SOL" if item["reward_lamports"] else "no reward"
        note = " (unsure -> waste)" if item["reason"] == "low_confidence" else ""
        _text(out, f"ITEM: {SHOWN.get(item['bin'], item['bin']).upper()} {item['confidence'] * 100:.0f}%{note}", (12, 84), WHITE, 0.7, 2)
        _text(out, f"{pay} - {'paid to ' + item['user_id'][:8] if item['user_id'] else 'nobody verified'}", (12, 110), WHITE, 0.55)
    else:
        _text(out, "show an item and hold it still in the box", (12, 84), GREY, 0.6)

    ident = status.get("identity") or {}
    seen = ident.get("face_seen")
    rep = ident.get("last_reply") or {}
    srv = (f"matched {rep.get('score', 0) * 100:.0f}%" if rep.get("matched") else
           f"{rep.get('reason', '-')}" + (f" {rep['score'] * 100:.0f}%" if rep.get("score") is not None else "")) if rep else "no answer yet"
    _text(out, f"local face check: {'face' if seen else 'no face' if seen is False else '-'}  |  server: {srv}", (12, h - 58), (200, 200, 200), 0.45)

    bw = w // 3
    for i, name in enumerate(LIDS):
        lit = status["open_lid"] == name
        x = i * bw
        cv2.rectangle(out, (x + 4, h - 46), (x + bw - 4, h - 6), GREEN if lit else (40, 40, 40), -1)
        label = f"{SHOWN.get(name, name).upper()} OPEN" if lit else SHOWN.get(name, name).upper()
        (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2 if lit else 1)
        cv2.putText(out, label, (x + (bw - tw) // 2, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE if lit else (170, 170, 170), 2 if lit else 1, cv2.LINE_AA)
    return out
