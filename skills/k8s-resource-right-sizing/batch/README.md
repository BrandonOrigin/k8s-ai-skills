# Batch Right-Sizing Scan (no LLM)

This is the unattended, CI/CD-friendly companion to the
[`k8s-resource-right-sizing`](../SKILL.md) Skill. It scans every
Deployment/StatefulSet/DaemonSet in a namespace, pulls historical CPU/memory
usage from Prometheus, and runs it through the **exact same deterministic
engine** (`../scripts/calc.py`, `../scripts/schema.py`) the interactive Skill
uses — percentile sizing, safety factors, rounding, over/under-provisioning
thresholds, memory-trend detection, confidence scoring, limit-policy
application. **No LLM call happens anywhere in this path.**

## Why this exists alongside the Skill

The interactive Skill's LLM never does arithmetic either — that's the whole
point of `calc.py`/`schema.py`. What it *does* spend tokens on is
conversation: asking follow-up questions, making judgment calls, and writing
prose. That's valuable for a human investigating one workload interactively,
but wasteful (and slow) if you want to scan every namespace in a large
fleet every night.

| | Interactive Skill | This batch script |
|---|---|---|
| Cost per workload | LLM tokens + latency | ~free (pure Python + one Prometheus query) |
| Best for | One-off, ambiguous, or narrated analysis; a human is in the loop | Scheduled, fleet-wide scans; CI/CD gating |
| Handles missing/ambiguous input by | Asking a follow-up question | Degrading confidence or excluding the container — never guessing |
| Output | Narrated Markdown report | Structured JSON (+ optional Markdown table) |

Use this script for routine, high-volume scanning, and reserve the Skill for
the workloads it flags that a human wants explained or where the platform's
limit policy needs to be resolved conversationally (see
[Escalating to the Skill](#escalating-to-the-interactive-skill) below).

## Prerequisites

- Python 3.10+
- `kubectl`, already configured against the target cluster with read access
  to `deployments`, `statefulsets`, `daemonsets`, `horizontalpodautoscalers`,
  and `pods` in the namespaces you scan. [`rbac/`](rbac/) has a ready-made
  `ClusterRole` (plus a single-namespace `Role` alternative) covering
  exactly this.
- A reachable Prometheus URL exposing `container_cpu_usage_seconds_total`,
  `container_memory_working_set_bytes`, and
  `kube_pod_container_status_last_terminated_reason` (the same metrics
  `../../test/` stands up via kube-state-metrics/node-exporter/cAdvisor for
  manual Skill testing).
- `pip install -r requirements.txt` (just `jsonschema` — everything else is
  stdlib).

## Quick start

```bash
cd skills/k8s-resource-right-sizing/batch
pip install -r requirements.txt

kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &

python3 rightsize_batch.py \
  --namespace prod \
  --hours 168 \
  --out rightsizing-report.json \
  --markdown-out rightsizing-report.md
```

This writes a JSON report and a human-readable Markdown table for every
container in every Deployment/StatefulSet/DaemonSet in `prod`, and prints a
one-line-per-flag summary to stdout.

## CLI reference

| Flag | Default | Meaning |
|---|---|---|
| `--namespace` | *(required)* | Namespace to scan |
| `--kinds` | all three | Subset of `deployment statefulset daemonset` |
| `--prom-url` | `http://localhost:9090` | Prometheus base URL |
| `--hours` | `168` (7 days) | Observation window; spec §10 penalizes confidence below 24h rather than rejecting |
| `--policy-file` | *(none)* | JSON file supplying `platformRequiresLimits`/`platformLimitPolicy` (see below) |
| `--out` | `rightsizing-report.json` | Structured JSON report path |
| `--markdown-out` | *(none)* | Optional human-readable Markdown summary path |
| `--fail-on` | *(none — always exits 0)* | Comma-separated flags that make the process exit `1`, for CI gating |

`--fail-on` accepts any of: `cpu_overprovisioned`, `cpu_underprovisioned`,
`memory_overprovisioned`, `memory_underprovisioned`, `oom_events`,
`low_confidence`, `config_errors`.

## Policy file

`platformRequiresLimits` and `platformLimitPolicy` (spec §12) are
organizational policy questions, not cluster state — kubectl can't answer
them, so the interactive Skill asks a human. In batch mode, supply them
explicitly:

```json
{
  "platformRequiresLimits": true,
  "platformLimitPolicy": { "type": "ratio", "cpu": 2.0, "memory": 1.5 }
}
```

Applied to every scanned workload that doesn't already have container
limits set. Omit `--policy-file` entirely and the script leaves the
question unresolved (matching the Skill's "never asked" state) — every
container's confidence is then capped at `MEDIUM` rather than reaching
`HIGH`, which is the honest outcome, not a bug.

## Output format

`--out` is a JSON array, one entry per workload:

```json
[
  {
    "kind": "Deployment",
    "name": "checkout-service",
    "namespace": "prod",
    "replicas": 3,
    "errors": [],
    "warnings": [],
    "containers": [
      {
        "container": "web",
        "current_request": { "cpu": "500m", "memory": "512Mi" },
        "has_metrics": true,
        "usage": {
          "cpu_p50_millicores": 305.0,
          "cpu_p95_millicores": 378.5,
          "memory_p50_bytes": 283115520.0,
          "memory_p95_bytes": 333971456.0
        },
        "recommended_request": { "cpu": "500m", "memory": "512Mi" },
        "recommended_limit": { "cpu": "1000m", "memory": "1Gi" },
        "limit_source": "existing-ratio",
        "flags": {
          "cpu_overprovisioned": false,
          "cpu_underprovisioned": false,
          "memory_overprovisioned": false,
          "memory_underprovisioned": false
        },
        "increasing_memory_trend": false,
        "oom_events": false,
        "confidence": "HIGH",
        "impact": {
          "current_total_cpu_millicores": 1500,
          "recommended_total_cpu_millicores": 1500,
          "current_total_memory_bytes": 1610612736,
          "recommended_total_memory_bytes": 1610612736
        }
      }
    ]
  }
]
```

A workload with schema validation errors (`errors` non-empty) has
`containers: []` — nothing about it was analyzed, matching the Skill's
`VALIDATE` state, which rejects rather than guesses. A container with no
matching Prometheus data gets `has_metrics: false`, `confidence: "LOW"`,
and no recommendation, instead of being silently skipped.

## CI/CD integration

### GitHub Actions (scheduled nightly scan)

```yaml
name: k8s-rightsizing-scan
on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch: {}

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Configure kubectl
        run: |
          echo "${{ secrets.KUBECONFIG_B64 }}" | base64 -d > kubeconfig
          echo "KUBECONFIG=$PWD/kubeconfig" >> "$GITHUB_ENV"
      - name: Install dependencies
        run: pip install -r skills/k8s-resource-right-sizing/batch/requirements.txt
      - name: Run batch scan
        working-directory: skills/k8s-resource-right-sizing/batch
        run: |
          python3 rightsize_batch.py \
            --namespace prod \
            --prom-url "${{ secrets.PROMETHEUS_URL }}" \
            --hours 168 \
            --out rightsizing-report.json \
            --markdown-out rightsizing-report.md \
            --fail-on memory_underprovisioned,oom_events,config_errors
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: rightsizing-report
          path: skills/k8s-resource-right-sizing/batch/rightsizing-report.*
```

The `--fail-on` list above fails the job only on things that matter for a
gate (active under-provisioning and OOM risk) — over-provisioning is
informational, surfaced in the artifact for review rather than blocking CI.
Adjust to your team's risk tolerance.

### GitLab CI

```yaml
rightsizing-scan:
  image: python:3.12-slim
  stage: test
  before_script:
    - apt-get update && apt-get install -y curl
    - curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    - install kubectl /usr/local/bin/kubectl
    - pip install -r skills/k8s-resource-right-sizing/batch/requirements.txt
  script:
    - cd skills/k8s-resource-right-sizing/batch
    - python3 rightsize_batch.py --namespace prod --prom-url "$PROMETHEUS_URL"
        --out rightsizing-report.json --markdown-out rightsizing-report.md
        --fail-on memory_underprovisioned,oom_events,config_errors
  artifacts:
    when: always
    paths:
      - skills/k8s-resource-right-sizing/batch/rightsizing-report.*
  rules:
    - if: '$CI_PIPELINE_SOURCE == "schedule"'
```

### In-cluster CronJob (no external CI runner needed)

For a company already running a lot on Kubernetes, running the scan as a
`CronJob` avoids relying on an external CI runner having cluster access at
all — it uses a `ServiceAccount` with read-only RBAC instead. Apply
[`rbac/`](rbac/) first (`ClusterRole` + `ServiceAccount` +
`ClusterRoleBinding`, or the single-namespace `Role` variant — see
[`rbac/README.md`](rbac/README.md)) to create `rightsizing-scanner`:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: k8s-rightsizing-scan
  namespace: platform-tools
spec:
  schedule: "0 6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: rightsizing-scanner   # bound to a read-only ClusterRole
          restartPolicy: OnFailure
          containers:
            - name: scan
              image: python:3.12-slim
              command: ["/bin/sh", "-c"]
              args:
                - |
                  pip install -q -r batch/requirements.txt &&
                  python3 batch/rightsize_batch.py --namespace prod \
                    --prom-url http://kube-prometheus-stack-prometheus.monitoring:9090 \
                    --out /reports/rightsizing-report.json
              volumeMounts:
                - name: repo
                  mountPath: /repo
                - name: reports
                  mountPath: /reports
          volumes:
            - name: repo
              # mount the repo (e.g. via an init container that clones it,
              # or bake it into a purpose-built image) and a PVC/object-store
              # sink for reports
            - name: reports
              emptyDir: {}
```

Bake this into a small custom image with the repo checked out and
`kubectl`'s RBAC narrowed to `get`/`list` on the relevant resources, rather
than mounting a live clone, for a production setup.

## Testing

The analysis logic (`analyze.py`) is pure — no cluster or Prometheus needed
to test it:

```bash
cd skills/k8s-resource-right-sizing
python3 -m pytest batch/tests/ -v
```

It's kept in a separate `pytest` invocation from `tests/` (the interactive
Skill's suite) rather than one combined run, matching how every verify
command in `../../docs/plan.md` already scopes `pytest` per package.

## Known limitations (read before trusting this in production)

Being unattended costs it some of what the conversation buys the Skill:

- **HPA and restart-history discovery are best-effort, not "confirmed."**
  `discover_hpas`/`discover_restart_history` reflect whatever `kubectl`
  currently sees — an HPA that doesn't match `scaleTargetRef` exactly, or a
  pod that was already recycled, won't show up. The interactive Skill's
  `null`/`[]` states mean a human explicitly confirmed absence; this
  script's mean "not found by this query," which is weaker.
- **Without `--policy-file`, confidence never reaches `HIGH`.** That's
  intentional (spec §10 requires `workload_info_complete`), not a defect —
  but it means a batch-only pipeline will rarely see `HIGH` unless you
  supply the policy file.
- **A container with a limit but no matching request** (rare — Kubernetes
  normally defaults the request to the limit on admission) is treated as
  requests-only rather than computing a ratio, to avoid a divide-by-zero;
  it won't get a recommended limit in that edge case.
- **No natural-language explanation.** The Markdown output is a table, not
  a narrated report — if a developer wants to know *why* a number is what
  it is, or push back on an assumption, that's a job for the Skill.

## Escalating to the interactive Skill

When this scan flags something that needs a human conversation — an
ambiguous `platformLimitPolicy`, a container the batch run couldn't reach
`HIGH` confidence on, or a developer who wants the reasoning spelled out —
paste the relevant entry from `rightsizing-report.json` (or the raw
workload config + Prometheus data, per `../SKILL.md`) into a Claude Code
conversation invoking the `k8s-resource-right-sizing` Skill. It runs the
same `calc.py`/`schema.py` engine, so the numbers will match; what you get
in addition is the conversation and the narrated report.
