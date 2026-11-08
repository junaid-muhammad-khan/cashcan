"""
MVP data model (SQLite). A trimmed version of cashcan-schema.md:

- BinType / SortingRule / RewardRule are folded into ItemClass for now.
- EventDetection, FaceMatchAttempt, WalletChallenge, DeletionRequest, UserStatsDaily
  are deferred. Add them when the feature needs them.
- Identity is resolved ASYNCHRONOUSLY: the bin opens immediately from the local
  classifier, and the event is attributed to a user later (identity_status).
"""
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


BIN_CHOICES = [("garbage", "Garbage"), ("organics", "Organics"),
               ("containers", "Containers"), ("paper", "Paper")]


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auth0_sub = models.CharField(max_length=128, unique=True, null=True, blank=True)
    display_name = models.CharField(max_length=40, blank=True)
    show_on_leaderboard = models.BooleanField(default=False)  # opt-in
    analytics_key = models.UUIDField(default=uuid.uuid4, unique=True)  # pseudonym for Databricks
    created_at = models.DateTimeField(auto_now_add=True)

    def label(self):
        return self.display_name or (self.email.split("@")[0] if self.email else "user")


class ConsentRecord(UUIDModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    purpose = models.CharField(max_length=32, default="face_enrollment")
    text_version = models.CharField(max_length=16)
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class Wallet(UUIDModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wallets")
    address = models.CharField(max_length=44, unique=True)  # base58 Solana pubkey
    network = models.CharField(max_length=16, default="devnet")
    verified_at = models.DateTimeField(null=True, blank=True)  # TODO: signed-message verification
    is_primary = models.BooleanField(default=True)
    unlinked_at = models.DateTimeField(null=True, blank=True)


class FaceEnrollment(UUIDModel):
    """Pointer + metadata only. The embedding itself goes to Databricks (TODO)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="face_enrollments")
    # RESTRICT (not PROTECT): consent can't be deleted on its own, but account deletion
    # (which removes both together) still works. Needed for delete-on-request.
    consent = models.ForeignKey(ConsentRecord, on_delete=models.RESTRICT)
    embedding_id = models.UUIDField(default=uuid.uuid4, unique=True)
    model_name = models.CharField(max_length=64, default="stub")
    model_version = models.CharField(max_length=32, default="0")
    status = models.CharField(max_length=16, default="active")  # active | revoked | deleted
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)


class Device(UUIDModel):
    name = models.CharField(max_length=64)
    api_key_hash = models.CharField(max_length=128, blank=True)
    location_label = models.CharField(max_length=128, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)


class ItemClass(models.Model):
    """Classifier label + routing + reward, in one row for the MVP."""
    code = models.CharField(max_length=48, primary_key=True)  # classifier label
    label = models.CharField(max_length=64)
    clean_bin = models.CharField(max_length=16, choices=BIN_CHOICES)
    contaminated_bin = models.CharField(max_length=16, choices=BIN_CHOICES)
    reason_en = models.TextField(blank=True)
    source_url = models.URLField(blank=True)
    verified_at = models.DateField(null=True, blank=True)  # null = NOT verified against local rules
    base_reward_lamports = models.BigIntegerField(default=0)  # 0 = no reward
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class SortingEvent(models.Model):
    id = models.UUIDField(primary_key=True)  # generated ON THE DEVICE (idempotency key)
    device = models.ForeignKey(Device, on_delete=models.PROTECT)
    item_class = models.ForeignKey(ItemClass, null=True, on_delete=models.PROTECT)
    contaminated = models.BooleanField(null=True)
    confidence = models.FloatField(null=True)
    destination = models.CharField(max_length=16, choices=BIN_CHOICES, blank=True)
    reason_text = models.TextField(blank=True)
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    # Async identity: the bin does not wait for this.
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    identity_status = models.CharField(max_length=12, default="pending",
                                       choices=[("pending", "pending"), ("matched", "matched"),
                                                ("unknown", "unknown")])
    face_score = models.FloatField(null=True, blank=True)
    attributed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-occurred_at"])]


class Payout(UUIDModel):
    event = models.OneToOneField(SortingEvent, on_delete=models.PROTECT)  # one payout per event
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="payouts")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT)
    amount_lamports = models.BigIntegerField()
    network = models.CharField(max_length=16, default="devnet")
    status = models.CharField(max_length=16, default="pending",
                              choices=[("pending", "pending"), ("submitted", "submitted"),
                                       ("confirmed", "confirmed"), ("failed", "failed")])
    tx_signature = models.CharField(max_length=100, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
