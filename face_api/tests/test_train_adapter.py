import numpy as np

from tools.train_adapter import make_pairs, split_people, wilson_upper


def labels():
    rng = np.random.default_rng(0)
    people = np.repeat(np.arange(300), rng.integers(1, 7, 300))  # 1-6 photos each
    return people


def test_splits_are_people_disjoint_and_strangers_are_single_photo_people():
    label = labels()
    sp = split_people(label, 3)
    groups = [sp["train"], sp["val"], sp["test"], sp["strangers_val"], sp["strangers_test"]]
    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            assert not (a & b)  # no person appears in two groups
    counts = {p: int((label == p).sum()) for p in set(label.tolist())}
    assert all(counts[p] >= 2 for p in sp["train"] | sp["val"] | sp["test"])
    assert all(counts[p] == 1 for p in sp["strangers_val"] | sp["strangers_test"])


def test_pairs_are_correctly_labelled_and_stay_inside_the_group():
    label = labels()
    sp = split_people(label, 0)
    a, b, same = make_pairs(label, sp["test"], np.random.default_rng(1))
    assert same.sum() == (~same).sum() and len(a) == len(b) == len(same)
    assert np.all((label[a] == label[b]) == same)  # label says same <=> same person
    assert set(label[a].tolist()) | set(label[b].tolist()) <= sp["test"]
    assert np.all(a[same] != b[same])


def test_wilson_upper_bound():
    assert wilson_upper(0, 831) > 0.003 and wilson_upper(0, 831) < 0.006  # ~3/N, never 0
