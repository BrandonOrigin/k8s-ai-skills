# Methodology

This document explains the numbers behind a right-sizing report in plain
language, so the model can cite the exact rule it used rather than
describing its arithmetic vaguely. See `docs/specs/skill1-technical-spec.md`
for the formal spec these rules are drawn from; the implementations live in
`scripts/calc.py`.

## Analysis unit

Every number below is computed **per container name**, independently,
including sidecars and infra containers — never as a single Pod-level
figure. For a workload with multiple replicas, metrics from every replica
pod running that container are combined before any statistic is computed;
with a single replica, that combination is a no-op.

## Percentile method

CPU and memory usage percentiles (P50 and P95) are computed using **linear
interpolation** on the sorted, combined sample array — the same method
`numpy.percentile` uses by default (`method="linear"`). CPU and memory
percentiles are computed independently of each other; they are not paired
by timestamp. This method is fixed so recommendations are reproducible: a
different interpolation convention (e.g. nearest-rank) would produce
slightly different numbers from the same input.

## Sizing formulas

The recommended request is the P95 usage scaled by a safety factor:

- **CPU**: `recommended_cpu = p95_cpu_usage * 1.2`
- **Memory**: `recommended_memory = p95_memory_usage * 1.25`

These safety factors (1.2 for CPU, 1.25 for memory) are v1 defaults, not
hardcoded constants baked into formatting — they can be overridden if a
platform-specific policy calls for a different margin.

## Rounding

Rounding is applied **after** the safety factor and is always **up**,
never down:

- **CPU** rounds up to the nearest **50m** (millicores).
- **Memory** rounds up to the nearest **128Mi** if the value is below
  1Gi, or the nearest **256Mi** if it is at or above 1Gi.

Worked examples (CPU, millicores): `264m → 300m`, `310m → 350m`,
`501m → 550m`.

Worked examples (memory, binary units throughout — Mi/Gi, not decimal
MB/GB): `300Mi → 384Mi`, `700Mi → 768Mi`, `875Mi → 896Mi`,
`1.1Gi → 1.25Gi`, `1.6Gi → 1.75Gi`.

When a limit is derived from an existing request/limit ratio, the order
of operations matters: the request is rounded first, *then* the ratio is
applied, and the resulting limit is rounded using the same rounding rule
— not the other way around.

## Over/under-provisioning thresholds

These are informational flags in the Risk Assessment section, not gates
that block a recommendation:

- **CPU over-provisioned**: current request is more than **2x** the
  recommended request.
- **Memory over-provisioned**: current request is more than **1.5x** the
  recommended request, *and* memory usage is not trending up, *and* there
  have been no OOM events. (A rising trend or any OOM event suppresses
  this flag, since a large current request may be appropriate headroom
  rather than waste.)
- **CPU under-provisioned**: P95 usage exceeds **0.8x** (80%) of the
  current request.
- **Memory under-provisioned**: P95 usage exceeds **0.9x** (90%) of the
  current request, *or* there have been OOM events, *or* memory usage is
  trending up.

All four comparisons use a strict `>`, not `>=` — a current request
exactly at 2x the recommendation is not flagged as over-provisioned.

## Increasing memory trend

"Increasing" is a precise, per-pod computation, not a subjective read of a
graph:

1. For each pod instance, sort that pod's own memory samples by its own
   timestamp, then split the series at its own temporal midpoint into a
   first half and a second half.
2. Compute that pod's percentage change: `second_half_mean /
   first_half_mean - 1`.
3. Average the percentage changes across all pod instances (unweighted).
4. If the average exceeds **10%**, the trend is flagged as increasing.

Two exclusions keep this well-defined: a pod with fewer than 4 samples is
skipped (not enough points to form two meaningful halves), and a pod
whose first-half mean is exactly zero is skipped (avoids a
divide-by-zero; an idle-then-active pod is ambiguous rather than
meaningfully "increasing"). If every pod ends up excluded, the trend is
reported as not increasing, and the report's Assumptions section notes
the partial coverage rather than treating this as a silent default.

Per-pod-then-average is necessary rather than splitting the combined
multi-replica sample set, because concatenating samples from concurrent
pods (as done for the percentile calculation) does not produce a single
well-defined wall-clock midpoint once there is more than one replica —
each pod's own timeline is well-ordered, but the concatenation of several
pods' timelines is not.

## Confidence model

Confidence is computed **per container**, not once for the whole
workload — a workload can report one container as HIGH confidence and a
noisy sidecar as LOW in the same run.

**Variability** is the ratio of P95 to P50 usage (`p95 / p50`), treated
as infinite when P50 is zero (an idle container with no measurable
baseline) rather than raising a divide-by-zero error:

- ratio `<= 2` → **stable**
- ratio `<= 4` → **variable**
- ratio `> 4` (or infinite) → **highly_variable**

Overall variability for a container is the worse of its CPU and memory
ratios.

**Confidence tiers**, evaluated in this precedence order — LOW is
checked first as an override, then HIGH's stricter AND-conditions, else
MEDIUM:

- **LOW** if the observation window is under **24 hours**, or overall
  variability is `highly_variable`, or critical information is missing
  (no requests, or no metrics at all for that container) — regardless of
  how long the observation window is.
- **HIGH** only if the observation window is at least **168 hours**
  (**7 days**) *and* the workload's optional fields are all resolved
  (see "complete workload info" below) *and* overall variability is
  `stable`.
- **MEDIUM** otherwise.

"Complete workload info" means every optional field from the workload
configuration has an explicit, recorded answer — the field's *key* is
present in the payload, whether its value is `null` (confirmed absent),
`[]` (confirmed zero), or populated. A field that was simply never asked
(key absent) caps confidence at MEDIUM even if the observation window and
variability numbers would otherwise qualify for HIGH — a container
cannot reach HIGH confidence just by skipping questions.

## Platform limit policy fallback

When a container has no existing limits and the platform requires them,
but the user doesn't know the exact ratio or cap their platform enforces,
the skill falls back to a conservative default ratio rather than
guessing or blocking the report: **2.0x** the recommended request for
CPU, **1.5x** for memory. These match the over-provisioning thresholds
above by design, so a limit set at this ratio doesn't immediately flag
itself as over-provisioned. Whenever this fallback is used, the report's
Assumptions section says so explicitly.
