"""kubectl + Prometheus I/O for batch right-sizing analysis.

Stdlib only, beyond `jsonschema` (already required by scripts/schema.py) --
no Kubernetes or Prometheus client libraries. Requires `kubectl` on PATH,
already pointed at the target cluster (same assumption test/README.md
makes for the manual skill-testing setup), and a reachable Prometheus URL.

This module only builds the parts of the workload-config shape (spec
§4.1) that are genuinely discoverable from live cluster state --
`platformRequiresLimits` / `platformLimitPolicy` are policy questions, not
cluster state, and are layered on by rightsize_batch.py from a policy
file instead.
"""

import json
import subprocess
import urllib.parse
import urllib.request

SUPPORTED_KINDS = ["deployment", "statefulset", "daemonset"]
_KIND_LABEL = {"deployment": "Deployment", "statefulset": "StatefulSet", "daemonset": "DaemonSet"}


def kubectl_get_json(args: list[str]) -> dict:
    proc = subprocess.run(["kubectl", "get", *args, "-o", "json"], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"kubectl get {' '.join(args)} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def _resources_dict(container_spec: dict, key: str) -> dict | None:
    res = (container_spec.get("resources") or {}).get(key)
    if not res:
        return None
    return {"cpu": res.get("cpu"), "memory": res.get("memory")}


def _build_base_config(kind: str, item: dict) -> dict:
    meta = item["metadata"]
    spec = item["spec"]
    containers = []
    for c in spec["template"]["spec"]["containers"]:
        requests = _resources_dict(c, "requests") or {}
        containers.append(
            {
                "name": c["name"],
                "requests": {"cpu": requests.get("cpu") or "0", "memory": requests.get("memory") or "0"},
                "limits": _resources_dict(c, "limits"),
            }
        )

    # Deployment/StatefulSet: .spec.replicas. DaemonSet has no such field --
    # unlike the interactive Skill (which must ask the user, spec §13 item
    # 4), batch mode has live cluster access and can read the scheduled
    # count directly.
    replicas = spec.get("replicas")
    if kind == "daemonset":
        replicas = item.get("status", {}).get("desiredNumberScheduled")

    config = {
        "kind": _KIND_LABEL[kind],
        "name": meta["name"],
        "namespace": meta["namespace"],
        "containers": containers,
    }
    if replicas is not None:
        config["replicas"] = replicas
    return config


def discover_workloads(namespace: str, kinds: list[str] = SUPPORTED_KINDS) -> list[dict]:
    """List Deployments/StatefulSets/DaemonSets in a namespace and translate
    each into the workload-config shape from spec §4.1 (requests/limits/
    replicas only -- see module docstring)."""
    workloads = []
    for kind in kinds:
        data = kubectl_get_json([kind, "-n", namespace])
        for item in data.get("items", []):
            workloads.append(_build_base_config(kind, item))
    return workloads


def discover_hpas(namespace: str) -> dict:
    """Map (kind, name) -> hpa dict (spec §4.1 shape) for every HPA in the
    namespace, keyed by its scaleTargetRef. A workload with no entry here
    is treated as hpa: null (spec §4.1's "confirmed absent" state) -- this
    is an approximation of "confirmed" based on what kubectl currently
    sees, not a literal confirmation from a human; see README.md's
    Limitations section."""
    try:
        data = kubectl_get_json(["hpa", "-n", namespace])
    except RuntimeError:
        return {}
    result = {}
    for item in data.get("items", []):
        ref = item["spec"]["scaleTargetRef"]
        target_cpu = None
        for m in item["spec"].get("metrics", []) or []:
            if m.get("type") == "Resource" and m["resource"]["name"] == "cpu":
                target_cpu = m["resource"].get("target", {}).get("averageUtilization")
        result[(ref["kind"], ref["name"])] = {
            "min": item["spec"].get("minReplicas"),
            "max": item["spec"]["maxReplicas"],
            "targetCPUUtilization": target_cpu,
        }
    return result


def discover_restart_history(namespace: str, workload_name: str) -> list[dict]:
    """Aggregate terminated-container reasons/counts for pods currently
    named `<workload_name>-...` (the same pod-name-prefix convention
    test/scripts/extract_metrics.py uses to scope a PromQL query). This
    only sees currently-live pods' last-terminated-state, not full
    historical restart counts -- a real limitation vs. asking a human who
    remembers what happened last week; documented in README.md."""
    try:
        data = kubectl_get_json(["pods", "-n", namespace])
    except RuntimeError:
        return []
    counts: dict[tuple[str, str], int] = {}
    for pod in data.get("items", []):
        if not pod["metadata"]["name"].startswith(f"{workload_name}-"):
            continue
        for cs in pod.get("status", {}).get("containerStatuses", []):
            last_state = (cs.get("lastState") or {}).get("terminated")
            if last_state and last_state.get("reason"):
                key = (cs["name"], last_state["reason"])
                counts[key] = counts.get(key, 0) + 1
    return [{"container": container, "reason": reason, "count": count} for (container, reason), count in sorted(counts.items())]


def prom_query_range(prom_url: str, query: str, start: float, end: float, step: str = "5m") -> list:
    params = {"query": query, "start": start, "end": end, "step": step}
    url = f"{prom_url}/api/v1/query_range?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus query failed: {data}")
    return data["data"]["result"]


def build_container_metrics(prom_url: str, namespace: str, workload: str, container: str, start: float, end: float) -> dict:
    """Same PromQL shape as test/scripts/extract_metrics.py, reused here so
    the batch script and the manual skill-testing extractor stay
    consistent with each other and with spec §4.2's runtime-metrics shape."""
    cpu_query = (
        f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}", '
        f'pod=~"{workload}-.*", container="{container}"}}[5m]) * 1000'
    )
    mem_query = (
        f'container_memory_working_set_bytes{{namespace="{namespace}", '
        f'pod=~"{workload}-.*", container="{container}"}}'
    )
    oom_query = (
        f'kube_pod_container_status_last_terminated_reason{{namespace="{namespace}", '
        f'pod=~"{workload}-.*", container="{container}", reason="OOMKilled"}}'
    )

    cpu_series = prom_query_range(prom_url, cpu_query, start, end)
    mem_series = prom_query_range(prom_url, mem_query, start, end)
    oom_series = prom_query_range(prom_url, oom_query, start, end)

    cpu_samples = [
        {
            "podName": s["metric"]["pod"],
            "timestampSeries": [v[0] for v in s["values"]],
            "valuesMillicores": [float(v[1]) for v in s["values"]],
        }
        for s in cpu_series
    ]
    mem_samples = [
        {
            "podName": s["metric"]["pod"],
            "timestampSeries": [v[0] for v in s["values"]],
            "valuesBytes": [float(v[1]) for v in s["values"]],
        }
        for s in mem_series
    ]
    oom_events = [
        {"podName": s["metric"]["pod"], "timestamp": v[0]} for s in oom_series for v in s["values"] if float(v[1]) == 1
    ]

    return {
        "container": container,
        "observationWindowHours": round((end - start) / 3600, 2),
        "cpu": {"samples": cpu_samples},
        "memory": {"samples": mem_samples},
        "oomEvents": oom_events,
    }
