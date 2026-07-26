import copy

from scripts import schema

WORKLOAD_CONFIG = {
    "kind": "Deployment",
    "name": "my-app",
    "namespace": "default",
    "replicas": 3,
    "containers": [
        {"name": "app", "requests": {"cpu": "500m", "memory": "512Mi"}, "limits": None},
        {"name": "sidecar", "requests": {"cpu": "100m", "memory": "128Mi"}, "limits": None},
    ],
    "hpa": None,
    "restartHistory": [],
    "platformRequiresLimits": False,
}

METRICS_APP = {
    "container": "app",
    "observationWindowHours": 168,
    "cpu": {"samples": [{"podName": "app-0", "timestampSeries": [1, 2], "valuesMillicores": [100, 200]}]},
    "memory": {"samples": [{"podName": "app-0", "timestampSeries": [1, 2], "valuesBytes": [1000, 2000]}]},
}

METRICS_SIDECAR = {
    "container": "sidecar",
    "observationWindowHours": 168,
    "cpu": {"samples": [{"podName": "app-0", "timestampSeries": [1, 2], "valuesMillicores": [10, 20]}]},
    "memory": {"samples": [{"podName": "app-0", "timestampSeries": [1, 2], "valuesBytes": [100, 200]}]},
}


def test_mismatched_container_name_is_error():
    bogus_metrics = copy.deepcopy(METRICS_APP)
    bogus_metrics["container"] = "not-a-real-container"
    errors, warnings = schema.validate_cross(WORKLOAD_CONFIG, [bogus_metrics, METRICS_SIDECAR])
    assert any("not-a-real-container" in e for e in errors)


def test_observation_window_below_one_is_error():
    short_window = copy.deepcopy(METRICS_APP)
    short_window["observationWindowHours"] = 0.5
    errors, _ = schema.validate_cross(WORKLOAD_CONFIG, [short_window, METRICS_SIDECAR])
    assert errors != []


def test_observation_window_at_one_hour_boundary_passes():
    boundary_window = copy.deepcopy(METRICS_APP)
    boundary_window["observationWindowHours"] = 1
    errors, _ = schema.validate_cross(WORKLOAD_CONFIG, [boundary_window, METRICS_SIDECAR])
    assert errors == []


def test_container_with_no_metrics_is_warning_not_error():
    errors, warnings = schema.validate_cross(WORKLOAD_CONFIG, [METRICS_APP])
    assert errors == []
    assert any("sidecar" in w for w in warnings)
