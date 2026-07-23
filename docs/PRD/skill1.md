# Skill: Kubernetes Resource Right-Sizing Recommendation

## Summary

Help platform engineers determine whether Kubernetes CPU and memory requests/limits are appropriately configured and provide actionable optimization recommendations.

—

## Problem Statement

Setting CPU and memory requests is one of the most common challenges in Kubernetes.

Over-provisioning wastes cluster resources and increases infrastructure costs.

Under-provisioning can lead to poor application performance, throttling, or OOM kills.

This Skill analyzes workload configuration and runtime resource usage to recommend appropriate resource settings.

—

## Expected Inputs

Required:

- Deployment / StatefulSet / DaemonSet manifest
- Resource requests and limits
- Historical CPU utilization
- Historical memory utilization

Optional:

- Namespace information
- HPA configuration
- Pod restart history
- Business criticality

—

## Expected Outputs

The Skill should produce a Markdown report containing:

- Current resource configuration
- Resource utilization summary
- Recommended CPU request
- Recommended CPU limit (if applicable)
- Recommended memory request
- Recommended memory limit (if applicable)
- Estimated resource savings
- Risk assessment
- Explanation of the recommendation

—

## Success Criteria

- Identifies obvious over-provisioning
- Identifies obvious under-provisioning
- Provides explainable recommendations
- Avoids unsafe recommendations when confidence is low

—

## Out of Scope

- Automatically modifying Kubernetes manifests
- Applying configuration changes
- Cluster autoscaling decisions