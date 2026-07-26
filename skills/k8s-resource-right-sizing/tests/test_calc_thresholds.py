from scripts import calc


# --- cpu_overprovisioned: current > recommended * 2 (strict) ---

def test_cpu_overprovisioned_at_boundary_is_false():
    assert calc.cpu_overprovisioned(current_cpu_request=200, recommended_cpu_request=100) is False


def test_cpu_overprovisioned_above_boundary_is_true():
    assert calc.cpu_overprovisioned(current_cpu_request=201, recommended_cpu_request=100) is True


def test_cpu_overprovisioned_below_boundary_is_false():
    assert calc.cpu_overprovisioned(current_cpu_request=199, recommended_cpu_request=100) is False


# --- memory_overprovisioned: current > recommended * 1.5 (strict), unless trend/OOM ---

def test_memory_overprovisioned_at_boundary_is_false():
    assert (
        calc.memory_overprovisioned(
            current_memory_request=150,
            recommended_memory_request=100,
            increasing_trend=False,
            any_oom_events=False,
        )
        is False
    )


def test_memory_overprovisioned_above_boundary_is_true():
    assert (
        calc.memory_overprovisioned(
            current_memory_request=151,
            recommended_memory_request=100,
            increasing_trend=False,
            any_oom_events=False,
        )
        is True
    )


def test_memory_overprovisioned_false_when_increasing_trend():
    assert (
        calc.memory_overprovisioned(
            current_memory_request=1000,
            recommended_memory_request=100,
            increasing_trend=True,
            any_oom_events=False,
        )
        is False
    )


def test_memory_overprovisioned_false_when_oom_events():
    assert (
        calc.memory_overprovisioned(
            current_memory_request=1000,
            recommended_memory_request=100,
            increasing_trend=False,
            any_oom_events=True,
        )
        is False
    )


# --- cpu_underprovisioned: p95_usage > current_request * 0.8 (strict) ---

def test_cpu_underprovisioned_at_boundary_is_false():
    assert calc.cpu_underprovisioned(p95_cpu_usage=80, current_cpu_request=100) is False


def test_cpu_underprovisioned_above_boundary_is_true():
    assert calc.cpu_underprovisioned(p95_cpu_usage=81, current_cpu_request=100) is True


def test_cpu_underprovisioned_below_boundary_is_false():
    assert calc.cpu_underprovisioned(p95_cpu_usage=79, current_cpu_request=100) is False


# --- memory_underprovisioned: p95_usage > current_request * 0.9 (strict), or OOM, or trend ---

def test_memory_underprovisioned_at_boundary_is_false():
    assert (
        calc.memory_underprovisioned(
            p95_memory_usage=90,
            current_memory_request=100,
            increasing_trend=False,
            any_oom_events=False,
        )
        is False
    )


def test_memory_underprovisioned_above_boundary_is_true():
    assert (
        calc.memory_underprovisioned(
            p95_memory_usage=91,
            current_memory_request=100,
            increasing_trend=False,
            any_oom_events=False,
        )
        is True
    )


def test_memory_underprovisioned_true_on_oom_events_even_if_ratio_low():
    assert (
        calc.memory_underprovisioned(
            p95_memory_usage=10,
            current_memory_request=100,
            increasing_trend=False,
            any_oom_events=True,
        )
        is True
    )


def test_memory_underprovisioned_true_on_increasing_trend_even_if_ratio_low():
    assert (
        calc.memory_underprovisioned(
            p95_memory_usage=10,
            current_memory_request=100,
            increasing_trend=True,
            any_oom_events=False,
        )
        is True
    )
