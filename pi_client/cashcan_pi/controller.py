"""One camera, two jobs: who is this, and what are they throwing?

  frame -> BinLoop        (face match + head-turn check -> a live session = a logged-in, verified person)
        -> ItemGate       (is an item being presented and held still?)
        -> classifier     (organics / cans / waste, averaged over a few looks)
        -> LidController  (opens THE RIGHT lid, whether or not anyone is identified)
        -> POST /interactions (the record; the SERVER decides the reward and pays it, the bin only reports what it saw)

Rules
- The lid opens for every confident item, identified or not: nobody is blocked from sorting. An unsure item goes to the waste lid.
- Reward: decided by the face API (face_api/app/rewards.py: 5 cents CAD per can, paid in devnet SOL), only for a live, verified
  session and a confident classification. The bin sends no amount. Nobody identified -> the item is still recorded (no payout),
  so the dashboard counts it. The server's answer (reward_cents, payout_status) is shown in the item event and the preview.
- Records carry an interaction_id chosen here. A failed send waits in a short-lived outbox (TTL) and is retried with the SAME id,
  so the server stores it once. No face data is ever in the outbox.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from .classifier import average_probs, decide
from .lid import LidController


def server_outcome(res: dict) -> dict:
    """The parts of the server's answer worth showing: reward (CAD cents), payout status, why there is no reward, tx."""
    return {k: res.get(k) for k in ("reward_cents", "payout_status", "reason", "tx_signature") if k in res}


@dataclass
class Pending:
    payload: dict
    expires: float
    next_try: float = 0.0
    tries: int = 0


class Outbox:
    """Short-lived retry queue for interaction records (never holds biometric data)."""

    def __init__(self, api, ttl: float = 600.0, backoff: float = 5.0, on_event: Callable[[dict], None] = lambda e: None):
        self.api, self.ttl, self.backoff, self.emit = api, ttl, backoff, on_event
        self.items: list[Pending] = []

    def send(self, payload: dict, now: float) -> dict | None:
        """Try now and return the server's answer; on a network or server problem keep it for later (None).
        A 4xx means the server refuses it for good, so drop it."""
        import httpx

        try:
            return self.api.interaction(payload) or {}
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                self.emit({"event": "interaction_rejected", "interaction_id": payload["interaction_id"], "status": e.response.status_code})
                return None
        except (httpx.HTTPError, ValueError):
            pass
        self.items.append(Pending(payload, now + self.ttl, now + self.backoff, 1))
        self.emit({"event": "interaction_queued", "interaction_id": payload["interaction_id"]})
        return None

    def flush(self, now: float) -> None:
        import httpx

        keep = []
        for p in self.items:
            if now > p.expires:
                self.emit({"event": "interaction_dropped", "interaction_id": p.payload["interaction_id"], "why": "expired"})
                continue
            if now < p.next_try:
                keep.append(p)
                continue
            try:
                res = self.api.interaction(p.payload) or {}
                self.emit({"event": "interaction_recorded", "interaction_id": p.payload["interaction_id"], "after_retries": p.tries,
                           **server_outcome(res)})
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    p.tries, p.next_try = p.tries + 1, now + self.backoff * min(p.tries + 1, 6)
                    keep.append(p)
            except (httpx.HTTPError, ValueError):
                p.tries, p.next_try = p.tries + 1, now + self.backoff * min(p.tries + 1, 6)
                keep.append(p)
        self.items = keep


@dataclass
class BinController:
    loop: object               # BinLoop (identity)
    gate: object               # ItemGate
    classifier: object         # .probs(frame) -> {bin: p}
    lid: LidController
    outbox: Outbox
    on_event: Callable[[dict], None] = lambda e: None
    bin_id: str = "bin-1"
    min_confidence: float = 0.60
    votes: int = 3
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex
    switch_margin: float = 0.12    # to move the lid, the new bin must lead the current one by this much (averaged), twice in a row
    teach_gap: float = 0.5         # ignore teach key presses closer together than this (a held-down key)
    reeval_interval: float = 1.0   # while an item is held in the box, look at it again this often and update the decision
    save_dir: str | None = None   # save a photo of every item the bin looks at (see _save_photo): the raw material for retraining on this camera

    def __post_init__(self):
        self._votes: list[dict] | None = None
        self._first_crop = None
        self._crop = None
        self._last_frame = None
        self._committed: dict | None = None   # the decision currently in force for the item in the box: bin, confidence, reason
        self._recent: list[dict] = []         # the last few looks, averaged so one odd frame does not flip the decision
        self._next_reeval = 0.0
        self._pending: str | None = None     # a bin that has led once and must lead again before the lid moves
        self._last_teach = -1e9
        self.last_item: dict | None = None   # most recent decision, for the preview window
        self.last_item_at = 0.0

    def status(self, now: float) -> dict:
        """What the bin is doing right now, for the preview window and for debugging."""
        session = self.loop.current_session(now)
        return {"user_id": session.user_id if session else None,
                "gate": getattr(self.gate, "state", "?"),
                "collecting_looks": self._votes is not None,
                "open_lid": self.lid.open_bin,
                "last_item": self.last_item if now - self.last_item_at < 15 else None,
                "identity": self.loop.info() if hasattr(self.loop, "info") else {},
                "gate_why": getattr(self.gate, "why", ""),
                "can_teach": hasattr(self.classifier, "teach"), "taught": len(getattr(self.classifier, "labels", []))}

    def step(self, frame, now: float) -> None:
        self._last_frame = frame
        self.loop.step(frame, now)          # identity: keeps the session fresh
        self.lid.tick(now)
        self.outbox.flush(now)

        if self._votes is not None:         # collecting looks at the item that just settled
            self._crop = getattr(self.gate, "item_crop", self.gate.crop)(frame)
            self._votes.append(self.classifier.probs(self._crop))
            if len(self._votes) >= self.votes:
                self._decide(now)
            return
        if self.gate.step(frame, now):
            self._crop = getattr(self.gate, "item_crop", self.gate.crop)(frame)
            self._votes = [self.classifier.probs(self._crop)]
            if len(self._votes) >= self.votes:
                self._decide(now)
            return
        state = getattr(self.gate, "state", None)
        if state == "empty":
            self._committed, self._recent, self._pending = None, [], None   # the item is gone: forget its decision
        elif state == "present" and self._committed and now >= self._next_reeval:
            self._crop = getattr(self.gate, "item_crop", self.gate.crop)(frame)
            self._reeval(now)

    def _reeval(self, now: float, fresh: bool = False) -> None:
        """Look at the item in the box again (every `reeval_interval` s while it is held). The numbers on screen follow what the bin sees now, but the LID
        only moves when another bin has clearly led (by `switch_margin`, with at least `min_confidence`) on two looks in a row; this stops the lid flipping
        between two close classes every second. `fresh` (just taught) drops the earlier looks and may switch at once. A confident change to Recycle or
        Organics records a new item (the server decides any reward)."""
        if self._committed is None or self._crop is None:
            return
        self._next_reeval = now + self.reeval_interval
        p = self.classifier.probs(self._crop)
        self._recent = ([p] if fresh else self._recent + [p])[-5:]
        avg = average_probs(self._recent)
        cand = max(avg, key=avg.get)
        old = self._committed["bin"]
        item = self.last_item
        if cand == old or avg[cand] < self.min_confidence or avg[cand] - avg[old] < self.switch_margin:
            self._pending = None                                  # no clear challenger: the decision stands
            self._committed["confidence"] = avg[old]
            if item is not None:
                item.update(bin=old, confidence=round(avg[old], 3))
                self.last_item_at = now
            return
        if not fresh and self._pending != cand:
            self._pending = cand                                  # first time it leads: wait for one more look that agrees
            return
        self._pending = None
        conf = avg[cand]
        self.lid.open(cand, now)
        self._committed = {"bin": cand, "confidence": conf, "reason": "ok"}
        if item is not None:
            item.update(bin=cand, confidence=round(conf, 3), reason="ok")
            self.last_item_at = now
        self.on_event({"event": "item_revised", "from": old, "bin": cand, "confidence": round(conf, 3), "reason": "ok"})
        if cand != "waste":               # waste needs no record of its own; Recycle and Organics do (the server decides the reward)
            session = self.loop.current_session(now)
            iid = self.new_id()
            payload = {"interaction_id": iid, "item_class": cand, "confidence": round(conf, 4)}
            if session:
                payload["session_token"], payload["user_id"] = session.token, session.user_id
            if item is not None:
                item.update(interaction_id=iid, user_id=session.user_id if session else None, payout_status=None, reward_cents=None)
            res = self.outbox.send(payload, now)
            if res is not None:
                if item is not None:
                    item.update(server_outcome(res))
                self.on_event({"event": "interaction_recorded", "interaction_id": iid, "after_retries": 0, **server_outcome(res)})

    def teach(self, label: str, now: float) -> dict | None:
        """The person says what the item in the box right now really is. The bin remembers it and judges it again straight away; if the bin had not
        noticed the item yet, this makes it look at it now (so teaching works even when the automatic trigger did not fire)."""
        if not hasattr(self.classifier, "teach"):
            return None
        if now - self._last_teach < self.teach_gap:           # a key held down repeats many times a second: take the first press only
            return {"label": label, "examples": self.classifier.labels.count(label), "skipped": True}
        self._last_teach = now
        frame = getattr(self, "_last_frame", None)
        crop = getattr(self.gate, "item_crop", self.gate.crop)(frame) if frame is not None else self._crop
        if crop is None:
            return None
        self._crop = crop
        n = self.classifier.teach(label, crop)
        added = getattr(self.classifier, "last_added", True)
        self.on_event({"event": "taught", "label": label, "examples": n, "added": added})
        if self._committed is not None:
            self._reeval(now, fresh=True)
        else:
            self._votes = [self.classifier.probs(crop)]
            self._decide(now)
        return {"label": label, "examples": n, "added": added}

    def forget_last_teaching(self) -> str | None:
        gone = self.classifier.forget_last() if hasattr(self.classifier, "forget_last") else None
        if gone:
            self.on_event({"event": "forgot", "label": gone})
        return gone

    def _save_photo(self, bin_name: str, conf: float, reason: str, iid: str) -> None:
        """Keep the picture the classifier saw, named by its decision: <time>_<bin>_<confidence>[_unsure]_<id>.jpg. Sort these into folders
        (cans / organics / waste) by what the item REALLY was, and they become training photos from this very camera."""
        if not self.save_dir or self._crop is None:
            return
        import time as _t
        from pathlib import Path

        import cv2

        d = Path(self.save_dir).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        name = f"{_t.strftime('%Y%m%d-%H%M%S')}_{bin_name}_{int(conf * 100)}{'_unsure' if reason != 'ok' else ''}_{iid[:6]}.jpg"
        cv2.imwrite(str(d / name), self._crop, [cv2.IMWRITE_JPEG_QUALITY, 92])

    def _decide(self, now: float) -> None:
        votes, self._votes = self._votes, None
        bin_name, conf, reason = decide(votes, self.min_confidence)
        self._committed, self._recent, self._next_reeval = {"bin": bin_name, "confidence": conf, "reason": reason}, list(votes)[-3:], now + self.reeval_interval
        session = self.loop.current_session(now)   # a live, verified person right now?
        self.lid.open(bin_name, now)
        iid = self.new_id()
        self._save_photo(bin_name, conf, reason, iid)
        item = {"event": "item", "interaction_id": iid, "bin": bin_name, "confidence": round(conf, 3), "reason": reason,
                "user_id": session.user_id if session else None, "payout_status": None, "reward_cents": None}
        self.last_item, self.last_item_at = item, now
        self.on_event(item)
        payload = {"interaction_id": iid, "item_class": bin_name, "confidence": round(conf, 4)}
        if session:
            payload["session_token"] = session.token   # meaningful only if the server issued it
            payload["user_id"] = session.user_id       # a bin that identifies people itself names them; the bin key vouches for it
        res = self.outbox.send(payload, now)
        if res is not None:
            item.update(server_outcome(res))      # what the server decided: shown in the preview
            self.on_event({"event": "interaction_recorded", "interaction_id": iid, "after_retries": 0, **server_outcome(res)})
