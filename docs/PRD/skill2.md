# Skill: CrashLoopBackOff Root Cause Analysis

## Summary

Help engineers quickly identify the most likely causes of CrashLoopBackOff and recommend troubleshooting steps.

—

## Problem Statement

CrashLoopBackOff is one of the most common operational issues in Kubernetes.

Investigating failures often requires collecting information from multiple sources, including logs, events, pod configuration, probes, and recent deployment changes.

This Skill consolidates available information and provides a ranked list of likely root causes.

—

## Expected Inputs

Required:

- Pod description (`kubectl describe pod`)
- Pod events
- Container logs

Optional:

- Deployment manifest
- ConfigMaps
- Secrets
- Probe configuration
- Previous deployment revision

—

## Expected Outputs

The Skill should produce a Markdown report containing:

- Incident summary
- Most likely root causes
- Confidence level for each finding
- Supporting evidence
- Recommended investigation steps
- Recommended remediation actions

—

## Success Criteria

- Identifies common CrashLoopBackOff scenarios
- Explains why each hypothesis was generated
- Prioritizes findings by confidence
- Produces actionable troubleshooting guidance

—

## Out of Scope

- Automatically restarting workloads
- Automatically modifying Kubernetes resources
- Live debugging inside containers