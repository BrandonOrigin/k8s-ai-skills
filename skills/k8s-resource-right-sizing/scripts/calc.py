"""Deterministic math for Kubernetes resource right-sizing: percentiles, safety
factors, rounding, and thresholds. See docs/specs/skill1-technical-spec.md."""

import math
from statistics import mean
from typing import Callable

# K8s quantity suffixes, binary (1024-based) checked before decimal (1000-based)
# since both are valid K8s memory quantity suffixes and don't overlap textually.
_BINARY_MEMORY_SUFFIXES = {
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "Pi": 1024**5,
    "Ei": 1024**6,
}
_DECIMAL_MEMORY_SUFFIXES = {
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
    "P": 1000**5,
    "E": 1000**6,
}

# Largest-to-smallest so formatting picks the most compact exact representation.
_MEMORY_FORMAT_UNITS = [
    ("Gi", 1024**3),
    ("Mi", 1024**2),
    ("Ki", 1024),
]


def parse_cpu_quantity(s: str) -> int:
    """Parse a K8s CPU quantity ("500m", "1", "2") into millicores."""
    s = s.strip()
    if s.endswith("m"):
        return int(round(float(s[:-1])))
    return int(round(float(s) * 1000))


def parse_memory_quantity(s: str) -> int:
    """Parse a K8s memory quantity ("128Mi", "1Gi", "700Mi") into bytes."""
    s = s.strip()
    for suffix, multiplier in _BINARY_MEMORY_SUFFIXES.items():
        if s.endswith(suffix):
            return int(round(float(s[: -len(suffix)]) * multiplier))
    for suffix, multiplier in _DECIMAL_MEMORY_SUFFIXES.items():
        if s.endswith(suffix):
            return int(round(float(s[: -len(suffix)]) * multiplier))
    return int(round(float(s)))


def format_cpu_millicores(m: int) -> str:
    """Format millicores as a K8s CPU quantity string, e.g. 500 -> "500m"."""
    return f"{m}m"


def format_memory_bytes(b: int) -> str:
    """Format bytes as a K8s memory quantity string using binary units,
    e.g. 134217728 -> "128Mi", 1342177280 -> "1.25Gi". Picks the largest
    unit the value reaches or exceeds, then trims to a clean decimal."""
    if b == 0:
        return "0"
    for suffix, multiplier in _MEMORY_FORMAT_UNITS:
        if b >= multiplier:
            value = b / multiplier
            text = f"{value:.4f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return str(b)


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile on a sorted copy of `values`, matching
    numpy.percentile's default "linear" method (spec §6)."""
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    rank = (p / 100) * (n - 1)
    lower = int(rank)
    fraction = rank - lower
    if fraction == 0:
        return float(sorted_values[lower])
    return sorted_values[lower] + (sorted_values[lower + 1] - sorted_values[lower]) * fraction


def aggregate_samples(pod_sample_lists: list[list[float]]) -> list[float]:
    """Flatten per-pod sample lists into one combined list (spec §6). A
    no-op for `replicas == 1`, where there is only one list to flatten."""
    combined: list[float] = []
    for samples in pod_sample_lists:
        combined.extend(samples)
    return combined


CPU_SAFETY_FACTOR = 1.2
MEMORY_SAFETY_FACTOR = 1.25


def recommended_cpu_millicores(p95_millicores: float, safety_factor: float = CPU_SAFETY_FACTOR) -> float:
    """Pre-rounding CPU request recommendation (spec §7)."""
    return p95_millicores * safety_factor


def recommended_memory_bytes(p95_bytes: float, safety_factor: float = MEMORY_SAFETY_FACTOR) -> float:
    """Pre-rounding memory request recommendation (spec §7)."""
    return p95_bytes * safety_factor


def round_cpu_millicores(m: float) -> int:
    """Round CPU millicores up to the nearest 50m (spec §8)."""
    return math.ceil(m / 50) * 50


def round_memory_bytes(b: float) -> int:
    """Round memory bytes up to the nearest 128Mi (below 1Gi) or 256Mi
    (at or above 1Gi) (spec §8)."""
    gib = 1024**3
    if b < gib:
        step = 128 * 1024**2
    else:
        step = 256 * 1024**2
    return math.ceil(b / step) * step


def round_limit_from_ratio(rounded_request: float, ratio: float, round_fn: Callable[[float], int]) -> int:
    """Derive a rounded limit from an already-rounded request and an
    existing limit/request ratio, rounding the result with `round_fn`
    (spec §8's order of operations: round request, then multiply, then
    round the limit)."""
    return round_fn(rounded_request * ratio)


def cpu_overprovisioned(current_cpu_request: float, recommended_cpu_request: float) -> bool:
    """spec §9: current request more than 2x the recommendation."""
    return current_cpu_request > recommended_cpu_request * 2


def memory_overprovisioned(
    current_memory_request: float,
    recommended_memory_request: float,
    increasing_trend: bool,
    any_oom_events: bool,
) -> bool:
    """spec §9: current request more than 1.5x the recommendation, unless
    memory usage is trending up or OOM events have occurred."""
    return (
        current_memory_request > recommended_memory_request * 1.5
        and not increasing_trend
        and not any_oom_events
    )


def cpu_underprovisioned(p95_cpu_usage: float, current_cpu_request: float) -> bool:
    """spec §9: P95 usage above 80% of the current request."""
    return p95_cpu_usage > current_cpu_request * 0.8


def memory_underprovisioned(
    p95_memory_usage: float,
    current_memory_request: float,
    increasing_trend: bool,
    any_oom_events: bool,
) -> bool:
    """spec §9: P95 usage above 90% of the current request, or OOM events,
    or an increasing usage trend."""
    return (
        p95_memory_usage > current_memory_request * 0.9
        or any_oom_events
        or increasing_trend
    )


def container_memory_trend_increasing(pod_sample_series: list[list[tuple[float, float]]]) -> bool:
    """Per-pod first-half-vs-second-half memory trend detection (spec §9).
    Each pod's series is sorted by its own timestamp and split at its own
    midpoint; per-pod percentage changes are averaged unweighted across
    pods, flagged increasing if the average exceeds 10%."""
    per_pod_pct_changes = []
    for series in pod_sample_series:
        series = sorted(series, key=lambda s: s[0])
        if len(series) < 4:
            continue
        mid = len(series) // 2
        first_half_mean = mean(v for _, v in series[:mid])
        second_half_mean = mean(v for _, v in series[mid:])
        if first_half_mean == 0:
            continue
        per_pod_pct_changes.append(second_half_mean / first_half_mean - 1)

    if not per_pod_pct_changes:
        return False
    return mean(per_pod_pct_changes) > 0.10
