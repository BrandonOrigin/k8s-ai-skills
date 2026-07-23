# Skill: Kubernetes Resource Right-Sizing Recommendation

## Summary

Guide platform engineers through the process of analyzing running Kubernetes workloads, validating runtime resource usage, and generating safe, explainable resource right-sizing recommendations.

The Skill supports an interactive workflow where users can start with limited information. The Skill identifies missing information, guides users to collect required runtime data, validates the collected information, and generates container-level CPU and memory recommendations.

The Skill focuses on **post-deployment workload optimization** based on actual workload behavior.

—

# Problem Statement

Kubernetes resource sizing is one of the most common challenges for platform engineers.

Incorrect resource configuration can cause:

- Infrastructure cost waste due to over-provisioning.
- Application instability due to under-provisioning.
- Poor cluster capacity planning.
- Inefficient node utilization.

Although Kubernetes resource configuration is simple, determining the correct values requires understanding:

- Current workload configuration.
- Actual runtime resource consumption.
- Workload behavior patterns.
- Platform resource policies.

Many engineers do not know:

- Which metrics are required.
- How much historical data is enough.
- How to interpret workload behavior.
- Whether resource requests and limits are aligned with platform requirements.

This Skill provides a guided workflow to reach a data-driven recommendation.

—

# Scope

## Version 1 Goal

Analyze **existing running Kubernetes workloads** with historical runtime metrics.

The Skill requires:

```
Running Kubernetes workload
+
Runtime metrics
=
Resource recommendation
```

—

# Analysis Target

## Supported

Version 1 supports:

- Deployment
- StatefulSet
- DaemonSet

The target workload must already exist in a Kubernetes cluster.

—

## Not Supported

Version 1 does not analyze:

- Standalone YAML files without runtime data.
- Pre-deployment manifests.
- Job
- CronJob
- VirtualMachine

Static YAML review should be implemented as a separate Skill.

Example:

```
Resource Right-Sizing Skill

        vs

Kubernetes Manifest Review Skill
```

—

# Goals

The Skill should:

- Understand workload context through conversation.
- Collect required runtime information.
- Guide users to obtain missing metrics.
- Analyze resources at container level.
- Consider replica impact.
- Consider existing resource limits and platform policies.
- Generate explainable recommendations.
- Provide confidence levels.

—

# Analysis Unit

Kubernetes resource requests and limits are configured at the container level.

Therefore:

> The unit of analysis is the Kubernetes container, not the Pod.

The Skill must analyze each container independently.

A Pod may contain:

- Application containers
- Service mesh sidecars
- Logging agents
- Monitoring agents
- Other infrastructure containers

The Skill should not only provide Pod-level recommendations.

—

# Interactive Workflow

The Skill should guide users through an interactive process.

```mermaid
flowchart TD

A[User requests right-sizing analysis]
—> B[Identify workload]

B —> C[Collect workload configuration]

C —> D[Collect runtime metrics]

D —> E{Enough information available?}

E —>|No| F[Ask questions and guide data collection]

F —> D

E —>|Yes| G[Validate data]

G —> H[Analyze container resource usage]

H —> I[Generate recommendations]

I —> J[Calculate workload impact]

J —> K[Generate final report]
```

—

# Required Information

## Workload Configuration

Required:

- Kubernetes workload manifest
- Container names
- CPU requests
- Memory requests
- Replica count

Optional:

- Resource limits
- HPA configuration
- Pod restart history

—

# Runtime Metrics

Required:

CPU:

- Historical CPU usage

Memory:

- Historical memory usage


Preferred observation period:

```
>= 7 days
```

Minimum acceptable:

```
>= 24 hours
```

The Skill should reduce confidence if the observation period is insufficient.

—

# Replica Handling

## Recommendation Scope

Replica count does not directly affect container resource recommendations.

The recommendation answers:

> How much CPU and memory should each container instance request?

Example:

Deployment:

```
Replica count: 10
```

Recommendation:

```
CPU Request:

300m per container
```

Not:

```
3000m per container
```

—

## Replica-aware Impact Analysis

Replica count is used for workload-level impact calculation.

Example:

Current:

```
Replicas:
10

CPU Request:
1000m
```

Total:

```
10 × 1000m

= 10000m CPU
```

Recommendation:

```
CPU Request:
300m
```

Total:

```
10 × 300m

= 3000m CPU
```

The Skill should report:

- Total resource reduction
- Potential capacity improvement
- Estimated cost impact (future enhancement)

—

# Multi-replica Metrics Aggregation

When multiple replicas exist:

The Skill should aggregate metrics from all container instances before calculating percentiles.

```mermaid
flowchart LR

A[Metrics from All Replica Containers]
—> B[Combine Usage Samples]

B —> C[Calculate P95 Usage]

C —> D[Apply Safety Factor]

D —> E[Generate Container Recommendation]
```

The Skill should not calculate recommendations based on a single Pod unless only one replica exists.

—

# Resource Limits Handling

## Purpose of Resource Limits

Resource limits are not the primary optimization target.

Resource requests are optimized based on workload utilization.

Resource limits are collected because they provide:

- Capacity planning context.
- Risk assessment.
- Request/limit relationship validation.

—

# Resource Limit Decision Logic

```mermaid
flowchart TD

A[Check Existing Limits]

A —> B{Limits configured?}

B —>|Yes| C[Analyze existing limits]

B —>|No| D{Platform requires limits?}

D —>|Yes| E[Generate limit recommendation]

D —>|No| F[Recommend requests only]

C —> G[Generate final recommendation]

E —> G

F —> G
```

—

# Existing Resource Limits

If limits are already configured:

The Skill should:

- Analyze current request/limit ratio.
- Recommend updated limits when appropriate.
- Preserve existing ratio unless workload behavior suggests otherwise.

Example:

Current:

```yaml
requests:
  cpu: 1000m

limits:
  cpu: 2000m
```

Ratio:

```
2x
```

Recommendation:

```
Request:
300m

Limit:
600m
```

—

# No Existing Resource Limits

If limits are not configured:

The Skill should not automatically create limits by default.

The Skill should ask:

```
Does your Kubernetes platform require resource limits?
```

Possible answers:

```
1. Yes
2. No
3. Unknown
```

If:

```
No
```

The Skill recommends requests only.

If:

```
Yes
```

The Skill generates limit recommendations based on platform policy.

—

# Sizing Methodology

The Skill uses percentile-based resource analysis.

The goal:

> Cover normal workload peaks while avoiding unnecessary over-provisioning.

—

# CPU Recommendation

Formula:

```
Recommended CPU Request =
CPU P95 Usage × CPU Safety Factor
```

Default:

```
CPU Safety Factor = 1.2
```

Example:

```
Current Request:

1000m


CPU P95:

250m


Recommendation:

250m × 1.2

= 300m
```

—

# Memory Recommendation

Formula:

```
Recommended Memory Request =
Memory P95 Usage × Memory Safety Factor
```

Default:

```
Memory Safety Factor = 1.25
```

Example:

```
Current Request:

2Gi


Memory P95:

700Mi


Recommendation:

700Mi × 1.25

= 875Mi

Rounded:

1Gi
```

—

# Recommendation Thresholds

## CPU Over-provisioning

Detected when:

```
Current CPU Request >
Recommended CPU Request × 2
```

—

## Memory Over-provisioning

Detected when:

```
Current Memory Request >
Recommended Memory Request × 1.5
```

Additional checks:

- No increasing memory trend.
- No recent OOM events.

—

## CPU Under-provisioning

Detected when:

```
CPU P95 Usage >
Current CPU Request × 0.8
```

—

## Memory Under-provisioning

Detected when:

```
Memory P95 Usage >
Current Memory Request × 0.9
```

or:

- OOMKilled events detected.
- Memory continuously increasing.

—

# Confidence Model

Every recommendation must include confidence.

## High Confidence

Conditions:

- Metrics >= 7 days.
- Complete workload information.
- Stable usage pattern.

—

## Medium Confidence

Conditions:

- Metrics between 24 hours and 7 days.
- Some optional information missing.

—

## Low Confidence

Conditions:

- Metrics < 24 hours.
- High workload variability.
- Missing critical information.

—

# Expected Output

The Skill should generate a Markdown report.

Structure:

```
# Executive Summary

# Current Configuration

# Container Analysis

## Container A

Current Resources

Usage Analysis

Recommendation

Confidence


# Replica Impact Summary

# Resource Limit Analysis

# Estimated Resource Savings

# Risk Assessment

# Assumptions

# Missing Information
```

—

# Success Criteria

A successful analysis should:

- Analyze running workloads only.
- Provide container-level recommendations.
- Correctly handle multi-container Pods.
- Correctly account for replica impact.
- Explain request and limit relationships.
- Provide explainable methodology.
- Clearly communicate confidence and limitations.

—

# Out of Scope

Version 1 does not:

- Analyze standalone YAML manifests.
- Automatically modify Kubernetes resources.
- Apply Kubernetes changes.
- Configure HPA.
- Configure Cluster Autoscaler.
- Continuously monitor workloads.

—

# Future Enhancements

Possible improvements:

- Automatic metric collection.
- Prometheus integration.
- Cost estimation.
- HPA-aware recommendations.
- Namespace-level optimization.
- Automated pull request generation.