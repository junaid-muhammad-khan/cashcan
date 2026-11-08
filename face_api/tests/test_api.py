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


def test_accepts_the_mount_prefix_too(client):
    assert client.get("/health").json() == {"ok": True}
    assert client.get("/face-api/health").json() == {"ok": True}
    r = client.post("/face-api/enroll", data={"user_id": "x", "wallet": "w"})  # reaches the real route (fails validation, not 404)
    assert r.status_code in (400, 422)


def test_pose_endpoint_reads_the_head_direction(client):
    from tests.conftest import png
    for turn, want in ((0.0, "front"), (0.3, "left"), (-0.3, "right"), (0.13, "between"), (0.6, "profile")):
        r = client.post("/pose", files={"frame": ("f.png", png(1, turn=turn), "image/png")}).json()
        assert r["found"] and r["pose"] == want, (turn, r)
    assert client.post("/pose", files={"frame": ("f.png", png(1, noface=True), "image/png")}).json()["found"] is False


def test_enroll_checks_each_photo_shows_its_pose(client):
    from tests.conftest import png, WALLET
    f = lambda t, who=5: ("frames", ("f.png", png(who, turn=t), "image/png"))
    ok = client.post("/enroll", data={"user_id": "p1", "wallet": WALLET, "consent": "true", "poses": "front,left,right"},
                     files=[f(0.0), f(0.3), f(-0.3)])
    assert ok.status_code == 200 and ok.json()["frames_used"] == 3
    # the person turned left for the "front" photo: that photo is refused, the other two still count
    bad = client.post("/enroll", data={"user_id": "p2", "wallet": WALLET, "consent": "true", "poses": "front,left,right"},
                      files=[f(0.3, 6), f(0.3, 6), f(-0.3, 6)])
    assert bad.status_code == 200 and bad.json()["frames_used"] == 2 and "Expected" in bad.json()["problems"][0]
    assert client.post("/enroll", data={"user_id": "p3", "wallet": WALLET, "consent": "true", "poses": "front,up"},
                       files=[f(0.0, 7), f(0.3, 7)]).status_code == 400


def test_a_face_cannot_be_enrolled_under_a_second_account(client):
    from tests.conftest import png, WALLET
    f = [("frames", ("f.png", png(11), "image/png"))]
    assert client.post("/enroll", data={"user_id": "first", "wallet": WALLET, "consent": "true"}, files=f).status_code == 200
    r = client.post("/enroll", data={"user_id": "second", "wallet": WALLET, "consent": "true"}, files=f)
    assert r.status_code == 409 and "already registered" in r.text
    other = [("frames", ("f.png", png(12), "image/png"))]  # a different person is fine
    assert client.post("/enroll", data={"user_id": "third", "wallet": WALLET, "consent": "true"}, files=other).status_code == 200


def test_match_logs_similarity_and_threshold_but_the_response_keeps_its_shape(client, caplog):
    import logging
    from tests.conftest import png, WALLET
    client.post("/enroll", data={"user_id": "logme", "wallet": WALLET, "consent": "true"}, files=[("frames", ("f.png", png(21), "image/png"))])
    with caplog.at_level(logging.INFO, logger="cashcan.match"):
        r = client.post("/match", files={"frame": ("f.png", png(21), "image/png")}).json()
    assert r["matched"] is True
    line = next(m for m in caplog.messages if m.startswith("match "))
    assert "matched=True" in line and "user=logme" in line and "similarity=" in line and "threshold=0.45" in line


def test_a_face_can_replace_its_old_account_when_the_person_chooses_to(client):
    from tests.conftest import png, WALLET
    f = lambda who: [("frames", ("f.png", png(who), "image/png"))]
    d = lambda uid, **kw: {"user_id": uid, "wallet": WALLET, "consent": "true", **kw}
    assert client.post("/enroll", data=d("old"), files=f(31)).status_code == 200
    r = client.post("/enroll", data=d("new"), files=f(31))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "face_already_registered"        # the page uses this to offer the button
    ok = client.post("/enroll", data=d("new", replace="true"), files=f(31))
    assert ok.status_code == 200 and ok.json()["replaced_old_account"] is True
    assert client.post("/match", files={"frame": ("f.png", png(31), "image/png")}).json()["user_id"] == "new"   # one account holds the face now
    assert client.delete("/users/old").status_code == 404                                              # the old one is gone


def test_replace_is_refused_when_the_photos_match_two_accounts_or_nobody(client):
    from tests.conftest import png, WALLET
    d = lambda uid, **kw: {"user_id": uid, "wallet": WALLET, "consent": "true", **kw}
    client.post("/enroll", data=d("a1"), files=[("frames", ("f.png", png(41), "image/png"))])
    client.post("/enroll", data=d("a2"), files=[("frames", ("f.png", png(42), "image/png"))])
    mixed = [("frames", ("f.png", png(41), "image/png")), ("frames", ("f.png", png(42), "image/png"))]
    r = client.post("/enroll", data=d("n1", replace="true"), files=mixed)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "face_replace_refused"
    half = [("frames", ("f.png", png(41), "image/png")), ("frames", ("f.png", png(43), "image/png"))]     # only one of two photos matches a1
    assert client.post("/enroll", data=d("n2", replace="true"), files=half).status_code == 409
    assert client.post("/enroll", data=d("n3", replace="true"), files=[("frames", ("f.png", png(44), "image/png"))]).status_code == 200  # nothing to replace: normal enroll
    assert client.post("/match", files={"frame": ("f.png", png(41), "image/png")}).json()["user_id"] == "a1"       # a1 untouched by the refusals


def test_live_matching_needs_no_head_turn_by_default():
    from app import config
    assert config.REQUIRE_LIVENESS is False   # enrollment collects the head turns; the bin verifies on the best similarity alone (CASHCAN_LIVENESS=on to ask again)
