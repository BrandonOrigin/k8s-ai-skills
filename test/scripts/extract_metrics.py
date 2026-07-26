#!/usr/bin/env python3
"""
Pull per-container CPU/memory history from Prometheus and emit it in the
runtime-metrics JSON shape skill1 expects (docs/specs/skill1-technical-spec.md
Sec 4.2). Stdlib only -- no pip install required.

Usage:
    kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
    python3 extract_metrics.py \
        --namespace test-workload --workload overprovisioned-app \
        --containers app log-agent --hours 168 \
        --out overprovisioned-app-runtime-metrics.json
"""
import argparse
import json
import time
import urllib.parse
import urllib.request


def prom_query_range(prom_url, query, start, end, step="5m"):
    params = {"query": query, "start": start, "end": end, "step": step}
    url = f"{prom_url}/api/v1/query_range?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus query failed: {data}")
    return data["data"]["result"]


def build_container_metrics(prom_url, namespace, workload, container, start, end):
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
        {"podName": s["metric"]["pod"], "timestamp": v[0]}
        for s in oom_series
        for v in s["values"]
        if float(v[1]) == 1
    ]

    return {
        "container": container,
        "observationWindowHours": round((end - start) / 3600, 2),
        "cpu": {"samples": cpu_samples},
        "memory": {"samples": mem_samples},
        "oomEvents": oom_events,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prom-url", default="http://localhost:9090")
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--workload", required=True, help="Deployment name (pod name prefix)")
    ap.add_argument("--containers", nargs="+", required=True)
    ap.add_argument("--hours", type=float, default=168, help="Observation window, default 7 days")
    ap.add_argument("--out", default="skill1-runtime-metrics.json")
    args = ap.parse_args()

    end = time.time()
    start = end - args.hours * 3600

    result = [
        build_container_metrics(args.prom_url, args.namespace, args.workload, c, start, end)
        for c in args.containers
    ]

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {args.out} covering {args.hours}h for containers: {', '.join(args.containers)}")


if __name__ == "__main__":
    main()
