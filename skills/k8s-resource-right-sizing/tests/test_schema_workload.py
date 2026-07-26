import copy

from scripts import schema

VALID_CONFIG = {
    "kind": "Deployment",
    "name": "my-app",
    "namespace": "default",
    "replicas": 3,
    "containers": [
        {
            "name": "app",
            "requests": {"cpu": "500m", "memory": "512Mi"},
            "limits": {"cpu": "1", "memory": "1Gi"},
        }
    ],
    "hpa": None,
    "restartHistory": [],
    "platformRequiresLimits": True,
    "platformLimitPolicy": None,
}


def test_fully_populated_valid_config_passes():
    assert schema.validate_workload_config(VALID_CONFIG) == []


def test_empty_containers_fails():
    data = copy.deepcopy(VALID_CONFIG)
    data["containers"] = []
    assert schema.validate_workload_config(data) != []


def test_container_missing_requests_memory_fails():
    data = copy.deepcopy(VALID_CONFIG)
    del data["containers"][0]["requests"]["memory"]
    assert schema.validate_workload_config(data) != []


def test_container_limits_null_passes():
    data = copy.deepcopy(VALID_CONFIG)
    data["containers"][0]["limits"] = None
    assert schema.validate_workload_config(data) == []


def test_hpa_null_passes():
    data = copy.deepcopy(VALID_CONFIG)
    data["hpa"] = None
    assert schema.validate_workload_config(data) == []


def test_restart_history_empty_list_passes():
    data = copy.deepcopy(VALID_CONFIG)
    data["restartHistory"] = []
    assert schema.validate_workload_config(data) == []


def test_restart_history_null_fails():
    data = copy.deepcopy(VALID_CONFIG)
    data["restartHistory"] = None
    assert schema.validate_workload_config(data) != []


def test_platform_requires_limits_null_passes():
    data = copy.deepcopy(VALID_CONFIG)
    data["platformRequiresLimits"] = None
    assert schema.validate_workload_config(data) == []


def test_platform_requires_limits_unknown_string_fails():
    data = copy.deepcopy(VALID_CONFIG)
    data["platformRequiresLimits"] = "unknown"
    assert schema.validate_workload_config(data) != []
