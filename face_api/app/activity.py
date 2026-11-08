"""GET /me/activity: one user's drops summarised for the website dashboard. Only real stored values, nothing estimated:
paid CAD uses the rate stored on each paid row (the rate at the moment it was sent)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .payouts import public

RANGES = ("today", "week", "30d")
CLASSES = ("cans", "organics", "waste")
DEFAULT_TZ = "America/Vancouver"


def zone(tz: str | None):
    try:
        return ZoneInfo(tz or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        try:
            return ZoneInfo(DEFAULT_TZ)
        except ZoneInfoNotFoundError:
            return timezone.utc


def window(rng: str, tz, now: datetime | None = None) -> tuple[datetime, list[tuple[str, datetime]], str]:
    """(start, [(label, bucket_start)], unit). Buckets are hours for today, local days otherwise."""
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if rng == "today":
        return midnight, [(f"{h}:00", midnight + timedelta(hours=h)) for h in range(24)], "per hour"
    days = 7 if rng == "week" else 30
    first = midnight - timedelta(days=days - 1)
    buckets = [(f"{d.day} {d.strftime('%b')}", d) for d in (first + timedelta(days=i) for i in range(days))]
    return first, buckets, "per day"


def summarise(rows: list[dict], rng: str, tz, now: datetime | None = None, recent: int = 10) -> dict:
    start, buckets, unit = window(rng, tz, now)
    series = [{"label": label, "start": b.isoformat(), "cans": 0, "organics": 0, "waste": 0} for label, b in buckets]
    by_bin = {c: 0 for c in CLASSES}
    t = {"items": 0, "reward_cents": 0, "paid_count": 0, "paid_lamports": 0, "paid_sol": 0.0,
         "paid_cad": 0.0, "held_count": 0, "held_cents": 0, "pending_count": 0, "pending_cents": 0, "failed_count": 0}
    rows = [r for r in rows if r.get("created_at") and r["created_at"] >= start]
    for r in rows:
        cls = r.get("item_class") if r.get("item_class") in CLASSES else "waste"
        by_bin[cls] += 1
        t["items"] += 1
        local = r["created_at"].astimezone(tz)
        idx = local.hour if unit == "per hour" else (local.date() - start.date()).days
        if 0 <= idx < len(series):
            series[idx][cls] += 1
        cents, st = r.get("reward_cents") or 0, r.get("payout_status")
        t["reward_cents"] += cents
        if st == "paid":
            lam = r.get("lamports") or 0
            t["paid_count"] += 1
            t["paid_lamports"] += lam
            if r.get("cad_per_sol"):
                t["paid_cad"] += lam / 1e9 * r["cad_per_sol"]
        elif st == "held":
            t["held_count"] += 1
            t["held_cents"] += cents
        elif st in ("pending", "sending"):
            t["pending_count"] += 1
            t["pending_cents"] += cents
        elif st == "failed":
            t["failed_count"] += 1
            t["pending_cents"] += cents  # still owed: the reconcile job retries it
    t["paid_sol"] = t["paid_lamports"] / 1e9
    t["paid_cad"] = round(t["paid_cad"], 4)
    items = []
    for r in rows[:recent]:
        p = public(r)
        p.pop("user_id", None)
        items.append({**p, "bin_id": r.get("bin_id"), "bin_name": r.get("bin_name"), "created_at": r["created_at"].isoformat()})
    return {"range": rng, "timezone": str(tz), "start": start.isoformat(), "unit": unit, "totals": t, "by_bin": by_bin,
            "series": series, "recent": items}
