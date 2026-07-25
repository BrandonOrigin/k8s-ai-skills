# Technical Spec: Kubernetes Resource Right-Sizing Recommendation Skill

Source PRD: `docs/PRD/skill1.md`

—

## 1. Purpose

This document translates the skill1 PRD into an implementable design for a Claude Code Skill: package layout, data contracts, algorithms, control flow, and validation rules. It is the reference for building `skills/k8s-resource-right-sizing/`.

—

## 2. Skill Package Layout

Claude Code Skills are discovered via a `SKILL.md` file with YAML frontmatter, plus optional bundled scripts and reference material (progressive disclosure — the model reads `SKILL.md` first and pulls in other files only as needed).

```text
skills/k8s-resource-right-sizing/
  SKILL.md                     # frontmatter + workflow instructions (entry point)
  references/
    methodology.md             # sizing formulas, rounding rules, thresholds (Sections 7-10 below)
    report-template.md          # Markdown report skeleton (Section 11)
  scripts/
    calc.py                    # deterministic math: percentiles, safety factors, rounding, thresholds
    schema.py                  # input validation (jsonschema) for workload config + metrics
  examples/
    sample-input.json
    sample-report.md
```

**Frontmatter (`SKILL.md`):**

```yaml
---
name: k8s-resource-right-sizing
description: >
  Analyze a running Kubernetes Deployment, StatefulSet, or DaemonSet using
  historical CPU/memory usage metrics and generate container-level resource
  request/limit recommendations with confidence levels. Use when a user asks
  to right-size, optimize, or reduce resource waste for an existing workload.
---
```

Rationale for putting the arithmetic in `scripts/calc.py` rather than leaving it to the model: percentile math, rounding, and threshold comparisons are exact and repeatable — they should not depend on model arithmetic. The model's job is conversation, data collection, judgment calls (e.g., is a trend "increasing"), and report authoring; the script's job is the numbers that feed into it.

—

## 3. Conversation State Machine

Maps the PRD's Mermaid flow (PRD §"Interactive Workflow") onto explicit states the model tracks during the conversation.

| State | Entry condition | Exit condition |
|---|---|---|
| `IDENTIFY_WORKLOAD` | User requests analysis | Workload kind + name + namespace known, and kind ∈ {Deployment, StatefulSet, DaemonSet} |
| `COLLECT_CONFIG` | Workload identified | Required config fields present (§4.1) or user declines to provide more |
| `COLLECT_METRICS` | Config collected | Required metrics present (§4.2) or user declines |
| `GATE_SUFFICIENCY` | Metrics collected | Route: enough → `VALIDATE`; not enough → back to `COLLECT_METRICS` with a targeted question |
| `VALIDATE` | Sufficiency gate passed | Data passes schema validation (§4.3) or fails → surface errors, return to collection |
| `ANALYZE` | Validated | Per-container metrics aggregated and percentiles computed (§6) |
| `RECOMMEND` | Analysis complete | Per-container request/limit recommendations generated (§7-10) |
| `IMPACT` | Recommendations generated | Replica-scaled totals computed (§5.2) |
| `REPORT` | Impact computed | Final Markdown report emitted (§11) |

If the workload kind is unsupported (Job, CronJob, VirtualMachine, or a bare manifest with no runtime data), the skill must stop at `IDENTIFY_WORKLOAD` and tell the user this analysis requires a running workload with metrics, per PRD §"Not Supported" — it must not silently fall back to a static-YAML review.

—

## 4. Data Contracts

### 4.1 Workload Configuration (input)

```json
{
  "kind": "Deployment | StatefulSet | DaemonSet",
  "name": "string",
  "namespace": "string",
  "replicas": "integer >= 1",
  "containers": [
    {
      "name": "string",
      "requests": { "cpu": "string (K8s quantity)", "memory": "string (K8s quantity)" },
      "limits":   { "cpu": "string (K8s quantity)", "memory": "string (K8s quantity)" }
    }
  ],
  "hpa": { "min": "int", "max": "int", "targetCPUUtilization": "int" } | null,
  "restartHistory": [{ "container": "string", "reason": "OOMKilled | Error | ...", "count": "int" }],
  "platformRequiresLimits": "boolean | null",
  "platformLimitPolicy": { "type": "ratio | absolute", "cpu": "number | K8s quantity", "memory": "number | K8s quantity" } | null
}
```

`containers[].requests.{cpu,memory}` is **required** per container. `limits`, `hpa`, `restartHistory`, `platformRequiresLimits`, and `platformLimitPolicy` are optional (PRD §"Workload Configuration"); see §12 for how `platformRequiresLimits`/`platformLimitPolicy` are populated. Every optional field must be set to an explicit value or explicit `null`/"confirmed absent" — the model must not leave a field simply unasked, per the completeness rule in §10.

**`platformRequiresLimits` (resolved):** a two-valued question, not three — the model asks "Does your Kubernetes platform require resource limits? [Yes/No]" and stores the boolean answer directly in this field. `null` means the question hasn't been asked yet (an unresolved state the completeness checklist in §10 can detect), not a third answer choice; there is no "Unknown" response the user can give. `platformLimitPolicy` (the ratio/cap itself) is a separate field, only relevant when `platformRequiresLimits == true` — see §12.

**DaemonSet replicas (resolved, was open in §13):** the model asks the user directly — "How many nodes/pods is this DaemonSet currently scheduled on?" — rather than reading `.spec.replicas` (which doesn't exist) or inferring from cluster state the skill has no access to. If the user cannot provide it, `replicas` is left unset, the Replica Impact Summary (§11) reports totals as "not computable — replica count unknown" instead of guessing, and this counts as missing critical info, forcing per-container confidence to `LOW` (§10).

### 4.2 Runtime Metrics (input, per container)

```json
{
  "container": "string",
  "observationWindowHours": "number",
  "cpu": { "samples": [{ "podName": "string", "timestampSeries": "...", "valuesMillicores": [number, ...] }] },
  "memory": { "samples": [{ "podName": "string", "timestampSeries": "...", "valuesBytes": [number, ...] }] },
  "oomEvents": [{ "podName": "string", "timestamp": "string" }]
}
```

Required: `cpu.samples`, `memory.samples`, `observationWindowHours` (used directly for the confidence model, §10). `oomEvents` is optional but feeds under-provisioning detection (§9) and the memory over-provisioning exclusion (§8).

### 4.3 Validation Rules

- Reject if `containers` is empty or any container is missing `requests.cpu`/`requests.memory`.
- Reject if a metrics sample set exists for a container name not present in `containers` (mismatch — likely wrong workload).
- Reject if `observationWindowHours < 1` (not just below the 24h "minimum acceptable" — that's a confidence penalty, not a hard failure; PRD only hard-requires *some* data).
- Warn (do not reject) if a container present in `containers` has no matching metrics — that container is reported under "Missing Information" (§11) and excluded from recommendations, not silently dropped from the report.

—

## 5. Analysis Unit & Replica Handling

### 5.1 Container-level analysis (PRD §"Analysis Unit")

Every computation in §6-10 runs **per container name**, independently, including sidecars and infra containers. The skill must never emit a single Pod-level number as if it were a recommendation.

### 5.2 Replica semantics (PRD §"Replica Handling")

Two distinct computations, not to be conflated:

1. **Per-container recommendation** — computed from aggregated *per-instance* usage (§6.1). Independent of replica count by construction, because aggregation happens before the percentile, not after.
2. **Workload impact** — `totalCurrent = replicas × currentRequest`, `totalRecommended = replicas × recommendedRequest`, reported as absolute and percentage delta. This is purely arithmetic on the already-rounded per-container recommendation from §9-10, computed once at the `IMPACT` state.

—

## 6. Multi-Replica Metrics Aggregation

Per PRD §"Multi-replica Metrics Aggregation":

```text
for each container name:
    combined_samples = concat(samples from every pod instance of that container)
    p50 = percentile(combined_samples, 50)
    p95 = percentile(combined_samples, 95)
```

- If `replicas == 1`, aggregation is a no-op (single sample set) — this is the one case where per-Pod == the aggregate, consistent with PRD's "should not calculate recommendations based on a single Pod unless only one replica exists."
- Percentile method: linear interpolation on the sorted sample array (standard nearest-rank alternative is acceptable but must be fixed and documented — implementation should pick one, e.g. `numpy.percentile` default `linear`, and use it consistently for P50 and P95 and for both resources).
- CPU and memory percentiles are computed independently; they are not correlated/paired by timestamp for this version.

—

## 7. Sizing Formulas

Implemented as pure functions in `scripts/calc.py`, taking `p95_usage` and returning the pre-rounding recommendation (PRD §"CPU Recommendation" / §"Memory Recommendation"):

```python
CPU_SAFETY_FACTOR = 1.2
MEMORY_SAFETY_FACTOR = 1.25

def recommended_cpu_millicores(p95_cpu_millicores: float) -> float:
    return p95_cpu_millicores * CPU_SAFETY_FACTOR

def recommended_memory_bytes(p95_memory_bytes: float) -> float:
    return p95_memory_bytes * MEMORY_SAFETY_FACTOR
```

Safety factors are constants for v1 but must be exposed as parameters (not hardcoded inline in formatting logic) so a platform override (§7.4 below / PRD §"Platform Override") can pass different values without code changes.

—

## 8. Rounding

Applied **after** the safety factor, **before** limit-ratio math (PRD §"Recommendation Rounding": "the ratio is applied to the rounded request, and the resulting limit is then rounded using the same rules"). Rounding is always up, never down.

```python
def round_cpu_millicores(m: float) -> int:
    return ceil(m / 50) * 50

def round_memory_bytes(b: float) -> int:
    GiB = 1024**3
    if b < GiB:
        step = 128 * 1024**2  # 128Mi
    else:
        step = 256 * 1024**2  # 256Mi
    return ceil(b / step) * step
```

Order of operations for a limit derived from an existing ratio:

```text
rounded_request = round(p95 * safety_factor)
limit = rounded_request * existing_ratio      # ratio = current_limit / current_request
recommended_limit = round(limit)                # same rounding function as the request
```

Verify against PRD worked examples as unit test fixtures: `264m→300m`, `310m→350m`, `501m→550m`; `300Mi→384Mi`, `700Mi→768Mi`, `875Mi→896Mi`; `1.1Gi→1.25Gi`, `1.6Gi→1.75Gi`. Note the memory examples mix binary (Mi/Gi) units throughout — the implementation must use binary (1024-based) units end to end, not decimal (1000-based) MB/GB, to reproduce these exact figures.

A platform-override hook (config dict passed into `calc.py`) allows substituting different step sizes or a decimal-unit convention without touching the core algorithm.

—

## 9. Over/Under-Provisioning Detection

Pure boolean checks per container per resource, evaluated after §6-8 produce a recommendation (PRD §"Recommendation Thresholds"):

```python
cpu_overprovisioned    = current_cpu_request    > recommended_cpu_request * 2
memory_overprovisioned = (current_memory_request > recommended_memory_request * 1.5
                           and not increasing_memory_trend
                           and not any_oom_events)
cpu_underprovisioned    = p95_cpu_usage    > current_cpu_request * 0.8
memory_underprovisioned = (p95_memory_usage > current_memory_request * 0.9
                            or any_oom_events
                            or increasing_memory_trend)
```

**`increasing_memory_trend` (resolved, was open in §13):** the PRD leaves this qualitative. Default: split the combined memory sample series at its temporal midpoint, compute the mean of each half, and flag "increasing" if `second_half_mean > first_half_mean × 1.10` (a >10% rise). This is chosen over a regression slope because it's simpler to explain in the report ("usage in the second half of the window averaged X% higher than the first half"), it's insensitive to reordering artifacts across concatenated multi-replica samples, and it avoids over-fitting noise on short or sparse windows where a slope+R² test is unreliable. Document this formula verbatim in `references/methodology.md` so the report's "Assumptions" section can cite it precisely.

These flags feed the "Risk Assessment" report section (§11) — they are informational, not gates that block a recommendation from being generated.

—

## 10. Confidence Model

Per PRD §"Confidence Model":

```python
def variability_ratio(p50, p95):
    return p95 / p50 if p50 > 0 else float("inf")

def variability_class(ratio):
    if ratio <= 2: return "stable"
    if ratio <= 4: return "variable"
    return "highly_variable"

# overall variability = worse of CPU and memory ratios
overall_variability = variability_class(max(cpu_ratio, mem_ratio))
```

Confidence per container:

```text
LOW    if observation_hours < 24
       or overall_variability == "highly_variable"
       or critical info missing (no requests, no metrics for that container)

HIGH   if observation_hours >= 168 (7 days)
       and complete workload info (see fixed checklist below)
       and overall_variability == "stable"

MEDIUM otherwise
```

Evaluate `LOW` conditions first (highest precedence — any one trips it regardless of the others), then `HIGH` (all conditions must hold), else `MEDIUM`. This matches the PRD's ordering (Low is checked as an override — "regardless of observation period length" — before High's stricter AND-conditions apply).

**"Complete workload info" (resolved, was open in §13):** defining this as "whatever fields were actually requested" is circular — it would let the model reach HIGH confidence just by not asking. Instead, "complete" means every optional field in §4.1 has an **explicit answer on record**, not merely a populated value:

- `limits` — either present, or the user has confirmed no limits are configured (not simply "not mentioned").
- `hpa` — either present, or the user has confirmed no HPA is configured.
- `restartHistory` — the model has explicitly asked about restarts/OOM events and recorded the answer (even if "none").
- `platformRequiresLimits` — a definite Yes/No on record (§4.1); and if Yes, `platformLimitPolicy` has either a policy value or an explicit "not sure" (the conservative-ratio fallback in §12) — either counts as resolved for completeness purposes, since "not sure" is a recorded answer, not a skipped question.

If any of these was simply never asked, confidence caps at `MEDIUM` even if the numeric criteria (7 days, stable variability) are met. This makes HIGH confidence a function of what was verified, not what was skipped.

`p50 == 0` (idle container with zero usage in some samples) must not raise a `ZeroDivisionError` — treat ratio as `inf` → `highly_variable` → forces `LOW` confidence, which is the conservative and correct outcome for a container with no measurable baseline.

Confidence is computed **per container**, not once for the whole workload — a workload with one stable container and one highly-variable sidecar reports mixed confidence, matching the per-container analysis unit (§5.1).

—

## 11. Output Report

Structure fixed by PRD §"Expected Output"; `references/report-template.md` holds the literal Markdown skeleton with placeholders for:

- Executive Summary — total containers analyzed, headline savings %, overall risk level.
- Current Configuration — table of kind/name/namespace/replicas/containers.
- Container Analysis (repeated per container, **including containers with no metrics** — resolved, was open in §13) — Current Resources, Usage Analysis (P50/P95/variability), Recommendation (request + limit if applicable), Confidence (+ one-line reason). A container present in the workload config but missing metrics still gets its own subsection, with Usage Analysis and Recommendation replaced by "No runtime metrics available — excluded from analysis" and Confidence forced to `LOW`; it is not omitted from the report, so the section count always matches the container count in Current Configuration, and the gap is visible in place rather than only in the aggregated Missing Information list.
- Replica Impact Summary — current vs. recommended totals, per §5.2.
- Resource Limit Analysis — existing ratio or "platform requires limits?" outcome, per §12.
- Estimated Resource Savings — CPU/memory delta, workload-level.
- Risk Assessment — over/under-provisioning flags from §9, OOM history callouts.
- Assumptions — e.g., percentile method, rounding convention, platform overrides applied.
- Missing Information — containers with no metrics, fields the user declined to provide, and how that lowered confidence.

The "Missing Information" and "Assumptions" sections are not optional boilerplate — they are where validation gaps from §4.3 and confidence downgrades from §10 must be surfaced, so the report is self-explanatory about *why* a number is what it is.

—

## 12. Resource Limit Decision Logic

Implements PRD §"Resource Limit Decision Logic" as a branch evaluated once per container:

```text
if container has existing limits:
    ratio = current_limit / current_request   # per resource, CPU and memory independently
    recommended_limit = round(recommended_request * ratio)   # §8

else:
    if platformRequiresLimits is null:
        ask_user("Does your Kubernetes platform require resource limits? [Yes/No]")
        # store the boolean answer in platformRequiresLimits (§4.1) — no third option

    if platformRequiresLimits == true:
        if platformLimitPolicy is not provided:
            ask_user(
                "What ratio or absolute cap does your platform require for CPU/memory limits? "
                "(e.g. '2x request', or an absolute value like '2000m CPU / 1Gi memory'). "
                "Reply 'not sure' if you don't know."
            )
        if platformLimitPolicy provided (ratio or absolute):
            recommended_limit = apply_policy(recommended_request, platformLimitPolicy)  # §8 rounding applied after
            label recommendation as "policy-derived" in the report, not usage-derived
        else:  # user replied "not sure" — platformRequiresLimits is still true, just no policy value
            recommended_limit = round(recommended_request * DEFAULT_CONSERVATIVE_RATIO)
            # DEFAULT_CONSERVATIVE_RATIO = 2.0 (CPU), 1.5 (memory) — matches the
            # PRD's own over-provisioning thresholds (§9), so a limit at this
            # ratio does not itself trigger an over-provisioning flag.
            flag in Assumptions: "No platform limit policy provided; used a
            conservative default ratio. Confirm against actual platform policy
            before applying."

    else:  # platformRequiresLimits == false
        recommended_limit = None  # requests-only recommendation
```

This must run per container per resource (CPU and memory can have different existing ratios), not once for the whole workload.

**Platform limit policy source (resolved, was open in §13):** rather than silently deriving a limit from an undefined "platform policy," the model asks for the policy directly in-conversation (a ratio or an absolute cap) and stores it in the optional `platformLimitPolicy` field (§4.1) so it's part of the auditable input, not a hidden side channel. If the user doesn't know their platform's policy, the skill falls back to a conservative default ratio (2.0× CPU, 1.5× memory — deliberately set at the PRD's own over-provisioning threshold, so the fallback recommendation doesn't immediately flag itself as over-provisioned) and says so explicitly under Assumptions, rather than guessing silently or blocking the report.

`platformRequiresLimits` itself is strictly boolean (§4.1) — the question posed to the user has exactly two answers, Yes or No. There is no "Unknown" branch: if the user genuinely doesn't know whether their platform requires limits, that's a real-world Yes/No fact they need to go find out or guess at, not a third state the skill models — the skill should encourage them to check rather than accept ambiguity here. (Contrast with `platformLimitPolicy`'s "not sure" above, which is a legitimately different question — "does my platform require limits" vs. "what exactly is the required ratio" — and only the latter has a graceful unknown-value fallback.)

—

## 13. Resolved Decisions (v1 Defaults)

The PRD left the following underspecified. Each is now pinned to a concrete default so implementation can proceed without further blocking questions. These are v1 defaults, not immutable — revisit if real usage shows a default is wrong.

| # | Gap | Default chosen | Where implemented |
|---|---|---|---|
| 1 | Whether the platform requires limits, and the policy source | Two-valued question ("Does your platform require limits? [Yes/No]") stored in its own `platformRequiresLimits` boolean field. If Yes, ask for the ratio/cap separately and store in `platformLimitPolicy`; if the user doesn't know the exact policy, fall back to a conservative ratio (2.0× CPU, 1.5× memory) and flag it under Assumptions. | §4.1, §12 |
| 2 | "Increasing memory trend" definition | First-half-vs-second-half mean comparison, flagged at >10% rise. Chosen over a regression slope for explainability and robustness on short/sparse windows. | §9 |
| 3 | "Complete workload info" for HIGH confidence | Requires an explicit answer (value or confirmed-absent) for every optional field — `limits`, `hpa`, `restartHistory`, `platformLimitPolicy` — not merely "whatever was asked." Prevents reaching HIGH confidence by skipping questions. | §10 |
| 4 | DaemonSet replica count | Ask the user directly ("how many nodes/pods is this scheduled on?"). If unavailable, leave `replicas` unset, report impact totals as "not computable," and force `LOW` confidence (missing critical info). | §4.1 |
| 5 | Percentile interpolation method & unit convention | Linear interpolation (e.g. `numpy.percentile` default); binary (1024-based) units end-to-end. Required to reproduce the PRD's own worked examples exactly. | §6, §8 |
| 6 | ~~"Unknown" answer to "does your platform require limits?"~~ | **Superseded** — the question is strictly Yes/No (item 1); there is no third "Unknown" answer to handle. `platformRequiresLimits: null` distinguishes "not asked yet" from either answer, so no separate Unknown-handling branch is needed. | §4.1, §12 |
| 7 | Container with config but no metrics | Gets its own Container Analysis subsection (not omitted), with Usage Analysis/Recommendation replaced by an explicit "no metrics" note and Confidence forced to `LOW`. | §11 |

Items 1 and 4 introduce user-facing questions beyond what §3's state machine originally enumerated (`COLLECT_CONFIG`/`COLLECT_METRICS` should be read as including these follow-ups, not just the base fields in §4.1-4.2).

—

## 14. Testing Strategy

- **Unit tests on `scripts/calc.py`**: all PRD worked examples (CPU/memory formulas, rounding, ratio-based limit derivation, variability classification, confidence tiers) as fixed input/output pairs — these are the PRD's own examples and must pass exactly.
- **Schema validation tests**: malformed/incomplete inputs from §4.3 each produce the expected rejection or warning, not a silent pass-through.
- **Scenario tests** (via `examples/sample-input.json` → expected report sections): single-replica workload, multi-replica workload, workload with existing limits, workload with no limits (both platform-requires-limits branches), workload with OOM events, workload with insufficient observation window (<24h) to confirm it downgrades confidence rather than blocking the report.
- **Conversation-flow review**: manually walk the state machine (§3) with partial information at each state to confirm the skill asks targeted follow-up questions rather than failing or guessing.
- **Resolved-decision coverage (§13)**: unit tests for the first-half/second-half trend detector at and around the 10% boundary; a scenario test for a DaemonSet with no user-supplied replica count (confirms "not computable" impact + forced `LOW` confidence, not a guessed number); a scenario test for a container present in config with zero metrics samples (confirms its own report subsection, not an omission); and scenario tests for both the policy-provided and "not sure" branches of §12's limit logic (confirms the conservative-ratio fallback and its Assumptions callout).
