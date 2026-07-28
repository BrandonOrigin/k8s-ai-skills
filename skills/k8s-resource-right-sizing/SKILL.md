---
name: k8s-resource-right-sizing
description: >
  Analyze a running Kubernetes Deployment, StatefulSet, or DaemonSet using
  historical CPU/memory usage metrics and generate container-level resource
  request/limit recommendations with confidence levels. Use when a user asks
  to right-size, optimize, or reduce resource waste for an existing workload.
---

# Kubernetes Resource Right-Sizing

Full design reference: `docs/specs/skill1-technical-spec.md` (section numbers
below, e.g. "§9", refer to that document). This file is the operational
workflow; `references/methodology.md` explains the formulas in prose for
citing in a report, and `references/report-template.md` is the literal
report skeleton to fill in.

For unattended, fleet-wide scans (nightly CI/CD job, Kubernetes CronJob)
instead of an interactive conversation, see `batch/README.md` — it runs the
same `scripts/calc.py`/`scripts/schema.py` engine with zero LLM calls.

## The one rule that matters most

**Never compute percentiles, safety factors, rounding, thresholds, trend
detection, confidence, or limit policy math yourself.** Every one of those
is implemented in `scripts/calc.py` and must be invoked, not
approximated or recalculated by hand — that's the entire reason the
arithmetic lives in a script instead of the model's head (spec §2). Your
job is the conversation, the judgment calls (is a container's kind
supported, did the user actually answer a question), and writing the
final report from the template. The numbers in that report must always
be values a script call actually returned.

Invoke the scripts from a shell with the skill's root directory as the
working directory (so `scripts/` resolves as a package), e.g.:

```bash
python3 -c "
from scripts import calc
print(calc.recommended_cpu_millicores(378.5))
"
```

For anything beyond a one-off call — validating a whole workload config,
running every container through the pipeline — write a small throwaway
Python snippet that imports `calc` and `schema` and prints the results you
need, rather than chaining many separate one-line invocations.

## Conversation state machine (spec §3)

Track which state you're in explicitly; don't skip ahead on assumptions.

| State | You're here when... | Move on when... |
|---|---|---|
| `IDENTIFY_WORKLOAD` | user asked for a right-sizing analysis | kind + name + namespace are known and kind is supported |
| `COLLECT_CONFIG` | workload identified | required config fields are present, or user declines further answers |
| `COLLECT_METRICS` | config collected | required metrics present, or user declines |
| `GATE_SUFFICIENCY` | metrics collected | enough to analyze → `VALIDATE`; not enough → back to `COLLECT_METRICS` with a specific follow-up |
| `VALIDATE` | sufficiency gate passed | schema validation passes → `ANALYZE`; fails → surface errors, return to collection |
| `ANALYZE` | validated | per-container aggregation + percentiles computed |
| `RECOMMEND` | analysis complete | per-container request/limit recommendations generated |
| `IMPACT` | recommendations generated | replica-scaled totals computed |
| `REPORT` | impact computed | final Markdown report emitted |

### `IDENTIFY_WORKLOAD`

Ask for (or extract from what the user already said): workload `kind`,
`name`, `namespace`.

**Stop immediately** if `kind` is not one of `Deployment`, `StatefulSet`,
`DaemonSet` — a `Job`, `CronJob`, `VirtualMachine`, or a bare manifest with
no runtime data is out of scope. Tell the user plainly that this analysis
requires a running workload with metrics, and do not fall back to a
static-YAML review. This is a hard stop, not a soft warning.

### `COLLECT_CONFIG`

Collect the workload configuration (spec §4.1). Ask only for what you
don't already have; don't re-ask something the user already told you.

1. **Per container** (name, and required `requests.cpu` / `requests.memory`):
   ask "Does container `<name>` currently have CPU/memory limits
   configured?" If yes, record the values. If no, record `limits: null`
   (§4.1's presence convention — the key must be present either way; never
   leave it out once you've asked).
2. **HPA**: ask whether this workload has a HorizontalPodAutoscaler
   attached, and its min/max/target if so. Record `hpa: null` if the user
   confirms there isn't one.
3. **Restart history**: ask whether the workload has had OOMKilled or
   other restarts recently. Record `restartHistory: []` if the user
   confirms none, or the populated list if they describe some.
4. **Replica count**:
   - For `Deployment`/`StatefulSet`, this is `.spec.replicas` — read it
     from what the user provides, don't ask a separate question if it's
     already implied.
   - For **`DaemonSet`**, there is no `.spec.replicas` to read. Ask
     directly: "How many nodes/pods is this DaemonSet currently scheduled
     on?" If the user cannot say, **leave `replicas` unset** (key absent)
     — do not guess or infer from anything else. This is intentional:
     the Replica Impact Summary will report "not computable" instead of a
     guessed number, and it also forces this workload's confidence to
     `LOW` (see `critical_info_missing` below).
5. **Platform limit policy** (only relevant once you know at least one
   container has `limits: null`) — this is a two-step, two-question
   sequence, not one question:
   - First, if `platformRequiresLimits` hasn't been asked yet (key absent
     or `null`): ask exactly "Does your Kubernetes platform require
     resource limits? [Yes/No]" and store the boolean answer directly.
     There is no third "unknown" answer here — if the user genuinely
     doesn't know, encourage them to check rather than accepting
     ambiguity, since this field is strictly two-valued (spec §4.1/§12).
   - If the answer was **Yes** and `platformLimitPolicy` hasn't been asked
     yet: ask "What ratio or absolute cap does your platform require for
     CPU/memory limits? (e.g. '2x request', or an absolute value like
     '2000m CPU / 1Gi memory'). Reply 'not sure' if you don't know."
     - A ratio or absolute answer → `platformLimitPolicy: {"type":
       "ratio"|"absolute", "cpu": ..., "memory": ...}`.
     - "Not sure" → `platformLimitPolicy: null` (a confirmed "asked,
       doesn't know," not a skipped question).
   - If the answer was **No**: don't ask the policy question at all;
     leave `platformLimitPolicy` unset.

Validate what you've collected with `schema.validate_workload_config`
before moving on:

```bash
python3 -c "
from scripts import schema
errors = schema.validate_workload_config(workload_config)
print(errors)
"
```

An empty list means proceed; a non-empty list means go back and fix the
specific fields named in the errors — don't silently drop or reinterpret
invalid input.

### `COLLECT_METRICS`

For each container, collect (spec §4.2): `observationWindowHours`, CPU
samples (`valuesMillicores` per pod instance), memory samples
(`valuesBytes` per pod instance), and optionally `oomEvents`.

If a container in the config has no matching metrics at all, that's not a
blocking problem — proceed anyway. It will surface as a warning at
`VALIDATE` and gets its own "no metrics" treatment in the report (see
`REPORT` below), not silent omission.

### `GATE_SUFFICIENCY`

You need, at minimum, *some* CPU and memory samples for at least one
container to proceed — the PRD does not require a minimum data volume
beyond "some data exists," though less than 24 hours downgrades
confidence rather than blocking (spec §4.3, §10). If you have nothing
usable at all, ask a targeted follow-up naming exactly what's missing
rather than a generic "please provide more data."

### `VALIDATE`

Run all three validators together:

```bash
python3 -c "
from scripts import schema
errors, warnings = schema.validate_cross(workload_config, metrics_list)
print('errors:', errors)
print('warnings:', warnings)
"
```

- **Errors** (schema violations, a metrics entry for a container not in
  the config, `observationWindowHours < 1`) are rejections — go back to
  `COLLECT_CONFIG`/`COLLECT_METRICS` and fix the specific issue.
- **Warnings** (a config container with no matching metrics entry) are
  not blocking — proceed, but remember which containers triggered a
  warning; they need the "no metrics" report treatment later.

### `ANALYZE`

Per container name (spec §5.1 — every container, including sidecars,
analyzed independently; never a single Pod-level number):

```bash
python3 -c "
from scripts import calc
cpu_combined = calc.aggregate_samples(cpu_sample_lists)   # one list per pod instance
mem_combined = calc.aggregate_samples(mem_sample_lists)
print('cpu p50/p95:', calc.percentile(cpu_combined, 50), calc.percentile(cpu_combined, 95))
print('mem p50/p95:', calc.percentile(mem_combined, 50), calc.percentile(mem_combined, 95))
"
```

For a container with a warning from `VALIDATE` (no metrics at all) or
zero total samples even though a metrics entry exists: skip percentile
calculation entirely for that container — an empty combined list has no
well-defined percentile. Treat it identically to "no metrics available."

Also compute, per container, the memory trend and the four
over/under-provisioning flags once you have a recommendation (see next
section for the recommendation itself — thresholds compare current vs.
recommended, so compute them right after `RECOMMEND` for that container):

```bash
python3 -c "
from scripts import calc
trend = calc.container_memory_trend_increasing(pod_memory_series)  # list of lists of (timestamp, value)
"
```

### `RECOMMEND`

For each container with usable metrics, in this order:

1. **Size** — `calc.recommended_cpu_millicores(p95_cpu)` and
   `calc.recommended_memory_bytes(p95_mem)` (defaults: 1.2x CPU, 1.25x
   memory safety factor).
2. **Round** — `calc.round_cpu_millicores(...)` and
   `calc.round_memory_bytes(...)`, applied to the sized value from step 1.
   This is the "recommended request."
3. **Limit decision** (spec §12, run per container, per resource — CPU
   and memory can have different existing ratios):
   - If `limits` is populated (existing limits): compute
     `ratio = current_limit / current_request` per resource, then call
     `calc.round_limit_from_ratio(rounded_request, ratio, round_fn)`,
     passing `calc.round_cpu_millicores` for CPU or `calc.round_memory_bytes`
     for memory as `round_fn`.
   - If `limits` is `null` and `platformRequiresLimits` is `False`: no
     limit recommendation (requests-only). Don't call `apply_limit_policy`
     at all in this branch.
   - If `limits` is `null` and `platformRequiresLimits` is `True`: call
     `calc.apply_limit_policy(rounded_request, platformLimitPolicy, resource, round_fn)`.
     - If `platformLimitPolicy` is populated, the returned limit is
       **policy-derived** — label it that way in the report, not
       usage-derived.
     - If `platformLimitPolicy` is `null` ("not sure"), the function falls
       back to the conservative default ratio (2.0x CPU / 1.5x memory)
       and returns `used_conservative_default=True` — when that flag is
       true, add an Assumptions callout saying so explicitly.
4. **Thresholds** — now that you have the recommendation, compute
   `calc.cpu_overprovisioned`, `calc.cpu_underprovisioned`,
   `calc.memory_overprovisioned`, `calc.memory_underprovisioned` (the
   latter two need the trend flag from `ANALYZE` and whether
   `oomEvents` is non-empty).
5. **Confidence** — per container:
   - `calc.variability_ratio(p50, p95)` and `calc.variability_class(...)`
     for CPU and memory independently; overall variability is
     `calc.variability_class(max(cpu_ratio, mem_ratio))`.
   - `schema.workload_info_complete(workload_config)` — this reads the
     whole workload's key-presence checklist (§10), so it's the same
     value for every container in the workload.
   - `schema.critical_info_missing(...)` — call this **scoped to a single
     container** by passing a copy of the workload config whose
     `containers` list holds only that one container (keeping
     `replicas` and other workload-level fields intact), alongside the
     full metrics list. This is what makes confidence genuinely
     per-container: a workload with one clean container and one
     metrics-less sidecar should report mixed confidence, not force
     every container to `LOW` just because one is missing data.
   - `calc.confidence_level(observation_hours, overall_variability, workload_info_complete, critical_info_missing)`.

   Remember: confidence measures trust in the *numbers* (data volume,
   noise, completeness) — it is independent of the risk flags from step
   4. A container can be `HIGH` confidence and still have OOM events; say
   so explicitly in the report rather than letting the two look
   contradictory.

For a container with no usable metrics (warned at `VALIDATE`, or zero
samples): skip steps 1-4 entirely. Confidence is forced to `LOW`
(`critical_info_missing` will be `True` for it once scoped per-container,
which `confidence_level` treats as an override regardless of anything
else).

### `IMPACT`

Only for containers with a computable recommendation:

```text
total_current    = replicas * current_request     (rounded values from RECOMMEND)
total_recommended = replicas * recommended_request
delta = total_recommended - total_current
```

This is plain arithmetic on already-rounded numbers — no script call
needed here, but don't recompute the request/limit rounding by hand; use
the values `RECOMMEND` already produced.

If `replicas` is unset (the DaemonSet-with-no-count case), report the
impact totals as **"not computable — replica count unknown"** instead of
guessing a number. Don't average, estimate, or infer a replacement value
from anything else.

### `REPORT`

Fill in `references/report-template.md`, in order, using
`references/methodology.md` to phrase the reasoning behind each number
(percentile method, rounding convention, thresholds, trend algorithm,
confidence tiers, and the policy fallback, all documented there with the
exact constants).

A few things the template's placeholders don't spell out on their own:

- **Every container in Current Configuration gets its own Container
  Analysis subsection** — including one with no metrics. For that
  container, replace Usage Analysis and Recommendation with "No runtime
  metrics available — excluded from analysis" and force Confidence to
  `LOW`. Never omit a container's subsection; the section count must
  match the container count.
- **Replica Impact Summary** is scoped to containers with a computable
  recommendation; note explicitly which containers were excluded and why.
- **Assumptions and Missing Information are not optional boilerplate.**
  They're where validation warnings (§4.3) and confidence downgrades
  (§10) get surfaced in prose — a reader should be able to tell *why* a
  number is what it is without re-deriving it.

## Quick reference: which script function, which spec section

| Need | Function | Spec §|
|---|---|---|
| Parse/format K8s quantities | `calc.parse_cpu_quantity`, `calc.parse_memory_quantity`, `calc.format_cpu_millicores`, `calc.format_memory_bytes` | §8 |
| Percentile / multi-replica aggregation | `calc.percentile`, `calc.aggregate_samples` | §6 |
| Sizing | `calc.recommended_cpu_millicores`, `calc.recommended_memory_bytes` | §7 |
| Rounding | `calc.round_cpu_millicores`, `calc.round_memory_bytes`, `calc.round_limit_from_ratio` | §8 |
| Over/under-provisioning | `calc.cpu_overprovisioned`, `calc.memory_overprovisioned`, `calc.cpu_underprovisioned`, `calc.memory_underprovisioned` | §9 |
| Memory trend | `calc.container_memory_trend_increasing` | §9 |
| Confidence | `calc.variability_ratio`, `calc.variability_class`, `calc.confidence_level` | §10 |
| Limit policy fallback | `calc.apply_limit_policy` | §12 |
| Workload config validation | `schema.validate_workload_config` | §4.1, §4.3 |
| Metrics validation | `schema.validate_runtime_metrics` | §4.2, §4.3 |
| Cross-validation (errors vs. warnings) | `schema.validate_cross` | §4.3 |
| "Complete workload info" check | `schema.workload_info_complete` | §10 |
| Critical-info-missing check (per container, scoped) | `schema.critical_info_missing` | §10 |

See `examples/sample-input.json` and `examples/sample-report.md` for a
worked end-to-end example covering an existing-limits container, a
policy-derived limit, OOM events, a rising memory trend, and a
missing-metrics sidecar in a single scenario.
