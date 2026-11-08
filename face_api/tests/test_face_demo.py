from argparse import Namespace

import numpy as np

from app import config
from tools import face_demo as fd

from .conftest import FakeEngine, png


def write(tmp_path, folder, name, pid, **kw):
    d = tmp_path / folder
    d.mkdir(exist_ok=True)
    (d / name).write_bytes(png(pid, **kw))
    return d


def args(tmp_path, **kw):
    base = dict(db=str(tmp_path / "d.db"), name="me", images=None, camera="0", count=5, interval=1.0,
                no_window=True, threshold=config.MATCH_THRESHOLD, margin=config.AMBIGUITY_MARGIN,
                mine=None, others=None, add=False, guided=False, lead=4.0, max_templates=40)
    return Namespace(**{**base, **kw})


def enroll_me(tmp_path, store, pid=1, n=3):
    for i in range(n):
        write(tmp_path, "enroll", f"e{i}.png", pid)
    return fd.cmd_enroll(args(tmp_path, images=[str(tmp_path / "enroll")]), FakeEngine(), store)


def test_enroll_from_images_saves_templates_only(tmp_path):
    from app.store import FaceStore

    store = FaceStore(str(tmp_path / "d.db"))
    assert enroll_me(tmp_path, store) == 0
    owners, gal = store.all_embeddings()
    assert owners == ["me"] * 3 and gal.shape == (3, 512)
    assert enroll_me(tmp_path, store) == 1  # already saved: refuses, nothing duplicated
    assert len(store.all_embeddings()[0]) == 3


def test_enroll_needs_enough_usable_images(tmp_path):
    from app.store import FaceStore

    store = FaceStore(str(tmp_path / "d.db"))
    write(tmp_path, "enroll", "a.png", 1)
    write(tmp_path, "enroll", "b.png", 1, bad=True)   # fails the quality gate
    write(tmp_path, "enroll", "c.png", 1, noface=True)
    assert fd.cmd_enroll(args(tmp_path, images=[str(tmp_path / "enroll")]), FakeEngine(), store) == 1
    assert not store.user_exists("me")


def test_identify_names_the_enrolled_person_and_rejects_strangers(tmp_path):
    import cv2

    from app.store import FaceStore

    store = FaceStore(str(tmp_path / "d.db"))
    enroll_me(tmp_path, store, pid=1)
    img = lambda pid: cv2.imdecode(np.frombuffer(png(pid), np.uint8), 1)
    mine = fd.identify_frame(FakeEngine(), store, img(1), 0.45, 0.05)[0]
    other = fd.identify_frame(FakeEngine(), store, img(2), 0.45, 0.05)[0]
    assert mine.matched and mine.name == "me" and mine.score > 0.9
    assert not other.matched and other.reason == "below_threshold"


def test_evaluate_passes_when_clean_and_fails_on_a_wrong_accept(tmp_path, capsys):
    from app.store import FaceStore

    store = FaceStore(str(tmp_path / "d.db"))
    enroll_me(tmp_path, store, pid=1)
    mine = write(tmp_path, "mine", "m.png", 1)
    others = write(tmp_path, "others", "o.png", 2)
    assert fd.cmd_evaluate(args(tmp_path, mine=[str(mine)], others=[str(others)]), FakeEngine(), store) == 0
    assert "Clean gap" in capsys.readouterr().out
    write(tmp_path, "others", "lookalike.png", 1)  # a stranger who scores as me
    assert fd.cmd_evaluate(args(tmp_path, mine=[str(mine)], others=[str(others)]), FakeEngine(), store) == 2
    assert "ERR" in capsys.readouterr().out


def test_list_images_accepts_files_and_folders(tmp_path):
    d = write(tmp_path, "x", "a.png", 1)
    write(tmp_path, "x", "b.JPG", 1)
    (d / "notes.txt").write_text("not an image")
    assert [p.name for p in fd.list_images([str(d)])] == ["a.png", "b.JPG"]
    assert [p.name for p in fd.list_images([str(d / "a.png")])] == ["a.png"]


def _report(sharp=500.0, box=(0, 0, 200, 200), det=0.99, enrolled=True):
    from app.face_engine import FaceResult
    emb = np.zeros(512, np.float32)
    emb[0] = 1.0
    owners, gal = (["me"], emb[None, :].copy()) if enrolled else ([], np.zeros((0, 512), np.float32))
    return fd.report_for(FaceResult(emb, det, box, sharp, 0.05), owners, gal, 0.45, 0.05)


def test_percent_is_a_similarity_not_a_probability_and_never_negative():
    assert fd.pct(0.974) == "97%" and fd.pct(0.0) == "0%" and fd.pct(-0.3) == "0%"


def test_skipped_frame_says_which_gate_failed_and_by_how_much():
    blurry = _report(sharp=12.0)
    assert not blurry.usable and "blurry" in blurry.label and f"12 < {config.ID_MIN_SHARPNESS:.0f}" in blurry.label
    small = _report(box=(0, 0, 30, 40))
    assert "too small" in small.label and f"30px < {config.ID_MIN_FACE_PX}px" in small.label
    unclear = _report(det=0.3)
    assert "unclear" in unclear.label and f"0.30 < {config.ID_MIN_DET_SCORE:.2f}" in unclear.label
    assert fd.short_gate(blurry) == "blurry" and "SKIPPED, blurry" in fd.describe(blurry)


def test_usable_frame_shows_percentage_and_the_threshold_needed():
    r = _report()
    assert r.usable and r.matched and r.label == "me 100%"
    assert "need 45% to match" in fd.describe(r) and "sharpness 500" in fd.describe(r)


def test_gate_overrides_let_a_soft_webcam_through(monkeypatch):
    from argparse import Namespace
    monkeypatch.setattr(config, "MIN_SHARPNESS", config.MIN_SHARPNESS)  # restore after the test
    assert not _report(sharp=20.0).usable
    fd.apply_gate_overrides(Namespace(min_sharpness=15.0, min_face=None, min_det=None))
    assert config.MIN_SHARPNESS == 15.0 and _report(sharp=20.0).usable


def test_enroll_add_extends_the_same_person_and_refuses_a_second_name_trap(tmp_path, capsys):
    from app.store import FaceStore

    store = FaceStore(str(tmp_path / "d.db"))
    enroll_me(tmp_path, store, pid=1)                       # 3 templates
    for i in range(3):
        write(tmp_path, "cam", f"c{i}.png", 1)
    add = args(tmp_path, images=[str(tmp_path / "cam")], add=True)
    assert fd.cmd_enroll(add, FakeEngine(), store) == 0
    assert len(store.embeddings_for("me")) == 6 and store.all_embeddings()[0].count("me") == 6   # still ONE person
    # enrolling again without --add is refused and explains the ambiguity trap
    assert fd.cmd_enroll(args(tmp_path, images=[str(tmp_path / "cam")]), FakeEngine(), store) == 1
    assert "ambiguous" in capsys.readouterr().err
    # --add for someone who is not saved yet is refused
    assert fd.cmd_enroll(args(tmp_path, name="nobody", images=[str(tmp_path / "cam")], add=True), FakeEngine(), store) == 1


def test_store_add_embeddings_has_a_cap(tmp_path):
    import pytest
    from app.store import FaceStore

    store = FaceStore(str(tmp_path / "s.db"))
    store.add_user("me", "W", [np.ones(512, np.float32)] * 3)
    assert store.add_embeddings("me", [np.ones(512, np.float32)] * 2) == 5
    assert store.room_for("me") == 35 and store.room_for("me", max_total=6) == 1
    with pytest.raises(ValueError):
        store.add_embeddings("me", [np.ones(512, np.float32)] * 36)
    with pytest.raises(KeyError):
        store.add_embeddings("ghost", [np.ones(512, np.float32)])


def test_debug_line_shows_the_threshold_that_was_actually_used():
    from app.face_engine import FaceResult
    emb = np.zeros(512, np.float32)
    emb[0] = 1.0
    owners, gal = ["me"], emb[None, :].copy()
    face = FaceResult(emb * 0.6 + np.eye(512, dtype=np.float32)[1] * 0.8, 0.99, (0, 0, 200, 200), 500.0, 0.0)  # 60% similar
    lenient = fd.report_for(face, owners, gal, 0.45, 0.05)
    strict = fd.report_for(face, owners, gal, 0.90, 0.05)
    assert lenient.matched and "need 45% to match" in fd.describe(lenient)
    assert not strict.matched and "need 90% to match" in fd.describe(strict)     # used to say 45% here


def test_add_checks_for_room_before_capturing_anything(tmp_path, capsys):
    from app.store import FaceStore

    store = FaceStore(str(tmp_path / "f.db"))
    store.add_user("me", "W", [np.ones(512, np.float32)] * 10)
    cam_used = []

    class Boom:
        def analyse(self, img):
            cam_used.append(1)
            raise AssertionError("must not capture when there is no room")

    a = args(tmp_path, add=True, guided=True, max_templates=20)          # 10 held + 13 planned > 20
    assert fd.cmd_enroll(a, Boom(), store) == 1 and not cam_used
    err = capsys.readouterr().err
    assert "room for 10 more but this needs 13" in err and "--max-templates" in err


def test_identification_is_more_lenient_than_enrollment():
    """A small, softish, dim-detected face is fine to RECOGNISE but not good enough to SAVE as a template."""
    from app.face_engine import FaceResult, QualityError, check_quality
    import pytest

    f = FaceResult(np.ones(512, np.float32), det_score=0.5, box=(0, 0, 60, 60), sharpness=40.0, turn=0.0)
    check_quality(f, identification=True)                   # passes the lenient tier
    with pytest.raises(QualityError):
        check_quality(f)                                    # rejected by the strict tier (det 0.5 < 0.6, 60px < 80, sharp 40 < 60)
    assert config.ID_MIN_DET_SCORE < config.MIN_DET_SCORE and config.ID_MIN_FACE_PX < config.MIN_FACE_PX
    assert config.ID_MIN_SHARPNESS < config.MIN_SHARPNESS


def test_enrollment_images_use_the_strict_tier_and_identification_photos_the_lenient_one(tmp_path):
    from app.face_engine import FaceResult

    class Soft:
        def analyse(self, img):  # a faint but usable face: fine to recognise, too soft to enroll from
            return [FaceResult(np.ones(512, np.float32) / 22.6, 0.99, (0, 0, 200, 200), 40.0, 0.0)]

    folder = write(tmp_path, "soft", "s.png", 1)
    from app.store import FaceStore
    store = FaceStore(str(tmp_path / "t.db"))
    assert fd.cmd_enroll(args(tmp_path, images=[str(folder)]), Soft(), store) == 1          # strict: 40 < 60, nothing saved
    assert not store.user_exists("me")
    assert fd.largest_usable(Soft(), np.zeros((50, 50, 3), np.uint8), identification=True)   # lenient: 40 >= 25
