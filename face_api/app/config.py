"""Tunable settings for face enrollment and matching.

Defaults suit InsightFace ArcFace (buffalo_s) embeddings. Tune MATCH_THRESHOLD on
the team's own faces and report the real false-accept / false-reject rates.
"""
import os

DB_PATH = os.environ.get("CASHCAN_DB", "cashcan_faces.db")  # local SQLite, used only when the Databricks store is off

# Where face templates live. "databricks" (default whenever DATABRICKS_HOST/TOKEN/WAREHOUSE_ID are set) or "sqlite" (local file).
STORE = os.environ.get("CASHCAN_STORE", "").lower() or (
    "databricks" if all(os.environ.get(k) for k in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID")) else "sqlite")

# Matching
MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.45"))  # cosine similarity
AMBIGUITY_MARGIN = float(os.environ.get("AMBIGUITY_MARGIN", "0.05"))  # best user must beat runner-up by this

# Quality gates come in two tiers.
# ENROLLMENT is strict: a bad frame would be saved as a bad template.
MIN_ENROLL_FRAMES = 1   # people will enroll with 1 photo, or 3 at most (measured: 1 photo recognises 93.6% on LFW at 45%, 2 photos 97.8%, 3 photos 99.0%)
MAX_ENROLL_FRAMES = 3
MIN_DET_SCORE = 0.60
MIN_FACE_PX = 80  # shortest side of the face box
MIN_SHARPNESS = 60.0  # contrast-normalised Laplacian variance of the face at 112x112 (lighting- and size-independent); rejects ~3% of LFW
# IDENTIFICATION is lenient: a weak frame can only fail to match, and the match threshold (not these gates) is what keeps strangers out.
# Measured: letting in the photos these gates used to reject gave 93% recognised and 0 wrong names on LFW (see ROBUSTNESS.md).
ID_MIN_DET_SCORE = 0.45
ID_MIN_FACE_PX = 48  # measured width of the detected face; with sensor noise + JPEG the model alone recognises 88% at 47 px, 73% at 38 px, 42% at 28 px (ROBUSTNESS.md)
ID_MIN_SHARPNESS = 25.0

# Bin session: after one successful match, items in this window pay out to that user
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "60"))

# Liveness (random head-turn challenge, issued only after a face is recognised)
REQUIRE_LIVENESS = os.environ.get("CASHCAN_LIVENESS", "on").lower() not in ("off", "0", "false")
LIVENESS_TTL_SECONDS = float(os.environ.get("LIVENESS_TTL_SECONDS", "10"))  # time allowed to complete a challenge
LIVENESS_CENTER_MAX = 0.12   # |turn ratio| at or below this counts as facing the camera
LIVENESS_TURN_MIN = 0.25     # ratio needed in the asked direction (~30 degrees of head turn)
LIVENESS_ID_THRESHOLD = float(os.environ.get("LIVENESS_ID_THRESHOLD", "0.35"))  # looser than MATCH_THRESHOLD: a turned head scores lower
LIVENESS_MAX_STRIKES = 3     # frames that fail the identity check before the challenge fails
LIVENESS_VALID_SECONDS = float(os.environ.get("LIVENESS_VALID_SECONDS", "120"))  # a live session may be refreshed by face re-check this long
LIVENESS_MAX_OPEN = 200      # cap on simultaneously open challenges

# Auth0 (website login). When AUTH0_DOMAIN is set, account endpoints require a valid Auth0 access token.
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")        # e.g. cashcoin.ca.auth0.com
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")    # the API identifier configured in Auth0
# Bins authenticate with a per-bin key, sent as X-Bin-Key. Comma-separated "bin_id:key" pairs.
BIN_API_KEYS = os.environ.get("BIN_API_KEYS", "")

# Rewards and payouts (see app/rewards.py and app/payouts.py)
MIN_CONFIDENCE = float(os.environ.get("MIN_CONFIDENCE", "0.75"))                    # classifier confidence needed for a reward
PAYOUT_COOLDOWN_SECONDS = int(os.environ.get("PAYOUT_COOLDOWN_SECONDS", "30"))      # one paying drop per user per window
PAYOUT_URL = os.environ.get("PAYOUT_URL", "")            # the website's /api/payout (Node route that signs the devnet transfer)
PAYOUT_SECRET = os.environ.get("PAYOUT_SECRET", "")      # shared secret, sent as "Authorization: Bearer ..."
PAYOUT_TIMEOUT_SECONDS = float(os.environ.get("PAYOUT_TIMEOUT_SECONDS", "8"))
PAYOUT_MAX_ATTEMPTS = int(os.environ.get("PAYOUT_MAX_ATTEMPTS", "5"))               # failed payouts are retried up to this many sends
PAYOUT_RETRY_BASE_SECONDS = int(os.environ.get("PAYOUT_RETRY_BASE_SECONDS", "30"))  # backoff: 30 s, 60 s, 120 s, ...
PAYOUT_STUCK_SECONDS = int(os.environ.get("PAYOUT_STUCK_SECONDS", "180"))           # a "sending" row older than this is resolved by memo lookup
CRON_SECRET = os.environ.get("CRON_SECRET", "")          # Vercel cron sends "Authorization: Bearer $CRON_SECRET"

# Where the API is mounted behind the website (vercel.json rewrites /face-api/* to it). Requests with this prefix are accepted too.
MOUNT_PREFIX = os.environ.get("MOUNT_PREFIX", "/face-api")

# Enrollment poses: each of the (up to) 3 photos must really show the requested head direction.
# turn ratio, positive = the person's own left (see liveness.py). A "little" turn, gentler than the liveness challenge.
ENROLL_FRONT_MAX = 0.10     # |turn| at or below this is "straight"
ENROLL_TURN_MIN = 0.16      # at least this much for "left"/"right"
ENROLL_TURN_MAX = 0.55      # beyond this the face is in profile and no longer recognisable

# Replacing an old account with the same face (destructive): every photo must match that one account, and on average at least this well
# (stricter than MATCH_THRESHOLD; strangers scored 21% at most in the tests, real people 58-83%).
REPLACE_MIN_SIMILARITY = float(os.environ.get("REPLACE_MIN_SIMILARITY", "0.50"))
