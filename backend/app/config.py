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
MIN_SHARPNESS = 40.0  # variance of Laplacian on the face crop

# Bin session: after one successful match, items in this window pay out to that user
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "60"))
