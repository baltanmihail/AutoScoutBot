"""Проверки калиброванного слияния (backend/ranking.py). Запуск: python test_ranking.py"""
import math
import random

from backend.ranking import StagePercentiles, calibrated_scores, effective_relevance_weight, stage_of


def order(xs):
    return sorted(range(len(xs)), key=lambda i: -xs[i])


def test_scale_invariance():
    rnd = random.Random(0)
    rel = [rnd.uniform(0.4, 0.7) for _ in range(100)]
    attr = [rnd.uniform(1, 10) for _ in range(100)]
    f1, _ = calibrated_scores(rel, attr, 0.5)
    f2, _ = calibrated_scores([10 * r + 3 for r in rel], [a / 7 for a in attr], 0.5)
    assert order(f1) == order(f2), "порядок должен не зависеть от шкал сигналов"


def test_weight_extremes():
    rnd = random.Random(1)
    rel = [rnd.random() for _ in range(50)]
    attr = [rnd.random() for _ in range(50)]
    assert order(calibrated_scores(rel, attr, 1.0)[0]) == order(rel)
    assert order(calibrated_scores(rel, attr, 0.0)[0]) == order(attr)


def test_display_bounds_and_monotonic():
    rnd = random.Random(2)
    fused, disp = calibrated_scores([rnd.random() for _ in range(80)], [rnd.random() for _ in range(80)])
    assert all(0.0 <= d <= 10.0 for d in disp)
    assert order(fused) == order(disp)


def test_stage_percentiles():
    sp = StagePercentiles([(2, 3.0), (2, 5.0), (8, 7.0), (8, 9.0), (None, 4.0), ("7", 8.0)])
    assert stage_of(None) == "unknown" and stage_of("0") == "unknown" and stage_of("5") == "trl_4_6"
    assert sp.percentile(2, 5.0) == 1.0 and sp.percentile(2, 3.0) == 0.5
    assert math.isclose(sp.percentile(9, 8.0), 2 / 3)
    assert sp.percentile(5, 6.0) == 0.5 and sp.percentile(2, None) == 0.5


def test_effective_weight():
    rel = [0.0, 1.0] * 10          # sd 0.5
    attr = [0.0, 3.0] * 10         # sd 1.5
    assert math.isclose(effective_relevance_weight(rel, attr, 0.5), 0.25)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
