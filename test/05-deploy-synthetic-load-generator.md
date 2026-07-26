# Step 5: Deploy the Synthetic Load Generator

Deploys a small `busybox` pod that continuously sends requests to
`target-app` (step 4) with a diurnal pattern — more concurrent, heavier
requests during business hours, lighter off-hours — so `target-app`'s
actual CPU/memory usage varies realistically over the observation window,
instead of sitting flat.

—

## Deploy

```bash
kubectl apply -f manifests/load-generator-configmap.yaml
kubectl apply -f manifests/load-generator-deployment.yaml
```

—

## Verify

```bash
kubectl get pods -n test-workload -l app=load-generator
```

Expect 1 pod `Running`.

Confirm it's actually reaching `target-app` and usage is moving:

```bash
kubectl top pods -n test-workload -l app=target-app
sleep 30
kubectl top pods -n test-workload -l app=target-app
```

CPU numbers for the `app` container should change between the two
snapshots (not necessarily up — the point is that it's not flat-lined at a
constant value).

—

## Let it run

This is the step where you stop actively driving the cluster and let time
pass. skill1's confidence model (spec §10) treats:

- `< 24h` observation as `LOW` confidence regardless of anything else
- `24h`-`7 days` (or unstable variability) as `MEDIUM`
- `>= 7 days` with stable variability as `HIGH`

So for a meaningful test, leave this running for at least 24 hours, and
ideally a full 7 days if you want to exercise the `HIGH`-confidence path.
Nothing further needs to happen on the cluster during this window — just
don't tear it down.

A quick way to sanity-check it's still alive without waiting the full
window:

```bash
kubectl get pods -n test-workload
kubectl logs -n test-workload deploy/load-generator --tail=5
```

Next: [06-collect-metrics-for-skill1.md](06-collect-metrics-for-skill1.md)
(only after the observation window above has elapsed)
