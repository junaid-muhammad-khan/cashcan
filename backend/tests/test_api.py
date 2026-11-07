from .conftest import enroll, png


def match(client, pid, **kw):
    return client.post("/match", files={"frame": ("m.png", png(pid, **kw), "image/png")}).json()


def test_enroll_then_match_opens_session(client):
    assert enroll(client, "alice", 1).status_code == 200
    enroll(client, "bob", 2)
    r = match(client, 1)
    assert r["matched"] and r["user_id"] == "alice" and r["score"] > 0.9
    s = client.get(f"/session/{r['session_token']}").json()
    assert s == {"user_id": "alice", "wallet": "wallet-alice"}


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


def test_enroll_needs_enough_good_frames(client):
    assert enroll(client, "a", 1, n=2).status_code == 400
    assert enroll(client, "a", 1, bad=True).status_code == 422
    assert enroll(client, "a", 1, noface=True).status_code == 422


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
