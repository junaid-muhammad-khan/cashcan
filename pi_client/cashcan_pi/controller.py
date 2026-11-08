"""One camera, two jobs: who is this, and what are they throwing?

  frame -> BinLoop        (face match + head-turn check -> a live session = a logged-in, verified person)
        -> ItemGate       (is an item being presented and held still?)
        -> classifier     (organics / cans / waste, averaged over a few looks)
        -> LidController  (opens THE RIGHT lid, whether or not anyone is identified)
        -> POST /interactions (only the record; a payout is due only if a verified person is in a live session)

Rules
- The lid opens for every confident item, identified or not: nobody is blocked from sorting. An unsure item goes to the waste lid.
- Reward: only when a live, verified session exists at the moment of the throw, the bin is not waste, and the class pays (REWARDS).
  Nobody identified -> the item is still recorded (user_id empty, no payout), so the dashboard counts it.
- Records carry an interaction_id chosen here. A failed send waits in a short-lived outbox (TTL) and is retried with the SAME id,
  so the server stores it once. No face data is ever in the outbox.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable

from .classifier import decide
from .lid import LidController

# Lamports per sorted item (1 SOL = 1e9). PLACEHOLDERS copied from backend/src/rewardTable.ts (cans ~ metal 0.004, organics ~ biological 0.001,
# waste 0): the real figures are an open team decision. Waste never pays.
REWARDS = {"cans": 4_000_000, "organics": 1_000_000, "waste": 0}


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

    def send(self, payload: dict, now: float) -> bool:
        """Try now; on a network or server problem keep it for later. A 4xx means the server refuses it for good, so drop it."""
        import httpx

        try:
            self.api.interaction(payload)
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                self.emit({"event": "interaction_rejected", "interaction_id": payload["interaction_id"], "status": e.response.status_code})
                return False
        except (httpx.HTTPError, ValueError):
            pass
        self.items.append(Pending(payload, now + self.ttl, now + self.backoff, 1))
        self.emit({"event": "interaction_queued", "interaction_id": payload["interaction_id"]})
        return False

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
                self.api.interaction(p.payload)
                self.emit({"event": "interaction_recorded", "interaction_id": p.payload["interaction_id"], "after_retries": p.tries})
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
    rewards: dict = field(default_factory=lambda: dict(REWARDS))
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
        reward = self.rewards.get(bin_name, 0) if (session and reason == "ok") else 0
        iid = self.new_id()
        item = {"event": "item", "interaction_id": iid, "bin": bin_name, "confidence": round(conf, 3), "reason": reason,
                "user_id": session.user_id if session else None, "reward_lamports": reward}
        self.last_item, self.last_item_at = item, now
        self.on_event(item)
        payload = {"interaction_id": iid, "item_class": bin_name, "confidence": round(conf, 4), "reward_lamports": reward}
        if session:
            payload["session_token"] = session.token
        if self.outbox.send(payload, now):
            self.on_event({"event": "interaction_recorded", "interaction_id": iid, "after_retries": 0})
