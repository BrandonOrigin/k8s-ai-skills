"""Deterministic math for Kubernetes resource right-sizing: percentiles, safety
factors, rounding, and thresholds. See docs/specs/skill1-technical-spec.md."""

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
    e.g. 134217728 -> "128Mi"."""
    if b == 0:
        return "0"
    for suffix, multiplier in _MEMORY_FORMAT_UNITS:
        if b % multiplier == 0:
            return f"{b // multiplier}{suffix}"
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
