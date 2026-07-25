# Implementation Plan: Kubernetes Resource Right-Sizing Skill

Source spec: `docs/specs/skill1-technical-spec.md` (all section numbers below, e.g. "§7", refer to that document).
Target package: `skills/k8s-resource-right-sizing/` (layout defined in spec §2).

## How to use this plan

Tasks are ordered so each one can be implemented and verified on its own, without later tasks existing yet. Within a phase, tasks are mostly independent of each other (noted under "Depends on"); phases are ordered by dependency. Run each task's verify command before moving on — don't batch several tasks and verify at the end.

All Python lives under `skills/k8s-resource-right-sizing/scripts/`; all tests live under `skills/k8s-resource-right-sizing/tests/`. Test commands below assume the working directory is the repo root.

—

## Phase 0: Scaffolding

### T0. Create package skeleton

**Files touched:**
- `skills/k8s-resource-right-sizing/SKILL.md` (frontmatter only, from spec §2, plus a one-line placeholder body)
- `skills/k8s-resource-right-sizing/references/methodology.md` (header only: `# Methodology`)
- `skills/k8s-resource-right-sizing/references/report-template.md` (header only: `# Report Template`)
- `skills/k8s-resource-right-sizing/scripts/__init__.py` (empty — makes `scripts` importable as a package)
- `skills/k8s-resource-right-sizing/scripts/calc.py` (module docstring only)
- `skills/k8s-resource-right-sizing/scripts/schema.py` (module docstring only)
- `skills/k8s-resource-right-sizing/scripts/requirements.txt` (`jsonschema` — pytest is a dev-only dependency, not listed here)
- `skills/k8s-resource-right-sizing/tests/__init__.py` (empty)
- `skills/k8s-resource-right-sizing/tests/conftest.py` (adds `scripts/`'s parent to `sys.path` so tests can `from scripts import calc, schema`)
- `skills/k8s-resource-right-sizing/examples/.gitkeep`

**Change:** Nothing functional — establishes the directory layout from spec §2 so every later task only adds/edits one file at a time.

**Verify:**
```bash
find skills/k8s-resource-right-sizing -type f | sort
python3 -m py_compile skills/k8s-resource-right-sizing/scripts/calc.py skills/k8s-resource-right-sizing/scripts/schema.py
pip install -r skills/k8s-resource-right-sizing/scripts/requirements.txt
```
All three commands succeed with no errors; the `find` output matches the layout in spec §2 plus the `tests/` additions listed above.

**Depends on:** nothing.

—

## Phase A: `scripts/calc.py` — deterministic math

Each task in this phase adds a self-contained group of functions to `calc.py` and a matching test file. They can be done in any order after T0, but the order below follows the data flow (units → percentiles → sizing → rounding → thresholds → trend → confidence → limit policy) so later tasks can reuse earlier ones in their own tests.

### T1. K8s quantity parsing and formatting

**Files touched:**
- `skills/k8s-resource-right-sizing/scripts/calc.py` — add `parse_cpu_quantity(s: str) -> int` (millicores), `parse_memory_quantity(s: str) -> int` (bytes), `format_cpu_millicores(m: int) -> str`, `format_memory_bytes(b: int) -> str`.
- `skills/k8s-resource-right-sizing/tests/test_calc_units.py` (new)

**Change:** Parse Kubernetes CPU quantities (`"500m"`, `"1"`, `"2"`) to millicores, and memory quantities (`"128Mi"`, `"1Gi"`, `"700Mi"`) to bytes using **binary (1024-based) units end-to-end**, per spec §8's pinned unit convention. Formatting functions are the inverse, used later when the report needs human-readable values.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_calc_units.py -v
```
Table-driven cases: `"500m"→500`, `"1"→1000`, `"2"→2000`, `"128Mi"→134217728`, `"1Gi"→1073741824`, `"700Mi"→734003200`; round-trip `format_cpu_millicores(500) == "500m"`, `format_memory_bytes(134217728) == "128Mi"`.

**Depends on:** T0.

—

### T2. Percentile calculation and multi-replica aggregation

**Files touched:**
- `scripts/calc.py` — add `percentile(values: list[float], p: float) -> float` (linear interpolation, per spec §6) and `aggregate_samples(pod_sample_lists: list[list[float]]) -> list[float]` (flat concatenation).
- `tests/test_calc_percentile.py` (new)

**Change:** Implement P50/P95 via linear interpolation on a sorted array (spec §6 pins this method to reproduce the PRD's worked examples exactly — do not use nearest-rank). `aggregate_samples` concatenates sample lists from all replica pods before percentiles are computed; for `replicas == 1` it's a no-op returning the single list unchanged.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_calc_percentile.py -v
```
Cases: a known array with a hand-computed P50/P95 (e.g. `[100,200,300,400,500]` → P50=300, P95=420 under linear interpolation — confirm against `numpy.percentile([100,200,300,400,500], 95, method="linear")` or equivalent manual calc); single-replica no-op; multi-replica aggregation producing a longer combined list before percentiles are taken.

**Depends on:** T0.

—

### T3. Sizing formulas

**Files touched:**
- `scripts/calc.py` — add `recommended_cpu_millicores(p95_millicores: float, safety_factor: float = 1.2) -> float`, `recommended_memory_bytes(p95_bytes: float, safety_factor: float = 1.25) -> float`.
- `tests/test_calc_sizing.py` (new)

**Change:** Pure multiplication per spec §7, with safety factors as **parameters with the spec's defaults**, not hardcoded — enables the platform-override hook from §8 to pass different values later without touching this function.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_calc_sizing.py -v
```
PRD worked examples: `recommended_cpu_millicores(250) == 300` (pre-rounding, 250×1.2); `recommended_memory_bytes(734003200) == 917504000.0` (700Mi × 1.25 = 875Mi in bytes, pre-rounding). Also confirm a custom `safety_factor` argument overrides the default.

**Depends on:** T0.

—

### T4. Rounding

**Files touched:**
- `scripts/calc.py` — add `round_cpu_millicores(m: float) -> int`, `round_memory_bytes(b: float) -> int`, `round_limit_from_ratio(rounded_request: float, ratio: float, round_fn: Callable) -> int`.
- `tests/test_calc_rounding.py` (new)

**Change:** Up-only rounding per spec §8 — CPU to nearest 50m, memory to nearest 128Mi below 1Gi / 256Mi at-or-above 1Gi. `round_limit_from_ratio` implements the exact order of operations from §8: multiply the **already-rounded** request by the ratio, then round the result with the same rounding function.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_calc_rounding.py -v
```
Exact fixtures from spec §8, as millicores/bytes: `264→300`, `310→350`, `501→550` (CPU); `format_memory_bytes(round_memory_bytes(parse_memory_quantity("300Mi"))) == "384Mi"`, `"700Mi"→"768Mi"`, `"875Mi"→"896Mi"`, `"1.1Gi"→"1.25Gi"`, `"1.6Gi"→"1.75Gi"`. Also the PRD's end-to-end limit example: request 1000m/limit 2000m (ratio 2×) with P95=250m → rounded request 300m → limit 600m via `round_limit_from_ratio`.

**Depends on:** T1 (uses `parse_memory_quantity`/`format_memory_bytes` in test fixtures), T3 (conceptually chains after sizing, though not a hard code dependency).

—

### T5. Over/under-provisioning thresholds

**Files touched:**
- `scripts/calc.py` — add `cpu_overprovisioned`, `memory_overprovisioned`, `cpu_underprovisioned`, `memory_underprovisioned` (boolean functions per spec §9's threshold formulas; `memory_overprovisioned`/`memory_underprovisioned` take `increasing_trend: bool` and `any_oom_events: bool` as parameters — trend detection itself is T6).
- `tests/test_calc_thresholds.py` (new)

**Change:** Direct translation of the four comparisons in spec §9 (2×, 1.5×, 0.8×, 0.9× thresholds).

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_calc_thresholds.py -v
```
Boundary cases for each: just above/below/at the threshold multiplier (e.g. `current=2×recommended` is NOT over-provisioned since the spec uses strict `>`; `current=2×recommended+1` is). Confirm `memory_overprovisioned` returns `False` when `increasing_trend=True` or `any_oom_events=True` even if the ratio condition holds.

**Depends on:** T0.

—

### T6. Per-pod memory trend detection

**Files touched:**
- `scripts/calc.py` — add `container_memory_trend_increasing(pod_sample_series: list[list[tuple[float, float]]]) -> bool`, exactly as specified in spec §9's resolved algorithm.
- `tests/test_calc_trend.py` (new)

**Change:** Implements the per-pod-then-combine trend algorithm: each pod's series sorted by its own timestamp, split at its own midpoint, `second_half_mean/first_half_mean - 1` computed per pod, then unweighted mean across pods, flagged `True` if `> 0.10`.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_calc_trend.py -v
```
Cases: single pod rising >10% → `True`; single pod flat/falling → `False`; multi-replica with one pod rising 30% and one falling 10% → average 10% → check boundary behavior at exactly the threshold; a pod with `<4` samples excluded from the signal (verify via a case where excluding it flips the result vs. including it incorrectly); all pods excluded → `False`; a pod with `first_half_mean == 0` skipped without raising `ZeroDivisionError`.

**Depends on:** T0.

—

### T7. Confidence model

**Files touched:**
- `scripts/calc.py` — add `variability_ratio(p50: float, p95: float) -> float`, `variability_class(ratio: float) -> str`, `confidence_level(observation_hours: float, overall_variability: str, workload_info_complete: bool, critical_info_missing: bool) -> str`.
- `tests/test_calc_confidence.py` (new)

**Change:** Implements spec §10 exactly, including precedence (`LOW` checked first as an override, then `HIGH`'s AND-conditions, else `MEDIUM`) and the `p50 == 0` → `inf` → `highly_variable` → forced `LOW` safety case.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_calc_confidence.py -v
```
Cases: `variability_ratio(0, 100) == float("inf")` (no exception); boundary `ratio == 2` → `"stable"`, `ratio == 2.0001` → `"variable"`, `ratio == 4` → `"variable"`, `ratio == 4.0001` → `"highly_variable"`; `confidence_level` boundaries at `observation_hours == 24` and `== 168`; `critical_info_missing=True` forces `LOW` even when hours/variability would otherwise qualify for `HIGH`; `workload_info_complete=False` caps at `MEDIUM` (not `LOW`) when hours/variability are otherwise fine.

**Depends on:** T0. (Note: the caller, not this function, is responsible for computing `workload_info_complete` and `critical_info_missing` from the presence-convention rules in spec §4.1/§10 — that logic lives in `schema.py`, see T10.)

—

### T8. Platform limit policy application

**Files touched:**
- `scripts/calc.py` — add `DEFAULT_CONSERVATIVE_CPU_RATIO = 2.0`, `DEFAULT_CONSERVATIVE_MEMORY_RATIO = 1.5`, and `apply_limit_policy(rounded_request: float, policy: dict | None, resource: Literal["cpu", "memory"], round_fn: Callable) -> tuple[int, bool]` — returns `(recommended_limit, used_conservative_default)`.
- `tests/test_calc_policy.py` (new)

**Change:** Implements spec §12's policy branch: `policy={"type": "ratio", ...}` multiplies and rounds; `policy={"type": "absolute", ...}` parses and rounds the absolute value directly; `policy=None` (the "not sure" case) falls back to the conservative default ratio and reports that it did so (the caller uses the returned flag to add the Assumptions callout from spec §12).

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_calc_policy.py -v
```
Cases: ratio policy doubles the rounded request then rounds again; absolute policy returns the parsed-and-rounded absolute value regardless of the request value; `policy=None` for `resource="cpu"` uses `2.0`, for `resource="memory"` uses `1.5`, and `used_conservative_default is True` only in this branch.

**Depends on:** T1 (quantity parsing for absolute policy values), T4 (rounding functions).

—

## Phase B: `scripts/schema.py` — input validation

### T9. Workload configuration schema + presence-convention validation

**Files touched:**
- `scripts/schema.py` — add `WORKLOAD_CONFIG_SCHEMA` (JSON Schema dict, draft 2020-12) and `validate_workload_config(data: dict) -> list[str]` (returns a list of human-readable error strings; empty list = valid).
- `tests/test_schema_workload.py` (new)

**Change:** Encodes spec §4.1's shape and the presence convention from spec §4.1/§4.3: `limits` (per container), `hpa`, `platformLimitPolicy` are typed `["object", "null"]`; `restartHistory` is typed `array` (no `null` variant — its "confirmed absent" state is `[]`, not `null`); `platformRequiresLimits` is typed `["boolean", "null"]`. `containers[].requests.{cpu,memory}` required; `containers` must be non-empty.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_schema_workload.py -v
```
Cases: a fully-populated valid config passes; empty `containers: []` fails; a container missing `requests.memory` fails; `limits: null` on a container passes (confirmed-absent, not a validation error); `hpa: null` passes; `restartHistory: []` passes; `restartHistory: null` **fails** (null is not a valid state for this field — only `[]` or a populated array); `platformRequiresLimits: null` passes (means unresolved, still schema-valid); `platformRequiresLimits: "unknown"` (a string) fails (must be boolean or null — no third value, per spec §4.1's resolved two-valued design).

**Depends on:** T0.

—

### T10. Runtime metrics schema, cross-validation, and completeness/critical-info checks

**Files touched:**
- `scripts/schema.py` — add `RUNTIME_METRICS_SCHEMA`, `validate_runtime_metrics(data: dict) -> list[str]`, `validate_cross(workload_config: dict, metrics_list: list[dict]) -> tuple[list[str], list[str]]` (returns `(errors, warnings)` per spec §4.3's reject-vs-warn split), and `workload_info_complete(workload_config: dict) -> bool` / `critical_info_missing(workload_config: dict, metrics_list: list[dict]) -> bool` implementing the completeness checklist from spec §10.

**Change:** `validate_runtime_metrics` requires `cpu.samples`, `memory.samples`, `observationWindowHours`. `validate_cross` implements all four bullets of spec §4.3: reject empty/missing-requests containers (delegates to T9's validator), reject a metrics entry whose container name isn't in the workload config, reject `observationWindowHours < 1`, and warn (not reject) on a config container with no matching metrics entry. `workload_info_complete` reads exactly the key-presence checklist from spec §10 (`limits` per container, `hpa`, `restartHistory`, `platformRequiresLimits`, and conditionally `platformLimitPolicy`).

**Files touched (tests):**
- `tests/test_schema_metrics.py` (new)
- `tests/test_schema_cross.py` (new)
- `tests/test_schema_completeness.py` (new)

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_schema_metrics.py tests/test_schema_cross.py tests/test_schema_completeness.py -v
```
`test_schema_metrics.py`: valid metrics entry passes; missing `cpu.samples` fails.
`test_schema_cross.py`: one fixture per §4.3 bullet — mismatched container name → error; `observationWindowHours = 0.5` → error; `observationWindowHours = 1` → passes (boundary); a config container with zero matching metrics entries → warning only, not an error, and the overall result is still "proceed."
`test_schema_completeness.py`: all four/five checklist fields key-present → `workload_info_complete() is True`; any one key-absent (not `null` — genuinely missing from the dict) → `False`; `platformRequiresLimits: True` with `platformLimitPolicy` key-absent → `False` (must ask the policy question); `platformRequiresLimits: True` with `platformLimitPolicy: null` (the "not sure" case) → `True` (resolved per spec §10's explicit carve-out); a container with no metrics → `critical_info_missing() is True`.

**Depends on:** T9.

—

## Phase C: Reference documentation

These are documentation files consumed by the model at conversation time, not by tests directly — verification is a manual content check against the spec, backed by a lightweight automated constant-check to catch transcription typos.

### T11. `references/methodology.md`

**Files touched:**
- `skills/k8s-resource-right-sizing/references/methodology.md`
- `tests/test_references_consistency.py` (new)

**Change:** Human-readable writeup (for the model to read at conversation time) of: percentile method (§6), sizing formulas (§7), rounding rules with the worked examples (§8), over/under-provisioning thresholds (§9), the per-pod trend algorithm in prose (§9), and the confidence model (§10) — mirroring the spec's content but written as guidance prose rather than pseudo-code, since this is what the model reads to explain its own numbers in the report's Assumptions section.

**Verify:**
- Manual check: read `references/methodology.md` side-by-side with spec §6-§10; confirm every constant and threshold matches exactly (safety factors 1.2/1.25, rounding steps 50m/128Mi/256Mi, over/under thresholds 2×/1.5×/0.8×/0.9×, trend threshold 10%, variability boundaries 2/4, confidence hour boundaries 24/168).
- Automated backstop:
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_references_consistency.py -v
```
which asserts (via simple string search) that `references/methodology.md` contains the literal tokens `"1.2"`, `"1.25"`, `"50m"`, `"128Mi"`, `"256Mi"`, `"2×"` or `"2x"`, `"1.5×"` or `"1.5x"`, `"0.8"`, `"0.9"`, `"10%"`, `"7 days"` or `"168"`, `"24"`. This doesn't prove correctness, only catches an omitted or mistyped constant.

**Depends on:** T0 (no code dependency, but should be written after Phase A so the prose can reference the actual function names/behavior).

—

### T12. `references/report-template.md`

**Files touched:**
- `skills/k8s-resource-right-sizing/references/report-template.md`
- `tests/test_report_template.py` (new)

**Change:** The literal Markdown skeleton from spec §11 with all nine sections in order (Executive Summary, Current Configuration, Container Analysis, Replica Impact Summary, Resource Limit Analysis, Estimated Resource Savings, Risk Assessment, Assumptions, Missing Information), including the "no metrics available" placeholder text for a container subsection per spec §11's resolved item 7.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_report_template.py -v
```
Asserts all nine section headings appear, in order, by searching for each heading string and checking their line-number ordering is monotonically increasing.

**Depends on:** T0.

—

## Phase D: Examples and integration tests

### T13. `examples/sample-input.json`

**Files touched:**
- `skills/k8s-resource-right-sizing/examples/sample-input.json`
- `tests/test_sample_input.py` (new)

**Change:** One realistic multi-container Deployment fixture (3 replicas) covering as many branches as possible in a single file: one container with existing limits (exercises the ratio branch of §12), one container with `limits: null` and `platformRequiresLimits: true` + a populated `platformLimitPolicy` (exercises the policy-provided branch), a sidecar container present in `containers[]` but absent from the metrics list (exercises the "no metrics" report subsection), and one `oomEvents` entry (exercises the memory under-provisioning OOM trigger).

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && python3 -c "import json; json.load(open('examples/sample-input.json'))"
pytest tests/test_sample_input.py -v
```
`test_sample_input.py` loads the fixture and runs it through `schema.validate_workload_config`, `schema.validate_runtime_metrics` (per container with metrics), and `schema.validate_cross`, asserting zero errors and exactly one warning (for the sidecar with no metrics).

**Depends on:** T9, T10.

—

### T14. End-to-end scenario tests

**Files touched:**
- `tests/test_scenarios.py` (new)

**Change:** Wires `calc.py` + `schema.py` together over `examples/sample-input.json` plus small inline fixtures, covering every scenario listed in spec §14: single-replica workload, multi-replica workload, existing-limits container, no-limits container with `platformRequiresLimits=True` (both policy-provided and "not sure" sub-branches), `platformRequiresLimits=False`, a workload with OOM events, a workload with `observationWindowHours < 24`, a DaemonSet with no user-supplied replica count, and a container present in config with zero metrics samples. Each scenario asserts on the *computed values* (recommended request/limit numbers, confidence tier, over/under-provisioning flags) — not on rendered Markdown, since report rendering is the model's job (T16), not this script's.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing && pytest tests/test_scenarios.py -v
```
Each scenario is a separate test function; all pass. This is the automated stand-in for spec §14's "Scenario tests" and "Resolved-decision coverage" bullets.

**Depends on:** T1-T10, T13.

—

### T15. `examples/sample-report.md`

**Files touched:**
- `skills/k8s-resource-right-sizing/examples/sample-report.md`

**Change:** A hand-authored full Markdown report for the `sample-input.json` scenario, following `report-template.md`'s structure, with numbers that match what `test_scenarios.py` (T14) computes for the same input. This is a reference artifact for SKILL.md's authoring style, not something the code validates.

**Verify:** Manual cross-check — for every numeric value in `sample-report.md` (recommended CPU/memory requests and limits, confidence tiers, savings percentages), confirm it matches the corresponding assertion in `tests/test_scenarios.py`. Also confirm all nine section headings from `report-template.md` (T12) are present.

**Depends on:** T12, T14.

—

## Phase E: The skill itself

### T16. `SKILL.md`

**Files touched:**
- `skills/k8s-resource-right-sizing/SKILL.md`

**Change:** Full workflow instructions implementing the §3 state machine: how to identify the workload and reject unsupported kinds, the exact data-collection questions (including the resolved follow-ups from spec §13 items 1, 4, and 8 — DaemonSet replica count, container-level limits, `platformRequiresLimits` Yes/No, policy ratio/absolute/"not sure"), when to call `scripts/calc.py` and `scripts/schema.py` functions vs. do arithmetic itself (never — per spec §2's rationale), and how to assemble the final report from `references/report-template.md` using `references/methodology.md` to explain the numbers.

**Verify:** Manual check — this is inherently not unit-testable, since it drives an LLM conversation rather than deterministic code (this is spec §14's "Conversation-flow review," performed here rather than automated):
1. Start a live conversation invoking the skill with only a workload name (no config, no metrics) and confirm it asks for missing information in a sensible order, including the resolved follow-up questions, without guessing.
2. Run it against the full `examples/sample-input.json` scenario (paste the data in) and confirm the produced report's structure and numbers match `examples/sample-report.md` (T15).
3. Trigger the DaemonSet-with-unknown-replica-count path and confirm the report says impact is "not computable" rather than guessing a number, and confidence is forced to `LOW`.
4. Trigger an unsupported workload kind (e.g. "analyze my CronJob") and confirm it stops immediately with an explanation, per spec §3, rather than attempting a static-YAML-style review.

**Depends on:** T1-T15 (references every prior artifact).

—

## Phase F: Wrap-up

### T17. Full test suite + dependency pin check

**Files touched:**
- `skills/k8s-resource-right-sizing/scripts/requirements.txt` (confirm final dependency list — likely just `jsonschema`)
- No other files — this is a verification-only task.

**Change:** None — this task exists to run the complete suite once, end to end, as a final gate before considering the skill implementation done.

**Verify:**
```bash
cd skills/k8s-resource-right-sizing
pip install -r scripts/requirements.txt
pytest tests/ -v
```
All tests from T1-T14 pass in a single run with no import errors or path issues.

**Depends on:** T0-T16.

—

## Summary table

| Task | Area | New files | Depends on |
|---|---|---|---|
| T0 | Scaffolding | package skeleton | — |
| T1 | calc.py | quantity parsing | T0 |
| T2 | calc.py | percentile/aggregation | T0 |
| T3 | calc.py | sizing formulas | T0 |
| T4 | calc.py | rounding | T1, T3 |
| T5 | calc.py | over/under thresholds | T0 |
| T6 | calc.py | trend detection | T0 |
| T7 | calc.py | confidence model | T0 |
| T8 | calc.py | limit policy | T1, T4 |
| T9 | schema.py | workload config schema | T0 |
| T10 | schema.py | metrics schema + cross-validation | T9 |
| T11 | references/ | methodology.md | T0 (after Phase A) |
| T12 | references/ | report-template.md | T0 |
| T13 | examples/ | sample-input.json | T9, T10 |
| T14 | tests/ | scenario tests | T1-T10, T13 |
| T15 | examples/ | sample-report.md | T12, T14 |
| T16 | SKILL.md | the skill itself | T1-T15 |
| T17 | — | full-suite check | T0-T16 |
