import copy

from scripts import schema

VALID_METRICS = {
    "container": "app",
    "observationWindowHours": 168,
    "cpu": {"samples": [{"podName": "app-0", "timestampSeries": [1, 2, 3], "valuesMillicores": [100, 200, 300]}]},
    "memory": {"samples": [{"podName": "app-0", "timestampSeries": [1, 2, 3], "valuesBytes": [1000, 2000, 3000]}]},
    "oomEvents": [],
}


def test_valid_metrics_entry_passes():
    assert schema.validate_runtime_metrics(VALID_METRICS) == []


def test_missing_cpu_samples_fails():
    data = copy.deepcopy(VALID_METRICS)
    del data["cpu"]["samples"]
    assert schema.validate_runtime_metrics(data) != []
