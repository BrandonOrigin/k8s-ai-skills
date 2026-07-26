# Test Environment: k3s + Prometheus for skill1 Validation

This folder sets up a real, minimal Kubernetes environment for validating
**skill1** (`docs/PRD/skill1.md`, `docs/specs/skill1-technical-spec.md`,
`docs/plan.md` — Kubernetes Resource Right-Sizing) against live cluster data
instead of only synthetic fixtures.

skill1 needs a running workload plus **historical** CPU/memory metrics
(minimum 24h, preferred 7 days). `metrics-server` (k3s's default) only
exposes current usage, so this setup adds a lightweight Prometheus +
kube-state-metrics stack to retain history, two deliberately mis-sized
target workloads, and synthetic load generators that drive a diurnal
(day/night) traffic pattern so the resulting metrics have realistic
variability.

—

## Scenarios

| Deployment | Scenario | skill1 should flag |
|---|---|---|
| `overprovisioned-app` | Requests far more CPU/memory than it needs | CPU/memory over-provisioning |
| `underprovisioned-app` | Requests too little memory; OOMKilled during peak-hour traffic | Memory under-provisioning + OOM events |

—

## Architecture

```mermaid
flowchart LR
    LG1["overprovisioned-\nload-generator"] -->|"moderate,\nsteady traffic"| SVC1["overprovisioned-app\n(Service)"]
    SVC1 --> APP1["overprovisioned-app\n(app + log-agent)"]

    LG2["underprovisioned-\nload-generator"] -->|"peak-hour\nconcurrent burst"| SVC2["underprovisioned-app\n(Service)"]
    SVC2 --> APP2["underprovisioned-app\n(app, OOMKilled at peak)"]

    APP1 -->|cAdvisor / kubelet| Prom[Prometheus]
    APP2 -->|cAdvisor / kubelet| Prom
    KSM[kube-state-metrics] --> Prom
    NE[node-exporter] --> Prom
    Prom -->|"PromQL /\nquery_range API"| Extract["scripts/extract_metrics.py"]
    Extract --> Out["*-runtime-metrics.json"]
```

—

## Steps

| # | Doc | What it does | Est. time |
|---|---|---|---|
| 1 | [01-provision-server.md](01-provision-server.md) | Size and prep a 2 vCPU Ubuntu server | 15 min |
| 2 | [02-install-k3s.md](02-install-k3s.md) | Install a lightweight k3s | 10 min |
| 3 | [03-install-monitoring-stack.md](03-install-monitoring-stack.md) | Install Prometheus + kube-state-metrics (no Grafana/Alertmanager) | 15 min |
| 4 | [04-deploy-target-workloads.md](04-deploy-target-workloads.md) | Deploy both scenario workloads (mis-sized on purpose) | 10 min |
| 5 | [05-deploy-synthetic-load-generators.md](05-deploy-synthetic-load-generators.md) | Deploy traffic that drives realistic, time-varying usage — and triggers the OOMKill scenario at peak hours | 10 min |
| — | **Wait** | Let 5 run continuously | ≥24h, ideally 7 days |
| 6 | [06-collect-metrics-for-skill1.md](06-collect-metrics-for-skill1.md) | Pull the accumulated history into skill1's input JSON shape, for both workloads | 15 min |

Reusable Kubernetes manifests live in `manifests/`; the metrics extractor
lives in `scripts/extract_metrics.py` (stdlib-only, no pip installs needed).

—

## Prerequisites

- A server with **2 vCPU / 4GB RAM minimum**, Ubuntu 22.04 LTS. RAM is the
  tighter constraint of the two once Prometheus is running — see
  `01-provision-server.md` for a lower-memory fallback.
- `kubectl` and `helm` on whichever machine you'll drive the cluster from
  (can be the server itself, or your laptop once kubeconfig is copied over —
  see `02-install-k3s.md`).
- SSH access to the server.

—

## What you end up with

For each of `overprovisioned-app` and `underprovisioned-app`:

- A `<workload>-runtime-metrics.json` file (per-container CPU/memory sample
  series + OOM events, matching spec §4.2) covering whatever observation
  window you waited for.
- A hand-assembled `<workload>-workload-config.json` (spec §4.1 shape)
  built from `kubectl get deployment` output — shown in step 6.

Each pair is exactly the two inputs skill1's `VALIDATE` state expects (spec
§3), so once `skills/k8s-resource-right-sizing/` exists (per
`docs/plan.md`) you can paste them straight into a conversation invoking
it — once per scenario.

—

## Cost note

Step 1 provisions a real cloud VM that then runs continuously for up to 7
days (step 5's wait). Remember to stop or delete it once you've captured
`skill1-runtime-metrics.json` in step 6 — nothing in this folder tears it
down automatically.
