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

from .classifier import decide
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

    def __post_init__(self):
        self._votes: list[dict] | None = None
        self._first_crop = None
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
                "identity": self.loop.info() if hasattr(self.loop, "info") else {}}

    def step(self, frame, now: float) -> None:
        self.loop.step(frame, now)          # identity: keeps the session fresh
        self.lid.tick(now)
        self.outbox.flush(now)

        if self._votes is not None:         # collecting looks at the item that just settled
            self._votes.append(self.classifier.probs(self.gate.crop(frame)))
            if len(self._votes) >= self.votes:
                self._decide(now)
            return
        if self.gate.step(frame, now):
            self._votes = [self.classifier.probs(self.gate.crop(frame))]
            if len(self._votes) >= self.votes:
                self._decide(now)

    def _decide(self, now: float) -> None:
        votes, self._votes = self._votes, None
        bin_name, conf, reason = decide(votes, self.min_confidence)
        session = self.loop.current_session(now)   # a live, verified person right now?
        self.lid.open(bin_name, now)
        iid = self.new_id()
        item = {"event": "item", "interaction_id": iid, "bin": bin_name, "confidence": round(conf, 3), "reason": reason,
                "user_id": session.user_id if session else None, "payout_status": None, "reward_cents": None}
        self.last_item, self.last_item_at = item, now
        self.on_event(item)
        payload = {"interaction_id": iid, "item_class": bin_name, "confidence": round(conf, 4)}
        if session:
            payload["session_token"] = session.token
        res = self.outbox.send(payload, now)
        if res is not None:
            item.update(server_outcome(res))      # what the server decided: shown in the preview
            self.on_event({"event": "interaction_recorded", "interaction_id": iid, "after_retries": 0, **server_outcome(res)})
