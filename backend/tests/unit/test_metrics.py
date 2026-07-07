from app.eval import metrics


def test_recall_at_k_full_hit():
    assert metrics.recall_at_k(["a", "b"], ["a", "b", "c"]) == 1.0


def test_recall_at_k_partial():
    assert metrics.recall_at_k(["a", "b"], ["a", "x"]) == 0.5


def test_recall_at_k_empty_expected_is_vacuously_one():
    assert metrics.recall_at_k([], ["a"]) == 1.0


def test_grounded_pass_requires_all_nodes():
    assert metrics.grounded_pass(["n1", "n2"], ["n1", "n2", "n3"]) is True
    assert metrics.grounded_pass(["n1", "n2"], ["n1"]) is False


def test_percentile_basic():
    assert metrics.percentile([10, 20, 30, 40], 95) == 40
    assert metrics.percentile([], 95) == 0.0
