"""End-to-end scenario tests wiring calc.py and schema.py together, covering
every scenario from spec §14. These assert on computed values (recommended
request/limit numbers, confidence tier, over/under-provisioning flags), not
on rendered Markdown -- report rendering is the model's job (SKILL.md), not
this script's."""

import json
from pathlib import Path

from scripts import calc, schema

SAMPLE_INPUT_PATH = Path(__file__).resolve().parent.parent / "examples" / "sample-input.json"


def _load_sample():
    return json.loads(SAMPLE_INPUT_PATH.read_text())


def _container(workload_config, name):
    return next(c for c in workload_config["containers"] if c["name"] == name)


def _metrics_for(metrics_list, name):
    return next(m for m in metrics_list if m["container"] == name)


def _percentiles(metrics_entry):
    cpu_combined = calc.aggregate_samples([s["valuesMillicores"] for s in metrics_entry["cpu"]["samples"]])
    mem_combined = calc.aggregate_samples([s["valuesBytes"] for s in metrics_entry["memory"]["samples"]])
    return {
        "cpu_p50": calc.percentile(cpu_combined, 50),
        "cpu_p95": calc.percentile(cpu_combined, 95),
        "mem_p50": calc.percentile(mem_combined, 50),
        "mem_p95": calc.percentile(mem_combined, 95),
    }


def test_single_replica_workload():
    # A single pod's samples are the aggregate as-is (spec §6's no-op case).
    samples = [100, 150, 200, 250, 300]
    combined = calc.aggregate_samples([samples])
    assert combined == samples
    assert calc.percentile(combined, 95) == calc.percentile(samples, 95)


def test_multi_replica_workload_web_container():
    data = _load_sample()
    metrics = _metrics_for(data["metrics"], "web")
    stats = _percentiles(metrics)
    assert stats["cpu_p50"] == 305.0
    assert stats["cpu_p95"] == 378.5
    assert stats["mem_p95"] == 333971456.0

    recommended_cpu = calc.round_cpu_millicores(calc.recommended_cpu_millicores(stats["cpu_p95"]))
    recommended_mem = calc.round_memory_bytes(calc.recommended_memory_bytes(stats["mem_p95"]))
    assert recommended_cpu == 500
    assert calc.format_memory_bytes(recommended_mem) == "512Mi"


def test_existing_limits_container_ratio_branch():
    data = _load_sample()
    web = _container(data["workloadConfig"], "web")
    assert web["limits"] is not None

    current_cpu = calc.parse_cpu_quantity(web["requests"]["cpu"])
    limit_cpu = calc.parse_cpu_quantity(web["limits"]["cpu"])
    ratio_cpu = limit_cpu / current_cpu
    assert ratio_cpu == 2.0

    stats = _percentiles(_metrics_for(data["metrics"], "web"))
    recommended_cpu = calc.round_cpu_millicores(calc.recommended_cpu_millicores(stats["cpu_p95"]))
    limit = calc.round_limit_from_ratio(recommended_cpu, ratio_cpu, calc.round_cpu_millicores)
    assert limit == 1000


def test_no_limits_platform_requires_limits_policy_provided():
    data = _load_sample()
    worker = _container(data["workloadConfig"], "worker")
    wc = data["workloadConfig"]
    assert worker["limits"] is None
    assert wc["platformRequiresLimits"] is True
    policy = wc["platformLimitPolicy"]
    assert policy is not None  # policy-provided branch, not "not sure"

    stats = _percentiles(_metrics_for(data["metrics"], "worker"))
    recommended_cpu = calc.round_cpu_millicores(calc.recommended_cpu_millicores(stats["cpu_p95"]))
    assert recommended_cpu == 350

    limit, used_default = calc.apply_limit_policy(recommended_cpu, policy, "cpu", calc.round_cpu_millicores)
    assert used_default is False
    assert limit == 700  # 350 * policy ratio (2.0)


def test_no_limits_platform_requires_limits_not_sure_fallback():
    # platformRequiresLimits is still True here (the platform does require
    # limits), but platformLimitPolicy is null -- the user didn't know the
    # exact ratio/cap. Falls back to the conservative default ratio.
    recommended_cpu = 300
    limit, used_default = calc.apply_limit_policy(recommended_cpu, None, "cpu", calc.round_cpu_millicores)
    assert used_default is True
    assert limit == 600  # 300 * DEFAULT_CONSERVATIVE_CPU_RATIO (2.0)

    recommended_mem = calc.parse_memory_quantity("128Mi")
    mem_limit, mem_used_default = calc.apply_limit_policy(recommended_mem, None, "memory", calc.round_memory_bytes)
    assert mem_used_default is True
    assert calc.format_memory_bytes(mem_limit) == "256Mi"  # 128Mi * 1.5 -> rounds up


def test_platform_requires_limits_false_means_requests_only():
    workload_config = {
        "kind": "Deployment",
        "name": "no-limit-policy-app",
        "namespace": "default",
        "replicas": 2,
        "containers": [
            {"name": "app", "requests": {"cpu": "100m", "memory": "128Mi"}, "limits": None},
        ],
        "hpa": None,
        "restartHistory": [],
        "platformRequiresLimits": False,
    }
    assert schema.validate_workload_config(workload_config) == []
    # No platformLimitPolicy key needed: when the platform doesn't require
    # limits, §12 never asks the policy question, and the recommendation
    # is requests-only (no limit).
    assert "platformLimitPolicy" not in workload_config
    assert schema.workload_info_complete(workload_config) is True


def test_workload_with_oom_events():
    data = _load_sample()
    worker_metrics = _metrics_for(data["metrics"], "worker")
    assert len(worker_metrics["oomEvents"]) > 0

    current_mem = calc.parse_memory_quantity(_container(data["workloadConfig"], "worker")["requests"]["memory"])
    # OOM events alone force memory_underprovisioned regardless of usage ratio.
    assert calc.memory_underprovisioned(0, current_mem, increasing_trend=False, any_oom_events=True) is True
    # And OOM events suppress memory_overprovisioned even if the ratio would otherwise flag it.
    assert (
        calc.memory_overprovisioned(current_mem * 10, current_mem, increasing_trend=False, any_oom_events=True)
        is False
    )


def test_observation_window_below_24_hours_downgrades_confidence_not_blocking():
    metrics_entry = {
        "container": "app",
        "observationWindowHours": 12,
        "cpu": {"samples": [{"podName": "app-0", "timestampSeries": [1, 2], "valuesMillicores": [100, 100]}]},
        "memory": {"samples": [{"podName": "app-0", "timestampSeries": [1, 2], "valuesBytes": [1000, 1000]}]},
    }
    # Below 24h is NOT a hard validation failure (only <1h is, per spec §4.3)
    # -- it's a confidence penalty instead, applied downstream.
    assert schema.validate_runtime_metrics(metrics_entry) == []
    confidence = calc.confidence_level(
        observation_hours=metrics_entry["observationWindowHours"],
        overall_variability="stable",
        workload_info_complete=True,
        critical_info_missing=False,
    )
    assert confidence == "LOW"


def test_daemonset_with_no_replica_count():
    workload_config = {
        "kind": "DaemonSet",
        "name": "log-agent",
        "namespace": "kube-system",
        "containers": [
            {"name": "agent", "requests": {"cpu": "100m", "memory": "128Mi"}, "limits": None},
        ],
        "hpa": None,
        "restartHistory": [],
        "platformRequiresLimits": False,
    }
    # No "replicas" key at all -- the user couldn't say how many nodes it's on.
    assert "replicas" not in workload_config
    assert schema.validate_workload_config(workload_config) == []  # replicas is schema-optional

    metrics_list = [
        {
            "container": "agent",
            "observationWindowHours": 168,
            "cpu": {"samples": [{"podName": "agent-0", "timestampSeries": [1, 2], "valuesMillicores": [50, 60]}]},
            "memory": {"samples": [{"podName": "agent-0", "timestampSeries": [1, 2], "valuesBytes": [1000, 2000]}]},
        }
    ]
    # Missing replicas counts as missing critical info -> forces LOW
    # confidence, and Replica Impact Summary reports "not computable"
    # rather than guessing a number.
    assert schema.critical_info_missing(workload_config, metrics_list) is True
    confidence = calc.confidence_level(
        observation_hours=168,
        overall_variability="stable",
        workload_info_complete=schema.workload_info_complete(workload_config),
        critical_info_missing=schema.critical_info_missing(workload_config, metrics_list),
    )
    assert confidence == "LOW"


def test_container_with_zero_metrics_samples():
    metrics_entry = {
        "container": "empty-container",
        "observationWindowHours": 168,
        "cpu": {"samples": [{"podName": "empty-container-0", "timestampSeries": [], "valuesMillicores": []}]},
        "memory": {"samples": [{"podName": "empty-container-0", "timestampSeries": [], "valuesBytes": []}]},
    }
    # Zero-length sample arrays are still schema-valid...
    assert schema.validate_runtime_metrics(metrics_entry) == []
    # ...but aggregate_samples correctly reflects there's no usable data --
    # this is the signal the caller must check before invoking percentile()
    # (an empty combined list has no well-defined percentile). A container
    # in this state must get its own report subsection with "no metrics"
    # treatment, not be silently analyzed as if it had real usage data.
    combined_cpu = calc.aggregate_samples([s["valuesMillicores"] for s in metrics_entry["cpu"]["samples"]])
    combined_mem = calc.aggregate_samples([s["valuesBytes"] for s in metrics_entry["memory"]["samples"]])
    assert combined_cpu == []
    assert combined_mem == []
