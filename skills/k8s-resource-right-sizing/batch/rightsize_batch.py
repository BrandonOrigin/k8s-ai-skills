#!/usr/bin/env python3
"""Unattended, no-LLM batch companion to the k8s-resource-right-sizing Skill.

Scans every Deployment/StatefulSet/DaemonSet in a namespace, pulls
historical CPU/memory usage from Prometheus, and runs the exact same
deterministic engine (scripts/calc.py + scripts/schema.py) the
interactive Skill uses -- with zero LLM calls. Meant for scheduled,
fleet-wide runs (cron, CI/CD pipeline, Kubernetes CronJob); use the
interactive Skill instead for one-off, ambiguous, or narrated analysis.
See README.md for CI/CD integration examples.

Usage:
    kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
    python3 rightsize_batch.py --namespace prod --hours 168 \\
        --out rightsizing-report.json --markdown-out rightsizing-report.md \\
        --fail-on memory_underprovisioned,oom_events,config_errors
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze  # noqa: E402
import k8s_client  # noqa: E402

_FAIL_ON_CHOICES = [
    "cpu_overprovisioned",
    "cpu_underprovisioned",
    "memory_overprovisioned",
    "memory_underprovisioned",
    "oom_events",
    "low_confidence",
    "config_errors",
]


def _apply_policy(workload_config: dict, policy: dict) -> None:
    """Layer policy-question fields (not discoverable from cluster state)
    onto a workload config, per spec §4.1/§12's rules for when
    platformLimitPolicy is even relevant."""
    requires_limits = policy.get("platformRequiresLimits")
    if requires_limits is None:
        return
    workload_config["platformRequiresLimits"] = requires_limits
    if requires_limits and policy.get("platformLimitPolicy") is not None:
        workload_config["platformLimitPolicy"] = policy["platformLimitPolicy"]


def _should_fail(reports: list[dict], fail_on: set[str]) -> bool:
    if not fail_on:
        return False
    for report in reports:
        if "config_errors" in fail_on and report.get("errors"):
            return True
        for container in report.get("containers", []):
            if "low_confidence" in fail_on and container.get("confidence") == "LOW":
                return True
            if "oom_events" in fail_on and container.get("oom_events"):
                return True
            flags = container.get("flags") or {}
            for flag_name in (
                "cpu_overprovisioned",
                "cpu_underprovisioned",
                "memory_overprovisioned",
                "memory_underprovisioned",
            ):
                if flag_name in fail_on and flags.get(flag_name):
                    return True
    return False


def _print_summary(reports: list[dict], namespace: str) -> None:
    total_containers = sum(len(r.get("containers", [])) for r in reports)
    flagged = {k: 0 for k in _FAIL_ON_CHOICES}
    for report in reports:
        if report.get("errors"):
            flagged["config_errors"] += 1
        for container in report.get("containers", []):
            if container.get("confidence") == "LOW":
                flagged["low_confidence"] += 1
            if container.get("oom_events"):
                flagged["oom_events"] += 1
            for flag_name, value in (container.get("flags") or {}).items():
                if value:
                    flagged[flag_name] += 1

    print(f"\nnamespace={namespace}  workloads={len(reports)}  containers={total_containers}")
    for name, count in flagged.items():
        if count:
            print(f"  {name}: {count}")


def _render_markdown(reports: list[dict], namespace: str) -> str:
    lines = [f"# Resource right-sizing report -- namespace `{namespace}`", ""]
    for report in reports:
        lines.append(f"## {report['kind']}/{report['name']}")
        if report.get("errors"):
            lines.append("")
            lines.append("**Validation errors -- excluded from analysis:**")
            for err in report["errors"]:
                lines.append(f"- {err}")
            lines.append("")
            continue
        if report.get("warnings"):
            lines.append("")
            for w in report["warnings"]:
                lines.append(f"> {w}")
        lines.append("")
        lines.append("| Container | Current Request | Recommended Request | Recommended Limit | Confidence | Flags |")
        lines.append("|---|---|---|---|---|---|")
        for c in report.get("containers", []):
            if not c.get("has_metrics"):
                lines.append(f"| {c['container']} | {c['current_request']['cpu']}/{c['current_request']['memory']} | - | - | LOW | {c.get('note', '')} |")
                continue
            flags = ", ".join(k for k, v in (c.get("flags") or {}).items() if v) or "-"
            req = c["recommended_request"]
            lim = c["recommended_limit"]
            lim_str = f"{lim['cpu']}/{lim['memory']}" if lim else "-"
            lines.append(
                f"| {c['container']} | {c['current_request']['cpu']}/{c['current_request']['memory']} "
                f"| {req['cpu']}/{req['memory']} | {lim_str} | {c['confidence']} | {flags} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--kinds", nargs="+", default=k8s_client.SUPPORTED_KINDS, choices=k8s_client.SUPPORTED_KINDS)
    ap.add_argument("--prom-url", default="http://localhost:9090")
    ap.add_argument("--hours", type=float, default=168, help="Observation window, default 7 days")
    ap.add_argument("--policy-file", help="JSON file: {platformRequiresLimits, platformLimitPolicy} applied to every workload without existing limits")
    ap.add_argument("--out", default="rightsizing-report.json")
    ap.add_argument("--markdown-out")
    ap.add_argument(
        "--fail-on",
        default="",
        help=f"comma-separated flags that make this script exit non-zero for CI gating: {','.join(_FAIL_ON_CHOICES)}",
    )
    args = ap.parse_args()

    fail_on = {f.strip() for f in args.fail_on.split(",") if f.strip()}
    unknown = fail_on - set(_FAIL_ON_CHOICES)
    if unknown:
        ap.error(f"--fail-on: unknown flag(s) {sorted(unknown)}; choose from {_FAIL_ON_CHOICES}")

    policy = json.loads(Path(args.policy_file).read_text()) if args.policy_file else {}

    end = time.time()
    start = end - args.hours * 3600

    workloads = k8s_client.discover_workloads(args.namespace, args.kinds)
    hpas = k8s_client.discover_hpas(args.namespace)

    reports = []
    for workload_config in workloads:
        key = (workload_config["kind"], workload_config["name"])
        workload_config["hpa"] = hpas.get(key)
        workload_config["restartHistory"] = k8s_client.discover_restart_history(args.namespace, workload_config["name"])
        _apply_policy(workload_config, policy)

        metrics_list = [
            k8s_client.build_container_metrics(args.prom_url, args.namespace, workload_config["name"], c["name"], start, end)
            for c in workload_config["containers"]
        ]
        reports.append(analyze.analyze_workload(workload_config, metrics_list))

    Path(args.out).write_text(json.dumps(reports, indent=2))
    print(f"Wrote {args.out} covering {len(reports)} workload(s) in namespace {args.namespace}")

    if args.markdown_out:
        Path(args.markdown_out).write_text(_render_markdown(reports, args.namespace))
        print(f"Wrote {args.markdown_out}")

    _print_summary(reports, args.namespace)
    sys.exit(1 if _should_fail(reports, fail_on) else 0)


if __name__ == "__main__":
    main()
