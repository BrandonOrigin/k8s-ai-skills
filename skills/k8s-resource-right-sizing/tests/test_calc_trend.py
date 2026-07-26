from scripts import calc


def test_single_pod_rising_above_threshold_is_true():
    series = [(1, 100), (2, 100), (3, 120), (4, 120)]  # first half mean 100, second half mean 120: +20%
    assert calc.container_memory_trend_increasing([series]) is True


def test_single_pod_flat_is_false():
    series = [(1, 100), (2, 100), (3, 100), (4, 100)]
    assert calc.container_memory_trend_increasing([series]) is False


def test_single_pod_falling_is_false():
    series = [(1, 100), (2, 100), (3, 80), (4, 80)]  # -20%
    assert calc.container_memory_trend_increasing([series]) is False


def test_multi_replica_average_just_below_threshold_is_false():
    # pod A rises 19%, pod B falls 1%. Average = (0.19 + -0.01) / 2 = 0.09 -> False.
    # (An exact 0.10 average isn't reliably constructible from computed
    # float ratios -- e.g. 110/100 - 1 != the 0.1 literal -- so this checks
    # the strict `>` boundary from just below rather than an exact tie.)
    pod_a = [(1, 100), (2, 100), (3, 119), (4, 119)]
    pod_b = [(1, 100), (2, 100), (3, 99), (4, 99)]
    assert calc.container_memory_trend_increasing([pod_a, pod_b]) is False


def test_multi_replica_average_just_above_threshold_is_true():
    # pod A rises 31%, pod B falls 9%. Average = (0.31 + -0.09) / 2 = 0.11 -> True.
    pod_a = [(1, 100), (2, 100), (3, 131), (4, 131)]
    pod_b = [(1, 100), (2, 100), (3, 91), (4, 91)]
    assert calc.container_memory_trend_increasing([pod_a, pod_b]) is True


def test_short_pod_excluded_from_signal():
    # Pod A is flat (pct 0%, 4 samples). Pod B has only 2 samples showing a
    # huge apparent rise, but must be excluded (< 4 samples) rather than
    # counted -- if it were wrongly included the average would flip to True.
    pod_a = [(1, 100), (2, 100), (3, 100), (4, 100)]
    pod_b = [(1, 100), (2, 1000)]
    assert calc.container_memory_trend_increasing([pod_a, pod_b]) is False


def test_all_pods_excluded_is_false():
    pod_a = [(1, 100), (2, 100)]
    pod_b = [(1, 50)]
    assert calc.container_memory_trend_increasing([pod_a, pod_b]) is False


def test_zero_first_half_mean_skipped_without_error():
    # First half mean is 0 -- must be skipped, not raise ZeroDivisionError.
    series = [(1, 0), (2, 0), (3, 50), (4, 50)]
    assert calc.container_memory_trend_increasing([series]) is False


def test_no_series_is_false():
    assert calc.container_memory_trend_increasing([]) is False
