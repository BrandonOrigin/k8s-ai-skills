# Report Template

This is the literal Markdown skeleton for a right-sizing report (spec §11).
Replace every `{{placeholder}}` with real values; repeat the "Container
Analysis" subsection once per container in "Current Configuration" so the
section count always matches, including containers with no runtime metrics.

—

# Resource Right-Sizing Report: {{kind}}/{{name}} ({{namespace}})

## Executive Summary

- Containers analyzed: {{total_containers}}
- Headline savings: {{headline_savings_percent}}%
- Overall risk level: {{overall_risk_level}}

{{one_or_two_sentence_summary}}

## Current Configuration

| Field | Value |
|---|---|
| Kind | {{kind}} |
| Name | {{name}} |
| Namespace | {{namespace}} |
| Replicas | {{replicas_or_not_computable}} |

| Container | CPU Request | Memory Request | CPU Limit | Memory Limit |
|---|---|---|---|---|
| {{container_name}} | {{current_cpu_request}} | {{current_memory_request}} | {{current_cpu_limit_or_none}} | {{current_memory_limit_or_none}} |

## Container Analysis

<!-- Repeat this subsection once per container listed in Current
Configuration, in the same order, with no omissions. -->

### {{container_name}}

**Current Resources**

- Request: {{current_cpu_request}} CPU / {{current_memory_request}} memory
- Limit: {{current_cpu_limit_or_none}} CPU / {{current_memory_limit_or_none}} memory

**Usage Analysis**

- CPU: P50 {{cpu_p50}}, P95 {{cpu_p95}}, variability {{cpu_variability_class}}
- Memory: P50 {{memory_p50}}, P95 {{memory_p95}}, variability {{memory_variability_class}}

**Recommendation**

- Request: {{recommended_cpu_request}} CPU / {{recommended_memory_request}} memory
- Limit: {{recommended_cpu_limit_or_none}} CPU / {{recommended_memory_limit_or_none}} memory

**Confidence**

{{confidence_level}} — {{one_line_confidence_reason}}

<!-- For a container present in the workload config with no matching
runtime metrics, replace the "Usage Analysis" and "Recommendation"
subsections above with the block below, and force Confidence to LOW: -->

<!--
**Usage Analysis / Recommendation**

No runtime metrics available — excluded from analysis.

**Confidence**

LOW — no runtime metrics available for this container.
-->

## Replica Impact Summary

| Metric | Current (total) | Recommended (total) | Delta |
|---|---|---|---|
| CPU | {{current_cpu_total_or_not_computable}} | {{recommended_cpu_total_or_not_computable}} | {{cpu_delta_or_not_computable}} |
| Memory | {{current_memory_total_or_not_computable}} | {{recommended_memory_total_or_not_computable}} | {{memory_delta_or_not_computable}} |

{{note_if_replica_count_unknown}}

## Resource Limit Analysis

For each container, one of:

- Existing limit ratio: {{container_name}} — CPU {{existing_cpu_ratio}}x, memory {{existing_memory_ratio}}x, applied to the recommended request.
- No existing limits, platform requires limits: {{container_name}} — limit derived from {{policy_derived_or_conservative_default}}.
- No existing limits, platform does not require limits: {{container_name}} — requests-only recommendation, no limit.

## Estimated Resource Savings

- CPU savings: {{cpu_savings_absolute}} ({{cpu_savings_percent}}%)
- Memory savings: {{memory_savings_absolute}} ({{memory_savings_percent}}%)

## Risk Assessment

| Container | Over-provisioned | Under-provisioned | OOM history |
|---|---|---|---|
| {{container_name}} | {{cpu_or_memory_overprovisioned_flags}} | {{cpu_or_memory_underprovisioned_flags}} | {{oom_event_count_or_none}} |

## Assumptions

- Percentile method: linear interpolation (spec §6).
- Rounding convention: {{rounding_convention_summary}}.
- Platform overrides applied: {{platform_overrides_or_none}}.
- {{any_other_assumption_e.g._partial_trend_coverage_or_conservative_default_ratio}}

## Missing Information

- Containers with no runtime metrics: {{containers_with_no_metrics_or_none}}
- Fields the user declined to provide: {{declined_fields_or_none}}
- How missing information lowered confidence: {{confidence_impact_summary}}
