# Skill: Node Group Resource Overcommit Analysis

## Summary

Analyze the aggregate resource allocation and usage of a labeled group of Kubernetes nodes (for example, nodes with label `infra=true`) and warn platform engineers when the group is **already overcommitted**, or is **trending toward overcommitment** in the near future.

The Skill looks at the node group as a single capacity pool: total allocatable CPU/memory versus what has been requested and what is actually being used, then projects forward using recent trend data to flag risk before it becomes an incident.

—

# Problem Statement

Kubernetes schedules Pods based on resource **requests** against node **allocatable** capacity, not on real-time usage. This makes it possible for a group of nodes to look healthy today while quietly approaching a state where:

- New Pods can no longer be scheduled (request-based overcommit / bin-packing exhaustion).
- Nodes experience CPU throttling under load (CPU overcommit).
- Nodes experience memory pressure, evictions, or OOM kills (memory overcommit).

This is especially risky for **purpose-labeled node groups** (e.g. `infra=true`, `role=logging`, `pool=gpu`) that host shared platform services. These groups are often sized once and forgotten, while workload count and resource requests grow over time.

Platform engineers need a way to:

- Check the current commitment level of a labeled node group.
- Understand whether current usage is close to what has been requested (are requests realistic?).
- Get an early warning before the group crosses a capacity threshold, not after.

—

# Scope

## Version 1 Goal

Analyze an **existing, running group of nodes** selected by a Kubernetes label selector.

```
Node group (label selector)
+
Allocatable capacity
+
Scheduled requests/limits
+
Recent usage history
=
Overcommit status + early warning
```

Example invocation:

```
Analyze nodes with label "infra=true" for resource overcommit risk.
```

—

# Analysis Target

## Supported

- A set of nodes selected by one or more label selectors (e.g. `infra=true`, `node-role.kubernetes.io/infra=""`).
- Cluster-wide analysis when no selector is given (treated as a single group: "all nodes").
- CPU and memory as the analyzed resource dimensions.
- Pod count / max-pods-per-node as a secondary scheduling constraint.

## Not Supported

Version 1 does not analyze:

- Ephemeral storage or extended resources (GPUs, custom device plugins) — noted as a future enhancement.
- Single-pod or single-container sizing (see the Resource Right-Sizing Skill for that).
- Cluster Autoscaler / node pool scale-up decisions — this Skill reports risk, it does not act on it.
- Multi-cluster comparison.

—

# Goals

The Skill should:

- Identify the target node group from a label selector.
- Collect allocatable capacity for every node in the group.
- Collect aggregate Pod resource requests and limits scheduled onto the group.
- Collect recent actual usage (CPU/memory) for the group, including a lookback trend.
- Calculate current overcommit ratios for requests, limits, and actual usage.
- Detect whether the group is already overcommitted.
- Project near-term trend to flag groups that will cross a threshold soon, even if not overcommitted today.
- Separate CPU risk (throttling, usually tolerable) from memory risk (eviction/OOM, usually not tolerable).
- Produce a clear, ranked warning report with supporting evidence.

—

# Analysis Unit

> The unit of analysis is the **node group as a capacity pool**, not an individual node or Pod.

Within that pool, the Skill should still surface **per-node outliers** (e.g. one node in the group already at 95% while the group average is 60%) so engineers aren't misled by averaging effects across the group.

—

# Interactive Workflow

```mermaid
flowchart TD

A[User requests overcommit analysis for a node group] --> B[Resolve label selector to node list]

B --> C{Any nodes match?}
C -->|No| Z[Report: no matching nodes, suggest checking label]
C -->|Yes| D[Collect node allocatable capacity]

D --> E[Collect scheduled Pod requests and limits on group]
E --> F[Collect recent usage metrics for group]

F --> G{Enough usage history available?}
G -->|No| H[Ask user to provide/collect metrics, lower confidence]
H --> F
G -->|Yes| I[Calculate current overcommit ratios]

I --> J[Calculate usage trend over lookback window]
J --> K[Project time-to-threshold]
K --> L[Identify per-node outliers]
L --> M[Classify risk: OK / Watch / Overcommitted]
M --> N[Generate report]
```

—

# Required Information

## Node Group Definition

Required:

- Label selector (e.g. `infra=true`). Defaults to all schedulable nodes if omitted.

Collected per matching node:

- Node name
- Allocatable CPU
- Allocatable memory
- Max Pods
- Ready / schedulable status
- Taints (informational — explains why only some workloads land here)

—

## Scheduled Workload Data

Required, aggregated across all Pods scheduled onto the group:

- Sum of container CPU requests
- Sum of container CPU limits
- Sum of container memory requests
- Sum of container memory limits
- Pod count

DaemonSet Pods must be included — they are often the biggest hidden contributor to overcommit on infra-labeled node groups (logging agents, CNI, storage agents, monitoring).

—

## Usage Metrics

Required:

- Node-level CPU usage (recent)
- Node-level memory usage (recent)

Preferred observation period:

```
>= 7 days, sampled at a resolution that preserves peak spikes (e.g. 5m)
```

Minimum acceptable:

```
>= 24 hours
```

The Skill should reduce confidence if the observation period is insufficient, same as the trend projection in the next section.

—

# Overcommit Calculation

The Skill evaluates overcommit across three layers, computed independently for CPU and memory:

```
Layer 1 — Request Overcommit (scheduling risk)
Layer 2 — Limit Overcommit  (burst/OOM risk)
Layer 3 — Usage Overcommit  (real-time pressure)
```

## Request Overcommit Ratio

```
Request Overcommit Ratio =
Sum(Container Requests) / Sum(Node Allocatable)
```

Interpretation:

```
Ratio <= 1.0   → Requests fit within allocatable capacity
Ratio >  1.0   → Group cannot schedule its declared requests
                 (new Pods may go Pending)
```

## Limit Overcommit Ratio

```
Limit Overcommit Ratio =
Sum(Container Limits) / Sum(Node Allocatable)
```

Interpretation:

```
CPU:    Ratio > 1.0 is common and often acceptable
        (CPU is compressible — worst case is throttling)

Memory: Ratio > 1.0 is high risk
        (Memory is incompressible — worst case is OOM kill / eviction)
```

## Usage Overcommit Ratio

```
Usage Overcommit Ratio =
P95(Node Group Usage) / Sum(Node Allocatable)
```

This reflects real pressure regardless of what was requested, and is the primary signal for "is this group actually running hot."

—

# Trend Projection — "Going to Be Overcommitted Soon"

A group that is not overcommitted today can still be flagged if it is approaching a threshold quickly.

## Method

1. Take the request-overcommit ratio and usage-overcommit ratio at regular points over the lookback window (e.g. daily).
2. Fit a simple linear trend to each series.
3. Project the number of days until the ratio crosses the warning threshold (default `0.85`) and the critical threshold (default `1.0`).

```
Projected Days To Threshold =
(Threshold - Current Ratio) / Daily Growth Rate
```

## Warning Conditions

```
Trending — Watch:
   Projected Days To Threshold <= 14
   AND Daily Growth Rate > 0

Trending — Urgent:
   Projected Days To Threshold <= 7
   AND Daily Growth Rate > 0
```

If the growth rate is flat or negative, the group is reported as stable regardless of current ratio proximity to threshold.

The Skill must clearly label trend-based warnings as **projections**, distinct from current-state findings, and must state the lookback window and assumptions used (linear growth).

—

# Risk Classification

Each resource dimension (CPU, memory) and each layer (request, limit, usage) is classified:

```
OK             Ratio <  0.70,  no urgent trend
Watch          0.70 <= Ratio < 0.85,  or trending — watch
Warning        0.85 <= Ratio < 1.00,  or trending — urgent
Overcommitted  Ratio >= 1.00
```

Memory findings at `Warning` or `Overcommitted` should always be surfaced above CPU findings of the same class — memory pressure has more severe failure modes (evictions/OOM) than CPU pressure (throttling).

—

# Per-Node Outlier Detection

After computing group-level ratios, the Skill should flag individual nodes whose usage or request ratio deviates significantly from the group average:

```
Outlier Node:
   Node Ratio >= Group Average Ratio + 20 percentage points
```

This prevents a well-balanced group average from hiding one or two hot nodes.

—

# Confidence Model

## High Confidence

- Usage metrics >= 7 days.
- All nodes in the selector returned complete allocatable and usage data.
- DaemonSet requests included in the aggregation.

## Medium Confidence

- Usage metrics between 24 hours and 7 days, or
- A small number of nodes (<10% of group) missing metrics.

## Low Confidence

- Usage metrics < 24 hours, or
- Scheduled request/limit data unavailable (ratios based on usage only), or
- Trend projection based on fewer than 3 data points.

—

# Expected Output

The Skill should generate a Markdown report.

Structure:

```
# Executive Summary

# Node Group
  - Label selector
  - Node count
  - Total allocatable CPU / Memory

# Current Overcommit Status
  - Request Overcommit Ratio (CPU / Memory)
  - Limit Overcommit Ratio (CPU / Memory)
  - Usage Overcommit Ratio (CPU / Memory)
  - Risk Classification

# Trend Projection
  - Growth rate
  - Projected days to Warning / Critical threshold

# Per-Node Outliers

# DaemonSet Contribution

# Recommendations
  - e.g. add nodes, rebalance workloads, right-size requests, adjust label selector membership

# Assumptions

# Missing Information
```

—

# Success Criteria

A successful analysis should:

- Correctly resolve the label selector to the intended node group.
- Include DaemonSet Pods in aggregation.
- Report request, limit, and usage overcommit separately.
- Distinguish CPU risk from memory risk in both language and ranking.
- Clearly separate "overcommitted now" from "trending toward overcommitted" findings.
- Identify per-node outliers, not just the group average.
- State confidence and data limitations explicitly.

—

# Out of Scope

Version 1 does not:

- Automatically add/remove nodes or resize node pools.
- Configure or trigger Cluster Autoscaler.
- Modify workload resource requests/limits.
- Analyze extended resources (GPU, ephemeral storage) or custom device plugins.
- Compare overcommit across multiple clusters.

—

# Future Enhancements

Possible improvements:

- Ephemeral storage and extended resource overcommit.
- Direct Cluster Autoscaler / Karpenter integration for automated remediation suggestions.
- Cost impact estimation for adding capacity vs. right-sizing workloads.
- Multi-selector comparison (e.g. compare `infra=true` vs `infra=false` pools).
- Seasonal/periodic trend detection instead of simple linear projection.
- Automated Slack/alertmanager notification integration.
