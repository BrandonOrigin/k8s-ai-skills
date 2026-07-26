import copy

from scripts import schema

COMPLETE_CONFIG = {
    "kind": "Deployment",
    "name": "my-app",
    "namespace": "default",
    "replicas": 3,
    "containers": [
        {"name": "app", "requests": {"cpu": "500m", "memory": "512Mi"}, "limits": None},
    ],
    "hpa": None,
    "restartHistory": [],
    "platformRequiresLimits": False,
}


def test_all_checklist_fields_present_is_complete():
    assert schema.workload_info_complete(COMPLETE_CONFIG) is True


def test_missing_limits_key_on_a_container_is_incomplete():
    data = copy.deepcopy(COMPLETE_CONFIG)
    del data["containers"][0]["limits"]
    assert schema.workload_info_complete(data) is False


def test_missing_hpa_key_is_incomplete():
    data = copy.deepcopy(COMPLETE_CONFIG)
    del data["hpa"]
    assert schema.workload_info_complete(data) is False


def test_missing_restart_history_key_is_incomplete():
    data = copy.deepcopy(COMPLETE_CONFIG)
    del data["restartHistory"]
    assert schema.workload_info_complete(data) is False


def test_missing_platform_requires_limits_key_is_incomplete():
    data = copy.deepcopy(COMPLETE_CONFIG)
    del data["platformRequiresLimits"]
    assert schema.workload_info_complete(data) is False


def test_platform_requires_limits_true_with_policy_key_absent_is_incomplete():
    data = copy.deepcopy(COMPLETE_CONFIG)
    data["platformRequiresLimits"] = True
    # platformLimitPolicy key intentionally absent -- the policy question hasn't been asked.
    assert schema.workload_info_complete(data) is False


def test_platform_requires_limits_true_with_policy_null_is_complete():
    data = copy.deepcopy(COMPLETE_CONFIG)
    data["platformRequiresLimits"] = True
    data["platformLimitPolicy"] = None  # "not sure" -- asked, doesn't know, still resolved.
    assert schema.workload_info_complete(data) is True


def test_container_with_no_metrics_is_critical_info_missing():
    metrics_list = []  # no metrics entry at all for the "app" container
    assert schema.critical_info_missing(COMPLETE_CONFIG, metrics_list) is True


def test_container_with_metrics_and_requests_is_not_critical_info_missing():
    metrics_list = [{"container": "app", "observationWindowHours": 168}]
    assert schema.critical_info_missing(COMPLETE_CONFIG, metrics_list) is False
