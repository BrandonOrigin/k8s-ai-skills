# Resource Right-Sizing Report: Deployment/checkout-service (prod)

This report is generated from `examples/sample-input.json` and follows the
structure in `references/report-template.md`. Every numeric value below
matches the corresponding computation in `tests/test_scenarios.py`.

## Executive Summary

- Containers analyzed: 3 (2 with usage data, 1 excluded for missing metrics)
- Headline change: **+13.3% CPU / +16.7% memory** across replicas — this is
  a net *increase*, not a saving
- Overall risk level: **Medium** (one container is under-provisioned with
  recent OOM events)

`web` is already sized correctly and needs no change. `worker` is
under-provisioned — its CPU and memory requests should increase to close
the gap that is currently causing OOM kills. `log-shipper` has no runtime
metrics and is excluded from analysis. Right-sizing isn't only about
finding waste to cut; here it correctly identifies a container that needs
*more* headroom.

## Current Configuration

| Field | Value |
|---|---|
| Kind | Deployment |
| Name | checkout-service |
| Namespace | prod |
| Replicas | 3 |

| Container | CPU Request | Memory Request | CPU Limit | Memory Limit |
|---|---|---|---|---|
| web | 500m | 512Mi | 1 (1000m) | 1Gi |
| worker | 250m | 256Mi | none | none |
| log-shipper | 50m | 64Mi | none | none |

## Container Analysis

### web

**Current Resources**

- Request: 500m CPU / 512Mi memory
- Limit: 1000m CPU / 1Gi memory

**Usage Analysis**

- CPU: P50 305m, P95 378.5m, variability stable (P95/P50 ≈ 1.24)
- Memory: P50 270Mi, P95 318.5Mi, variability stable (P95/P50 ≈ 1.18)

**Recommendation**

- Request: 500m CPU / 512Mi memory (unchanged — already correctly sized)
- Limit: 1000m CPU / 1Gi memory (existing 2x ratio applied to the
  recommended request)

**Confidence**

HIGH — 7 days of data (168h), stable variability, and complete workload
info (limits, HPA, restart history, and platform limit policy all
resolved).

### worker

**Current Resources**

- Request: 250m CPU / 256Mi memory
- Limit: none configured

**Usage Analysis**

- CPU: P50 205m, P95 254.25m, variability stable (P95/P50 ≈ 1.24)
- Memory: P50 212.5Mi, P95 240Mi, variability stable (P95/P50 ≈ 1.13)
- Memory usage is trending up (>10% average rise across replica pods)

**Recommendation**

- Request: 350m CPU / 384Mi memory (increase from current — see Risk
  Assessment)
- Limit: 700m CPU / 640Mi memory (platform limit policy: 2.0x CPU / 1.5x
  memory ratio, policy-derived — not a fallback default)

**Confidence**

HIGH — 7 days of data (168h), stable variability, and complete workload
info. Note: confidence measures trust in the *numbers* (enough data, low
noise, all questions answered) — it is independent of the operational
risk flagged below. A container can be HIGH confidence and still need
urgent attention.

### log-shipper

**Current Resources**

- Request: 50m CPU / 64Mi memory
- Limit: none configured

**Usage Analysis / Recommendation**

No runtime metrics available — excluded from analysis.

**Confidence**

LOW — no runtime metrics available for this container.

## Replica Impact Summary

Scoped to the two containers with a computable recommendation (`web`,
`worker`); `log-shipper` has no recommendation to scale and is tracked
separately under Missing Information.

| Metric | Current (total, 3 replicas) | Recommended (total, 3 replicas) | Delta |
|---|---|---|---|
| CPU | 2250m | 2550m | +300m (+13.3%) |
| Memory | 2.25Gi | 2.625Gi | +384Mi (+16.7%) |

## Resource Limit Analysis

- **web**: existing limit ratio — CPU 2.0x, memory 2.0x — applied to the
  recommended request → 1000m CPU / 1Gi memory.
- **worker**: no existing limits; platform requires limits and supplied a
  policy (2.0x CPU / 1.5x memory ratio) → limit is **policy-derived**, not
  usage-derived: 700m CPU / 640Mi memory.
- **log-shipper**: no existing limits; not applicable — excluded from
  analysis (no runtime metrics to derive a request from).

## Estimated Resource Savings

- CPU: no savings — `web` is unchanged, `worker` needs a **100m increase**
  per replica instance (workload-level: +300m, +13.3%)
- Memory: no savings — `web` is unchanged, `worker` needs a **128Mi
  increase** per replica instance (workload-level: +384Mi, +16.7%)

No over-provisioning was found in this workload, so there are no savings
to report — the recommendation is a net increase to fix `worker`'s
under-provisioning.

## Risk Assessment

| Container | Over-provisioned | Under-provisioned | OOM history |
|---|---|---|---|
| web | No | No | 0 events |
| worker | No | **Yes (CPU and memory)** | **2 events** |
| log-shipper | N/A — excluded | N/A — excluded | 0 events |

`worker`'s memory usage is trending upward and it has 2 recorded OOM
events in the observation window, consistent with `restartHistory`
reporting 2 OOMKilled restarts for this container. Its memory
recommendation increase (256Mi → 384Mi) directly addresses this.

## Assumptions

- Percentile method: linear interpolation (spec §6), computed
  independently for CPU and memory.
- Rounding convention: CPU rounds up to the nearest 50m; memory rounds up
  to the nearest 128Mi below 1Gi, or 256Mi at or above 1Gi.
- Platform overrides applied: `worker`'s limit used the platform-supplied
  policy (2.0x CPU / 1.5x memory) — this happens to match the built-in
  conservative-default ratio, but it was explicitly provided by the
  platform, not a fallback (`platformLimitPolicy` was populated, not
  `null`).
- No safety-factor overrides were applied to `web`; default safety
  factors (1.2x CPU, 1.25x memory) were used throughout.
- Confidence reflects data volume, variability, and completeness of the
  workload questionnaire — not current operational risk. See Risk
  Assessment for `worker`'s OOM/trend flags, which coexist with its HIGH
  confidence rating.

## Missing Information

- Containers with no runtime metrics: **log-shipper** — excluded from
  recommendations and Replica Impact Summary; confidence forced to LOW.
- Fields the user declined to provide: none — `hpa` (confirmed none),
  `restartHistory` (populated), and `platformRequiresLimits` /
  `platformLimitPolicy` (both resolved) were all explicitly answered.
- How missing information lowered confidence: `log-shipper`'s missing
  metrics is the only gap in this workload, and it affects only that
  container's confidence (forced LOW) — it does not lower confidence for
  `web` or `worker`, whose own information is complete.
