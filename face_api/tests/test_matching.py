import numpy as np

from app.matching import match

from .conftest import person_vec


def gallery(*pairs):
    return [p for p, _ in pairs], np.stack([v for _, v in pairs])


def test_best_of_multiple_embeddings_per_user():
    owners, g = gallery(("a", person_vec(1)), ("a", person_vec(5)), ("b", person_vec(2)))
    assert match(person_vec(5), owners, g).user_id == "a"


def test_ambiguous_when_two_users_look_alike():
    base = person_vec(1)
    twin = base + 0.01 * person_vec(3)
    twin /= np.linalg.norm(twin)
    owners, g = gallery(("a", base), ("b", twin))
    r = match(base, owners, g)
    assert not r.matched and r.reason == "ambiguous"
