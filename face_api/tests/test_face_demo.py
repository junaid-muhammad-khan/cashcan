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
                mine=None, others=None, add=False)
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
    assert not blurry.usable and "blurry" in blurry.label and f"12 < {config.MIN_SHARPNESS:.0f}" in blurry.label
    small = _report(box=(0, 0, 60, 70))
    assert "too small" in small.label and "60px < 80px" in small.label
    unclear = _report(det=0.4)
    assert "unclear" in unclear.label and "0.40 < 0.60" in unclear.label
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
    with pytest.raises(ValueError):
        store.add_embeddings("me", [np.ones(512, np.float32)] * 20)
    with pytest.raises(KeyError):
        store.add_embeddings("ghost", [np.ones(512, np.float32)])
