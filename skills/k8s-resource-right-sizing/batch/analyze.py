"""Pure batch analysis logic for Kubernetes resource right-sizing.

This is the same ANALYZE -> RECOMMEND -> IMPACT pipeline SKILL.md drives
conversationally, run unattended over already-resolved inputs -- no LLM
call anywhere in this module. It imports scripts/calc.py and
scripts/schema.py directly, so the arithmetic is byte-for-byte the same
engine the interactive Skill uses; only the orchestration differs (no
conversation, no follow-up questions -- missing/ambiguous inputs degrade
confidence or exclude a container rather than getting asked about).

See k8s_client.py for the kubectl/Prometheus I/O that feeds this module,
and batch/README.md for how the two fit together in a CI/CD pipeline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import calc, schema  # noqa: E402


def analyze_container(container_config: dict, metrics_entry: dict | None, replicas: int | None, workload_config: dict) -> dict:
    """Run one container through spec §§6-10, §12. Mirrors SKILL.md's
    RECOMMEND state exactly, minus the conversation."""
    name = container_config["name"]
    requests = container_config["requests"]
    limits = container_config.get("limits")

    result = {
        "container": name,
        "current_request": {"cpu": requests["cpu"], "memory": requests["memory"]},
        "has_metrics": False,
    }

    if metrics_entry is None:
        result["confidence"] = "LOW"
        result["note"] = "no runtime metrics available -- excluded from analysis"
        return result

    cpu_combined = calc.aggregate_samples([s["valuesMillicores"] for s in metrics_entry["cpu"]["samples"]])
    mem_combined = calc.aggregate_samples([s["valuesBytes"] for s in metrics_entry["memory"]["samples"]])
    if not cpu_combined or not mem_combined:
        result["confidence"] = "LOW"
        result["note"] = "zero usable samples -- excluded from analysis"
        return result

    result["has_metrics"] = True
    cpu_p50 = calc.percentile(cpu_combined, 50)
    cpu_p95 = calc.percentile(cpu_combined, 95)
    mem_p50 = calc.percentile(mem_combined, 50)
    mem_p95 = calc.percentile(mem_combined, 95)

    current_cpu = calc.parse_cpu_quantity(requests["cpu"])
    current_mem = calc.parse_memory_quantity(requests["memory"])

    recommended_cpu = calc.round_cpu_millicores(calc.recommended_cpu_millicores(cpu_p95))
    recommended_mem = calc.round_memory_bytes(calc.recommended_memory_bytes(mem_p95))

    pod_mem_series = [list(zip(s["timestampSeries"], s["valuesBytes"])) for s in metrics_entry["memory"]["samples"]]
    increasing_trend = calc.container_memory_trend_increasing(pod_mem_series)
    any_oom = len(metrics_entry.get("oomEvents", [])) > 0

    # Limit decision (spec §12). Existing limits win regardless of platform
    # policy -- a policy question is only meaningful when there's nothing
    # to derive a ratio from yet.
    recommended_limit = None
    limit_source = None
    used_conservative_default = False
    if limits and current_cpu > 0 and current_mem > 0:
        ratio_cpu = calc.parse_cpu_quantity(limits["cpu"]) / current_cpu
        ratio_mem = calc.parse_memory_quantity(limits["memory"]) / current_mem
        recommended_limit = {
            "cpu": calc.round_limit_from_ratio(recommended_cpu, ratio_cpu, calc.round_cpu_millicores),
            "memory": calc.round_limit_from_ratio(recommended_mem, ratio_mem, calc.round_memory_bytes),
        }
        limit_source = "existing-ratio"
    elif workload_config.get("platformRequiresLimits") is True:
        policy = workload_config.get("platformLimitPolicy")
        limit_cpu, used_default_cpu = calc.apply_limit_policy(recommended_cpu, policy, "cpu", calc.round_cpu_millicores)
        limit_mem, used_default_mem = calc.apply_limit_policy(recommended_mem, policy, "memory", calc.round_memory_bytes)
        recommended_limit = {"cpu": limit_cpu, "memory": limit_mem}
        used_conservative_default = used_default_cpu or used_default_mem
        limit_source = "conservative-default" if used_conservative_default else "policy"
    # else: platformRequiresLimits is False/unknown -> requests-only, no
    # limit recommendation (spec §12).

    flags = {
        "cpu_overprovisioned": calc.cpu_overprovisioned(current_cpu, recommended_cpu),
        "cpu_underprovisioned": calc.cpu_underprovisioned(cpu_p95, current_cpu),
        "memory_overprovisioned": calc.memory_overprovisioned(current_mem, recommended_mem, increasing_trend, any_oom),
        "memory_underprovisioned": calc.memory_underprovisioned(mem_p95, current_mem, increasing_trend, any_oom),
    }

    cpu_ratio = calc.variability_ratio(cpu_p50, cpu_p95)
    mem_ratio = calc.variability_ratio(mem_p50, mem_p95)
    overall_variability = calc.variability_class(max(cpu_ratio, mem_ratio))

    scoped_config = {**workload_config, "containers": [container_config]}
    critical_missing = schema.critical_info_missing(scoped_config, [metrics_entry])

    confidence = calc.confidence_level(
        observation_hours=metrics_entry["observationWindowHours"],
        overall_variability=overall_variability,
        workload_info_complete=schema.workload_info_complete(workload_config),
        critical_info_missing=critical_missing,
    )

    impact = None
    if replicas is not None:
        impact = {
            "current_total_cpu_millicores": replicas * current_cpu,
            "recommended_total_cpu_millicores": replicas * recommended_cpu,
            "current_total_memory_bytes": replicas * current_mem,
            "recommended_total_memory_bytes": replicas * recommended_mem,
        }

    result.update(
        {
            "usage": {
                "cpu_p50_millicores": cpu_p50,
                "cpu_p95_millicores": cpu_p95,
                "memory_p50_bytes": mem_p50,
                "memory_p95_bytes": mem_p95,
            },
            "recommended_request": {
                "cpu": calc.format_cpu_millicores(recommended_cpu),
                "memory": calc.format_memory_bytes(recommended_mem),
            },
            "recommended_limit": (
                {
                    "cpu": calc.format_cpu_millicores(recommended_limit["cpu"]),
                    "memory": calc.format_memory_bytes(recommended_limit["memory"]),
                }
                if recommended_limit
                else None
            ),
            "limit_source": limit_source,
            "used_conservative_default_limit": used_conservative_default,
            "flags": flags,
            "increasing_memory_trend": increasing_trend,
            "oom_events": any_oom,
            "confidence": confidence,
            "impact": impact,
        }
    )
    return result


def analyze_workload(workload_config: dict, metrics_list: list[dict]) -> dict:
    """Validate then analyze every container in a workload. Mirrors
    VALIDATE -> ANALYZE -> RECOMMEND -> IMPACT from SKILL.md; every input
    here must already be fully resolved since batch mode has no one to ask
    follow-up questions of."""
    errors, warnings = schema.validate_cross(workload_config, metrics_list)
    if errors:
        return {
            "kind": workload_config.get("kind"),
            "name": workload_config.get("name"),
            "namespace": workload_config.get("namespace"),
            "errors": errors,
            "warnings": [],
            "containers": [],
        }

    metrics_by_container = {m["container"]: m for m in metrics_list}
    replicas = workload_config.get("replicas")

    containers = [
        analyze_container(c, metrics_by_container.get(c["name"]), replicas, workload_config)
        for c in workload_config["containers"]
    ]

    return {
        "kind": workload_config["kind"],
        "name": workload_config["name"],
        "namespace": workload_config["namespace"],
        "replicas": replicas,
        "errors": [],
        "warnings": warnings,
        "containers": containers,
    }
