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
