"""The one reward table. Every amount CashCan pays is decided here; the bin's own figure is never trusted.

A paying item earns half the BC beverage-container deposit (10 cents) in Canadian cents. The cents are converted to SOL at the
live SOL/CAD rate at the moment the payout is sent (website/app/api/payout), so the table itself never holds a SOL amount.
The website's /prices page reads this table through GET /rewards (its own copy in website/lib/prices.ts is only the fallback,
and tests/test_rewards.py fails if the two disagree).
"""
from __future__ import annotations

BC_DEPOSIT_CENTS = 10      # BC Return-It deposit, the same on every container type the classifier calls "cans"
CASH_BACK_SHARE = 0.5      # CashCan pays half the deposit
CURRENCY = "CAD"

# Per classifier class (ml/class_map.yaml: cans / organics / waste). Organics and waste do not pay for now.
REWARD_CENTS: dict[str, int] = {
    "cans": round(BC_DEPOSIT_CENTS * CASH_BACK_SHARE),
    "organics": 0,
    "waste": 0,
}


def reward_cents(item_class: str) -> int:
    """Cents a correctly sorted item of this class earns. Unknown classes earn nothing."""
    return REWARD_CENTS.get((item_class or "").strip().lower(), 0)


def table() -> dict:
    """Read-only view served at GET /rewards."""
    return {"currency": CURRENCY, "deposit_cents": BC_DEPOSIT_CENTS, "cash_back_share": CASH_BACK_SHARE,
            "classes": dict(REWARD_CENTS),
            "note": "Paid in SOL (devnet) at the live SOL/CAD rate when the payout is sent."}
