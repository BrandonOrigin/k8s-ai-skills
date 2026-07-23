# Skill: Kubernetes Security Misconfiguration Review

## Summary

Review Kubernetes workload configuration and identify common security risks and configuration weaknesses.

—

## Problem Statement

Many Kubernetes workloads run with insecure default configurations, exposing unnecessary security risks.

This Skill reviews workload manifests against Kubernetes security best practices and highlights potential issues before they reach production.

—

## Expected Inputs

Required:

- Deployment / StatefulSet manifest

Optional:

- Service
- Ingress
- NetworkPolicy
- ServiceAccount
- Role
- RoleBinding
- Pod Security Context
- Namespace configuration

—

## Expected Outputs

The Skill should produce a Markdown report containing:

- Executive summary
- Security findings
- Severity for each finding
- Explanation of each risk
- Recommended remediation
- References to Kubernetes security best practices

—

## Success Criteria

- Detects common Kubernetes security misconfigurations
- Clearly explains the security impact
- Provides practical remediation guidance
- Avoids false positives where possible

—

## Out of Scope

- Vulnerability scanning
- Runtime threat detection
- Compliance certification
- Penetration testing