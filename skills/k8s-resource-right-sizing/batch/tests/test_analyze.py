"""Tests for the pure batch analysis logic in analyze.py. No kubectl, no
Prometheus, no LLM -- these exercise the same calc.py/schema.py engine
tests/test_scenarios.py already validates for the interactive Skill,
reusing the same examples/sample-input.json fixture so both stay
in sync."""

import json
from pathlib import Path

import analyze

SAMPLE_INPUT_PATH = Path(__file__).resolve().parent.parent.parent / "examples" / "sample-input.json"


def _load_sample():
    return json.loads(SAMPLE_INPUT_PATH.read_text())


def _container(workload_config, name):
    return next(c for c in workload_config["containers"] if c["name"] == name)


def _metrics_for(metrics_list, name):
    return next(m for m in metrics_list if m["container"] == name)


def test_web_container_matches_skill_scenario():
    # Cross-checked against tests/test_scenarios.py's
    # test_multi_replica_workload_web_container / ratio-branch assertions
    # for the same fixture -- the batch engine must produce identical
    # numbers to the interactive Skill.
    data = _load_sample()
    wc = data["workloadConfig"]
    result = analyze.analyze_container(_container(wc, "web"), _metrics_for(data["metrics"], "web"), wc["replicas"], wc)

    assert result["has_metrics"] is True
    assert result["recommended_request"] == {"cpu": "500m", "memory": "512Mi"}
    assert result["recommended_limit"] == {"cpu": "1000m", "memory": "1Gi"}
    assert result["limit_source"] == "existing-ratio"
    assert result["used_conservative_default_limit"] is False
    assert result["impact"]["current_total_cpu_millicores"] == 3 * 500
    assert result["impact"]["recommended_total_cpu_millicores"] == 3 * 500


def test_worker_container_oom_forces_underprovisioned_and_policy_limit():
    data = _load_sample()
    wc = data["workloadConfig"]
    result = analyze.analyze_container(_container(wc, "worker"), _metrics_for(data["metrics"], "worker"), wc["replicas"], wc)

    assert result["recommended_request"] == {"cpu": "350m", "memory": "384Mi"}
    assert result["flags"]["memory_underprovisioned"] is True  # OOM events alone force this
    assert result["oom_events"] is True
    assert result["limit_source"] == "policy"  # platformLimitPolicy is populated, not "not sure"
    assert result["used_conservative_default_limit"] is False


def test_container_with_no_metrics_forced_low_confidence():
    data = _load_sample()
    wc = data["workloadConfig"]
    result = analyze.analyze_container(_container(wc, "log-shipper"), None, wc["replicas"], wc)

    assert result["has_metrics"] is False
    assert result["confidence"] == "LOW"
    assert "no runtime metrics" in result["note"]


def test_analyze_workload_full_sample_produces_one_result_per_container():
    data = _load_sample()
    # log-shipper has no matching metrics entry in the fixture -- validate_cross
    # should warn (not reject), and it should still get its own report entry.
    metrics_list = [m for m in data["metrics"]]
    report = analyze.analyze_workload(data["workloadConfig"], metrics_list)

    assert report["errors"] == []
    assert any("log-shipper" in w for w in report["warnings"])
    assert {c["container"] for c in report["containers"]} == {"web", "worker", "log-shipper"}
    log_shipper = next(c for c in report["containers"] if c["container"] == "log-shipper")
    assert log_shipper["confidence"] == "LOW"
    assert log_shipper["has_metrics"] is False


def test_analyze_workload_validation_errors_short_circuit_analysis():
    bad_config = {
        "kind": "Deployment",
        "name": "broken",
        "namespace": "default",
        "containers": [],  # minItems: 1 violated
    }
    report = analyze.analyze_workload(bad_config, [])
    assert report["errors"] != []
    assert report["containers"] == []


def test_daemonset_without_replicas_key_yields_no_impact_totals():
    workload_config = {
        "kind": "DaemonSet",
        "name": "log-agent",
        "namespace": "kube-system",
        "containers": [{"name": "agent", "requests": {"cpu": "100m", "memory": "128Mi"}, "limits": None}],
        "hpa": None,
        "restartHistory": [],
        "platformRequiresLimits": False,
    }
    metrics_entry = {
        "container": "agent",
        "observationWindowHours": 168,
        "cpu": {"samples": [{"podName": "agent-0", "timestampSeries": [1, 2], "valuesMillicores": [50, 60]}]},
        "memory": {"samples": [{"podName": "agent-0", "timestampSeries": [1, 2], "valuesBytes": [1000, 2000]}]},
    }
    result = analyze.analyze_container(workload_config["containers"][0], metrics_entry, workload_config.get("replicas"), workload_config)
    assert result["impact"] is None  # replicas unset -> "not computable", never guessed
    assert result["recommended_limit"] is None  # platformRequiresLimits False -> requests-only
