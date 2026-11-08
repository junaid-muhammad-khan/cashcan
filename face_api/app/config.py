"""Tunable settings for face enrollment and matching.

Defaults suit InsightFace ArcFace (buffalo_s) embeddings. Tune MATCH_THRESHOLD on
the team's own faces and report the real false-accept / false-reject rates.
"""
import os

DB_PATH = os.environ.get("CASHCAN_DB", "cashcan_faces.db")

# Matching
MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.45"))  # cosine similarity
AMBIGUITY_MARGIN = float(os.environ.get("AMBIGUITY_MARGIN", "0.05"))  # best user must beat runner-up by this

# Enrollment quality gates
MIN_ENROLL_FRAMES = 3
MAX_ENROLL_FRAMES = 8
MIN_DET_SCORE = 0.60
MIN_FACE_PX = 80  # shortest side of the face box
MIN_SHARPNESS = 30.0  # Laplacian variance of the face crop resized to 112x112 (size-independent); rejects ~1% of LFW

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
