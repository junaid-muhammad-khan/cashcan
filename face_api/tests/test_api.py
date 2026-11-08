from .conftest import WALLET, enroll, png


def match(client, pid, **kw):
    return client.post("/match", files={"frame": ("m.png", png(pid, **kw), "image/png")}).json()


def test_enroll_then_match_opens_session(client):
    assert enroll(client, "alice", 1).status_code == 200
    enroll(client, "bob", 2)
    r = match(client, 1)
    assert r["matched"] and r["user_id"] == "alice" and r["score"] > 0.9
    s = client.get(f"/session/{r['session_token']}").json()
    assert s == {"user_id": "alice", "wallet": WALLET}


def test_unknown_face_rejected(client):
    enroll(client, "alice", 1)
    r = match(client, 99)
    assert not r["matched"] and r["reason"] == "below_threshold"
    assert "session_token" not in r


def test_no_users_enrolled(client):
    assert match(client, 1)["reason"] == "no_enrolled_users"


def test_consent_required(client):
    r = enroll(client, "alice", 1, consent=False)
    assert r.status_code == 400
    assert match(client, 1)["reason"] == "no_enrolled_users"  # nothing stored


def test_enroll_accepts_one_to_three_photos_and_refuses_none_usable_or_too_many(client):
    assert enroll(client, "one", 1, n=1).json()["frames_used"] == 1            # a single photo is enough
    assert enroll(client, "two", 2, n=2).status_code == 200
    assert enroll(client, "three", 3, n=3).json()["frames_used"] == 3
    assert enroll(client, "many", 4, n=4).status_code == 400                   # more than the 3 people will take
    assert enroll(client, "bad", 5, n=3, bad=True).status_code == 422          # nothing usable
    assert enroll(client, "none", 6, n=1, noface=True).status_code == 422
    files = [("frames", ("a.png", png(7), "image/png")), ("frames", ("b.png", png(7, bad=True), "image/png")),
             ("frames", ("c.png", png(7, noface=True), "image/png"))]
    mixed = client.post("/enroll", data={"user_id": "mixed", "wallet": WALLET, "consent": "true"}, files=files).json()
    assert mixed["frames_used"] == 1 and len(mixed["problems"]) == 2           # one good photo among bad ones still enrolls


def test_duplicate_and_bad_user_id(client):
    assert enroll(client, "alice", 1).status_code == 200
    assert enroll(client, "alice", 1).status_code == 409
    assert enroll(client, "../etc", 1).status_code == 400


def test_bad_frame_at_bin(client):
    enroll(client, "alice", 1)
    assert match(client, 1, noface=True)["reason"] == "bad_frame"
    assert match(client, 1, bad=True)["reason"] == "bad_frame"


def test_session_expires(client, clock):
    enroll(client, "alice", 1)
    token = match(client, 1)["session_token"]
    clock["now"] = 61
    assert client.get(f"/session/{token}").status_code == 404


def test_delete_removes_face_and_sessions(client):
    enroll(client, "alice", 1)
    token = match(client, 1)["session_token"]
    assert client.delete("/users/alice").status_code == 200
    assert client.delete("/users/alice").status_code == 404
    assert client.get(f"/session/{token}").status_code == 404
    assert match(client, 1)["reason"] == "no_enrolled_users"


def test_wallet_validated_server_side(client):
    files = [("frames", (f"f{i}.png", png(1), "image/png")) for i in range(3)]
    r = client.post("/enroll", data={"user_id": "a", "wallet": "not-a-wallet", "consent": "true"}, files=files)
    assert r.status_code == 400 and "wallet" in r.json()["detail"].lower()


def test_enrollment_page_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and "consent" in r.text.lower()
