# The recommendation from k8s-resource-right-sizing skill after /usage1 day.

## overprovisioned-app

### Output

- Recommendation: 50m CPU / 128Mi memory, limit 100m / 256Mi
- Confidence: MEDIUM (same reason)
- Note: the 128Mi memory recommendation is the rounding-floor artifact, not signal — actual usage is ~350x below it

Replica Impact (×3 replicas)

┌────────┬─────────┬─────────────┬──────────────┐
│ Metric │ Current │ Recommended │    Delta     │
├────────┼─────────┼─────────────┼──────────────┤
│ CPU    │ 1575m   │ 600m        │ −975m (−62%) │
├────────┼─────────┼─────────────┼──────────────┤
│ Memory │ 864Mi   │ 768Mi       │ −96Mi (−11%) │
└────────┴─────────┴─────────────┴──────────────┘

Memory savings are muted because log-agent's memory recommendation is pulled up to the 128Mi floor despite trivial actual usage — a case where the formula output is worth a human override.

No OOM events, restarts, or HPA were found for this workload over the full observation window.

✻ Baked for 3m 57s


### Claude Token Usage

Settings  Status   Config   Usage   Stats

 Session

 Total cost:            $1.14
 Total duration (API):  3m 55s
 Total duration (wall): 15m 35s
 Total code changes:    116 lines added, 0 lines removed
 Usage by model:
     claude-haiku-4-5:  535 input, 19 output, 0 cache read, 0 cache write ($0.0006)
      claude-sonnet-5:  654 input, 21.0k output, 1.7m cache read, 54.7k cache write ($1.14)
                                                                                                                                                    Current session
 ██                                                 4% used
 Resets 4:10pm (UTC)

--- 

## underprovisioned-app


### Output

 Executive Summary

- Containers analyzed: 1
- Headline change: memory is underprovisioned — this is a reliability fix, not a savings opportunity (+128Mi memory total; CPU unchanged)
- Overall risk level: HIGH — the container is actively crash-looping on OOMKilled

The app container is stuck in a continuous OOM crash-restart cycle: 172 and 175–177 restarts respectively on its two pods over the 25h observation window, all OOMKilled (exit 137), one as recently as ~3 minutes before this analysis. The 64Mi memory request / 128Mi limit is too tight for what the workload actually needs.

Current Configuration

┌───────────┬──────────────────────┐
│   Field   │        Value         │
├───────────┼──────────────────────┤
│ Kind      │ Deployment           │
├───────────┼──────────────────────┤
│ Name      │ underprovisioned-app │
├───────────┼──────────────────────┤
│ Namespace │ test-workload        │
├───────────┼──────────────────────┤
│ Replicas  │ 2                    │
└───────────┴──────────────────────┘

┌───────────┬─────────────┬────────────────┬───────────┬──────────────┐
│ Container │ CPU Request │ Memory Request │ CPU Limit │ Memory Limit │
├───────────┼─────────────┼────────────────┼───────────┼──────────────┤
│ app       │ 50m         │ 64Mi           │ 200m      │ 128Mi        │
└───────────┴─────────────┴────────────────┴───────────┴──────────────┘

Container Analysis

app

Current Resources
- Request: 50m CPU / 64Mi memory
- Limit: 200m CPU / 128Mi memory

Usage Analysis
- CPU: P50 12.8m, P95 23.0m, variability stable (P95/P50 ≈ 1.8)
- Memory: P50 11.7Mi, P95 66.9Mi, variability highly_variable (P95/P50 ≈ 5.7), no sustained increasing trend across the window as a whole — but each individual container lifetime ramps from a few MB up to ~120–128Mi before being OOMKilled

Recommendation
- Request: 50m CPU / 128Mi memory
- Limit: 200m CPU / 256Mi memory (derived from existing 4.0x CPU / 2.0x memory limit-to-request ratio)

Confidence

LOW — memory usage is classified highly_variable (P95/P50 ≈ 5.7), which forces LOW regardless of the observation window; this is itself a symptom of the crash-loop (each restart resets memory near zero, so the combined sample mixes low ramp-up values with near-limit pre-kill values).

Replica Impact Summary

┌────────┬─────────────────┬─────────────────────┬────────┐
│ Metric │ Current (total) │ Recommended (total) │ Delta  │
├────────┼─────────────────┼─────────────────────┼────────┤
│ CPU    │ 100m            │ 100m                │ 0m     │
├────────┼─────────────────┼─────────────────────┼────────┤
│ Memory │ 128Mi           │ 256Mi               │ +128Mi │
└────────┴─────────────────┴─────────────────────┴────────┘

Replica count (2) confirmed from .spec.replicas; no exclusions.

Resource Limit Analysis

- Existing limit ratio: app — CPU 4.0x, memory 2.0x, applied to the recommended request.

Estimated Resource Savings

None — this container needs more memory, not less. CPU is unchanged; memory increases 100% (128Mi → 256Mi total across 2 replicas) to give headroom above the observed pre-kill peak (~127.9Mi, essentially at the current 128Mi limit).

Risk Assessment

┌───────────┬─────────────────────┬──────────────────────┬───────────────────────────────────────────────────────────────────┐
│ Container │  Over-provisioned   │  Under-provisioned   │                            OOM history                            │
├───────────┼─────────────────────┼──────────────────────┼───────────────────────────────────────────────────────────────────┤
│ app       │ CPU: no, Memory: no │ CPU: no, Memory: yes │ 172 restarts (pod 269kr), 177 restarts (pod zr5q5), all OOMKilled │
└───────────┴─────────────────────┴──────────────────────┴───────────────────────────────────────────────────────────────────┘

No HPA configured on this workload.

Assumptions

- Percentile method: linear interpolation (spec §6).
- Rounding convention: CPU rounded up to the nearest 50m; memory rounded up to the nearest 128Mi (below 1Gi).
- Platform overrides applied: none — the container has explicit limits, so the limit was derived from its existing ratio.
- Methodology caveat specific to this workload: because the container restarts every few minutes, Prometheus emits a new metrics series per restart instance. CPU samples were computed as one average-rate value per restart instance (first-to-last counter delta ÷ duration); memory samples are the raw working_set_bytes readings from every restart concatenated in time order. This means the P95 memory figure (66.9Mi) is pulled down by the many low readings early in each short-lived instance's ramp-up — the true pre-kill ceiling is closer to the observed max (~127.9Mi, at the cgroup limit). The recommended 128Mi request / 256Mi limit is a reasoned response to this pattern, not a guarantee the app won't still grow past it — if the underlying cause is an unbounded memory leak rather than a legitimately higher steady-state need, this will delay OOM kills rather than eliminate them.
- Metrics source: Prometheus (kube-prometheus-stack) cAdvisor container metrics, sampled every 60s across the full 25h pod lifetime (both replicas) — not user-supplied.

Missing Information

- Containers with no runtime metrics: none.
- Fields the user declined to provide: none. platformRequiresLimits / platformLimitPolicy were not asked because the container already has explicit limits.
- OOM event list only contains each pod's single most recent OOMKilled timestamp (from lastState.terminated) — Kubernetes doesn't retain a full history of every past kill event, only the last one; total restart counts (172 / 177) came from kube_state_metrics counters and are the more reliable indicator of frequency.
- How missing information lowered confidence: it didn't need to — confidence is already forced to LOW by the highly_variable memory classification, which is itself a direct consequence of the crash-loop pattern.

### Claude Token Usage

Session

Total cost:            $1.94
Total duration (API):  6m 52s
Total duration (wall): 28m 15s
Total code changes:    116 lines added, 0 lines removed
Usage by model:
    claude-haiku-4-5:  535 input, 19 output, 0 cache read, 0 cache write ($0.0006)
     claude-sonnet-5:  1.2k input, 36.5k output, 3.0m cache read, 83.4k cache write ($1.94)

Current session
███▌                                               7% used
Resets 4:10pm (UTC)
