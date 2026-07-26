from scripts import calc


def test_percentile_p50_known_array():
    # [100,200,300,400,500], n=5: rank = 0.5*(5-1) = 2 -> values[2] = 300
    assert calc.percentile([100, 200, 300, 400, 500], 50) == 300


def test_percentile_p95_known_array():
    # rank = 0.95*(5-1) = 3.8 -> between values[3]=400 and values[4]=500,
    # fraction 0.8: 400 + (500-400)*0.8 = 480. Matches
    # numpy.percentile([100,200,300,400,500], 95, method="linear").
    assert calc.percentile([100, 200, 300, 400, 500], 95) == 480


def test_percentile_unsorted_input():
    assert calc.percentile([500, 100, 300, 200, 400], 50) == 300


def test_percentile_single_value():
    assert calc.percentile([42], 95) == 42


def test_aggregate_samples_single_replica_is_noop():
    single_pod = [[10, 20, 30]]
    assert calc.aggregate_samples(single_pod) == [10, 20, 30]


def test_aggregate_samples_multi_replica_concatenates():
    pods = [[10, 20], [30, 40], [50]]
    combined = calc.aggregate_samples(pods)
    assert combined == [10, 20, 30, 40, 50]
    assert len(combined) == sum(len(p) for p in pods)
