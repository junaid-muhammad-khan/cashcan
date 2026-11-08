import json
import re
from functools import wraps

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import ConsentRecord, FaceEnrollment, Payout, SortingEvent, User, Wallet

# Rough shape check for a base58 Solana address. Ownership verification is a TODO.
SOLANA_ADDR = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def api_login_required(fn):
    @wraps(fn)
    def wrapper(request, *a, **kw):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "unauthenticated"}, status=401)
        return fn(request, *a, **kw)
    return wrapper


def body(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return {}


def onboarding_state(user):
    consent = user.consents.filter(purpose="face_enrollment", revoked_at__isnull=True).exists()
    face = user.face_enrollments.filter(status="active").exists()
    wallet = user.wallets.filter(unlinked_at__isnull=True).exists()
    return {"consent": consent, "face": face, "wallet": wallet, "complete": consent and face and wallet}


def user_json(user):
    wallet = user.wallets.filter(unlinked_at__isnull=True, is_primary=True).first()
    return {"id": str(user.id), "email": user.email, "display_name": user.label(),
            "show_on_leaderboard": user.show_on_leaderboard,
            "wallet": wallet.address if wallet else None,
            "wallet_verified": bool(wallet and wallet.verified_at)}


@ensure_csrf_cookie
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False,
                             "auth0_enabled": settings.AUTH0_ENABLED,
                             "dev_login": settings.DEBUG and not settings.AUTH0_ENABLED})
    return JsonResponse({"authenticated": True, "user": user_json(request.user),
                         "onboarding": onboarding_state(request.user)})


@require_http_methods(["POST"])
@api_login_required
def profile(request):
    data = body(request)
    u = request.user
    if "display_name" in data:
        u.display_name = str(data["display_name"]).strip()[:40]
    if "show_on_leaderboard" in data:
        u.show_on_leaderboard = bool(data["show_on_leaderboard"])
    u.save()
    return JsonResponse({"user": user_json(u)})


@require_http_methods(["POST"])
@api_login_required
def onboarding_consent(request):
    data = body(request)
    if not data.get("agreed"):
        return JsonResponse({"error": "Consent is required to enroll your face."}, status=400)
    if "display_name" in data:
        request.user.display_name = str(data["display_name"]).strip()[:40]
        request.user.save(update_fields=["display_name"])
    if not request.user.consents.filter(purpose="face_enrollment", revoked_at__isnull=True).exists():
        ConsentRecord.objects.create(user=request.user, text_version=settings.CONSENT_TEXT_VERSION)
    return JsonResponse({"onboarding": onboarding_state(request.user)})


@require_http_methods(["POST"])
@api_login_required
def onboarding_face(request):
    """STUB. Real flow: browser captures frames, an embedding is computed and written to the
    Databricks vector table, and only the pointer is stored here. Never store raw photos."""
    consent = request.user.consents.filter(purpose="face_enrollment", revoked_at__isnull=True).first()
    if consent is None:
        return JsonResponse({"error": "Consent required first."}, status=400)
    if not request.user.face_enrollments.filter(status="active").exists():
        FaceEnrollment.objects.create(user=request.user, consent=consent)
    return JsonResponse({"onboarding": onboarding_state(request.user), "stub": True})


@require_http_methods(["POST"])
@api_login_required
def onboarding_wallet(request):
    address = str(body(request).get("address", "")).strip()
    if not SOLANA_ADDR.match(address):
        return JsonResponse({"error": "That doesn't look like a Solana address. "
                                      "Paste your public address only, never a seed phrase or private key."},
                            status=400)
    if Wallet.objects.filter(address=address).exclude(user=request.user).exists():
        return JsonResponse({"error": "That wallet is already linked to another account."}, status=400)
    request.user.wallets.filter(unlinked_at__isnull=True).update(unlinked_at=timezone.now(), is_primary=False)
    Wallet.objects.create(user=request.user, address=address)
    return JsonResponse({"onboarding": onboarding_state(request.user), "user": user_json(request.user)})


@api_login_required
def dashboard(request):
    u = request.user
    events = SortingEvent.objects.filter(user=u)
    confirmed = Payout.objects.filter(user=u, status="confirmed").aggregate(s=Sum("amount_lamports"))["s"] or 0
    pending = (Payout.objects.filter(user=u, status__in=["pending", "submitted"])
               .aggregate(s=Sum("amount_lamports"))["s"] or 0)
    agg = events.aggregate(total=Count("id"), n_contaminated=Count("id", filter=Q(contaminated=True)),
                           n_clean=Count("id", filter=Q(contaminated=False)))
    total = agg["total"]
    breakdown = list(events.values("item_class__label").annotate(n=Count("id")).order_by("-n")[:8])

    recent = [{"id": str(e.id), "when": e.occurred_at.isoformat(),
               "item": e.item_class.label if e.item_class else "Unknown",
               "contaminated": e.contaminated, "bin": e.destination,
               "reason": e.reason_text,
               "payout_status": getattr(getattr(e, "payout", None), "status", None),
               "payout_lamports": getattr(getattr(e, "payout", None), "amount_lamports", 0)}
              for e in events.select_related("item_class", "payout").order_by("-occurred_at")[:10]]

    payouts = [{"id": str(p.id), "when": p.created_at.isoformat(), "lamports": p.amount_lamports,
                "status": p.status, "tx": p.tx_signature, "network": p.network}
               for p in Payout.objects.filter(user=u).order_by("-created_at")[:10]]

    # Leaderboard metric is TBD. Ranking by clean deposits (not SOL) so early/heavy users don't dominate on payout alone.
    # Events and payouts are aggregated separately: joining both multi-valued relations in one
    # annotate() would multiply the counts and sums.
    board = list(User.objects.filter(show_on_leaderboard=True)
                 .annotate(items=Count("events"),
                           clean=Count("events", filter=Q(events__contaminated=False)))
                 .order_by("-clean", "-items")[:10])
    earned = dict(Payout.objects.filter(user__in=[b.id for b in board], status="confirmed")
                  .values_list("user").annotate(s=Sum("amount_lamports")))
    leaderboard = [{"rank": i + 1, "name": b.label(), "clean": b.clean, "items": b.items,
                    "lamports": earned.get(b.id, 0), "is_me": b.id == u.id} for i, b in enumerate(board)]

    return JsonResponse({
        "stats": {"items_total": total, "items_clean": agg["n_clean"], "items_contaminated": agg["n_contaminated"],
                  "clean_rate": round(agg["n_clean"] / total, 3) if total else None,
                  "lamports_confirmed": confirmed, "lamports_pending": pending},
        "breakdown": [{"item": r["item_class__label"] or "Unknown", "count": r["n"]} for r in breakdown],
        "recent": recent, "payouts": payouts, "leaderboard": leaderboard,
        "network": "devnet",
    })
