# Skill: Kubernetes Resource Right-Sizing Recommendation

## Summary

Guide platform engineers through the process of collecting the required workload and runtime information, then analyze Kubernetes resource utilization and provide safe, explainable CPU and memory request recommendations.

This Skill should support an interactive workflow, allowing users to start with little or no information. The Skill should determine what information is required, guide the user to collect it, validate the provided data, and produce actionable recommendations.

—

# Problem Statement

Determining appropriate Kubernetes resource requests is one of the most common and difficult operational tasks.

Many workloads are significantly over-provisioned, wasting cluster resources and increasing infrastructure costs. Others are under-provisioned, leading to CPU throttling, Out Of Memory (OOM) events, or degraded application performance.

Although resource optimization requires workload configuration and historical runtime metrics, engineers often do not know:

- What information is required
- Where to obtain the required metrics
- Which metrics are actually important
- How to interpret the collected data

This Skill should guide engineers through the complete right-sizing workflow instead of assuming all required data is already available.

—

# Goals

The Skill should:

- Help users identify the required information.
- Guide users to collect missing data.
- Validate whether sufficient information has been provided.
- Explain any limitations caused by missing data.
- Recommend appropriate CPU and memory requests.
- Explain the reasoning behind every recommendation.

—

# Supported Targets

Version 1 supports:

- Deployment
- StatefulSet
- DaemonSet

Version 1 does not support:

- Job
- CronJob
- VirtualMachine

—

# Expected User Workflow

The Skill should support an iterative conversation rather than a single request.

Typical workflow:

1. Understand the workload to analyze.
2. Determine what information is available.
3. Identify missing information.
4. Guide the user to collect missing data.
5. Validate the collected information.
6. Analyze resource utilization.
7. Produce recommendations.
8. Explain assumptions, confidence, and risks.

The Skill should continue the conversation until sufficient information is available or clearly explain any limitations.

—

# Required Information

The analysis may require:

## Workload Configuration

- Kubernetes manifest
- Current CPU requests
- Current Memory requests
- Resource limits (if configured)
- Replica count

## Runtime Metrics

- CPU utilization
- Memory utilization
- Observation period

Preferred observation period:

- 7 days or longer

Acceptable:

- 24 hours

The Skill should explain when the available observation period is insufficient.

—

# Interactive Data Collection

When required information is unavailable, the Skill should guide the user through the collection process.

Examples include:

- Asking which monitoring platform the user uses.
- Explaining what metrics are required.
- Suggesting how to obtain those metrics for the user’s environment.
- Confirming the collected information before continuing.

The Skill should adapt to the user’s environment instead of assuming a specific monitoring platform.

—

# Data Validation

Before analysis, the Skill should verify:

- Required workload configuration is available.
- CPU metrics are available.
- Memory metrics are available.
- Observation period is sufficient.

If information is missing, the Skill should:

- Explain what is missing.
- Explain how the missing information affects recommendation quality.
- Continue when possible with reduced confidence.

—

# Expected Output

The Skill should generate a Markdown report containing:

## Executive Summary

High-level recommendation and confidence.

## Current Configuration

Current CPU and memory requests.

## Resource Utilization Summary

Observed CPU and memory usage.

## Recommendation

Recommended CPU request.

Recommended memory request.

## Estimated Resource Savings

Estimated reduction in requested resources.

## Risk Assessment

Potential operational risks associated with the recommendation.

## Assumptions

Document assumptions made during analysis.

## Missing Information

List missing information that may reduce recommendation quality.

—

# Success Criteria

A successful analysis should:

- Identify obvious over-provisioning.
- Identify obvious under-provisioning.
- Produce explainable recommendations.
- Clearly communicate confidence.
- Clearly communicate analysis limitations.
- Require minimal Kubernetes expertise from the user.

—

# Out of Scope

Version 1 does not:

- Modify Kubernetes manifests.
- Apply configuration changes.
- Recommend HPA configuration.
- Recommend Cluster Autoscaler settings.
- Recommend Resource Limits.
- Continuously monitor workloads.

—

# Future Enhancements

Possible future capabilities include:

- Historical trend analysis
- HPA-aware recommendations
- Namespace-wide optimization
- Cost estimation
- Recommendation comparison across environments
- Automatic report generation