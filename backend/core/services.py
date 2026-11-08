"""Business logic kept out of views so the device API can reuse it later."""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Payout, SortingEvent, Wallet


def reward_for(item_class, contaminated):
    """Clean pays the base amount; contaminated pays CONTAMINATED_REWARD_FRACTION of it (50% default)."""
    if item_class is None or item_class.base_reward_lamports <= 0:
        return 0
    base = item_class.base_reward_lamports
    return int(base * settings.CONTAMINATED_REWARD_FRACTION) if contaminated else base


@transaction.atomic
def attribute_event(event: SortingEvent, user, face_score=None):
    """
    Called when the async face lookup returns. The bin has already opened by now.
    Marks the event matched and creates a pending Payout if the item earns a reward.
    Idempotent: calling twice never creates two payouts.
    """
    if event.identity_status == "matched":
        return getattr(event, "payout", None)
    event.user = user
    event.identity_status = "matched"
    event.face_score = face_score
    event.attributed_at = timezone.now()
    event.save()

    amount = reward_for(event.item_class, event.contaminated)
    wallet = Wallet.objects.filter(user=user, unlinked_at__isnull=True, is_primary=True).first()
    if amount <= 0 or wallet is None:
        return None
    # TODO MVP+: anti-abuse checks (rate limit, confidence, dedupe) before this point.
    payout, _ = Payout.objects.get_or_create(
        event=event, defaults={"user": user, "wallet": wallet, "amount_lamports": amount})
    return payout


def mark_unknown(event: SortingEvent):
    event.identity_status = "unknown"
    event.save(update_fields=["identity_status"])
