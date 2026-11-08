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
                mine=None, others=None)
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
