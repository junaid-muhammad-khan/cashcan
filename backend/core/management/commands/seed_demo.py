"""
python manage.py seed_demo [--reset]

Creates placeholder item rules, a demo device, fake leaderboard users, and a fully
onboarded dev user ("dev|demo") with events and payouts so the dashboard has data.

The item rules below are PLACEHOLDERS for UI/demo only. verified_at is left null on purpose:
verify against current Recycle BC / Metro Vancouver lists before using them for real.
"""
import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (ConsentRecord, Device, FaceEnrollment, ItemClass, Payout, SortingEvent, User, Wallet)

SOL = 1_000_000_000
# code, label, clean_bin, contaminated_bin, base reward (lamports; 0 = no reward)
ITEMS = [
    ("coffee_cup", "Coffee cup", "garbage", "garbage", 0),
    ("compostable_cutlery", "Compostable cutlery", "garbage", "garbage", 0),
    ("food_soiled_paper", "Food-soiled paper", "organics", "organics", 5_000_000),
    ("greasy_container", "Greasy container", "containers", "garbage", 10_000_000),
    ("chip_bag", "Chip bag", "garbage", "garbage", 0),
    ("plastic_bottle", "Plastic bottle", "containers", "garbage", 10_000_000),
    ("aluminum_can", "Aluminum can", "containers", "garbage", 10_000_000),
    ("cardboard", "Cardboard", "paper", "garbage", 5_000_000),
    ("banana_peel", "Banana peel", "organics", "organics", 5_000_000),
    ("yogurt_cup", "Yogurt cup", "containers", "garbage", 10_000_000),
    ("paper_bag", "Paper bag", "paper", "organics", 5_000_000),
    ("pizza_box", "Pizza box", "paper", "organics", 5_000_000),
]
FAKE_ADDR = "DemoWa11etDemoWa11etDemoWa11etDemoWa11et"[:43]


def make_user(sub, name, board=True):
    u, created = User.objects.get_or_create(
        auth0_sub=sub, defaults={"username": sub, "email": f"{name}@example.com",
                                 "display_name": name, "show_on_leaderboard": board})
    if created:
        u.set_unusable_password()
        u.save()
    return u


def onboard(u, addr):
    consent = ConsentRecord.objects.create(user=u, text_version="v1")
    FaceEnrollment.objects.create(user=u, consent=consent)
    return Wallet.objects.create(user=u, address=addr, verified_at=timezone.now())


def add_events(user, wallet, device, items, n, days=14):
    now = timezone.now()
    for _ in range(n):
        item = random.choice(items)
        contaminated = random.random() < 0.3
        when = now - timedelta(minutes=random.randint(5, days * 24 * 60))
        e = SortingEvent.objects.create(
            id=uuid.uuid4(), device=device, item_class=item, contaminated=contaminated,
            confidence=round(random.uniform(0.82, 0.99), 2),
            destination=item.contaminated_bin if contaminated else item.clean_bin,
            reason_text=("Soiled items can't be recycled." if contaminated else "Clean and accepted."),
            occurred_at=when, user=user, identity_status="matched", attributed_at=when)
        amount = item.base_reward_lamports
        if amount and contaminated:
            amount //= 2  # 50% for contaminated items (see services.reward_for)
        if amount:
            confirmed = random.random() < 0.8
            Payout.objects.create(
                event=e, user=user, wallet=wallet, amount_lamports=amount,
                status="confirmed" if confirmed else "pending",
                tx_signature=uuid.uuid4().hex + uuid.uuid4().hex if confirmed else None,
                confirmed_at=when if confirmed else None)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete events/payouts/seed users first")

    def handle(self, *args, **opts):
        random.seed(7)
        if opts["reset"]:
            Payout.objects.all().delete()
            SortingEvent.objects.all().delete()
            User.objects.filter(auth0_sub__startswith="seed|").delete()
            User.objects.filter(auth0_sub="dev|demo").delete()

        for code, label, cb, xb, reward in ITEMS:
            ItemClass.objects.update_or_create(code=code, defaults={
                "label": label, "clean_bin": cb, "contaminated_bin": xb, "base_reward_lamports": reward,
                "reason_en": "PLACEHOLDER rule: verify before use."})
        items = list(ItemClass.objects.all())
        device, _ = Device.objects.get_or_create(name="demo-bin-1", defaults={"location_label": "Demo table"})

        for i, name in enumerate(["maple", "fern", "cedar", "orca", "otter", "heron"]):
            u = make_user(f"seed|{name}", name)
            if not u.wallets.exists():
                w = onboard(u, f"{name}{'1' * 40}"[:43])
                add_events(u, w, device, items, random.randint(10, 60))

        demo = make_user("dev|demo", "demo")
        if not demo.wallets.exists():
            w = onboard(demo, FAKE_ADDR)
            add_events(demo, w, device, items, 35)
        self.stdout.write(self.style.SUCCESS("Seeded. Log in via /auth/dev-login as the demo user."))
