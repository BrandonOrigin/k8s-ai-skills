# Step 5: Deploy the Synthetic Load Generators

Two small `busybox` pods, one per scenario from step 4, each driving a
diurnal (day/night) traffic pattern against its target — but shaped very
differently, because the two scenarios need different kinds of load:

- **`overprovisioned-load-generator` → `overprovisioned-app`:** moderate,
  sequential CPU-work requests. Usage moves around realistically but never
  gets close to `overprovisioned-app`'s (deliberately high) requests.
- **`underprovisioned-load-generator` → `underprovisioned-app`:** off-peak
  is trivial (one small request at a time); peak hours fire a burst of ~20
  concurrent, larger, slower requests. Because `underprovisioned-app`'s
  server is threaded, those concurrent requests hold their memory buffers
  *at the same time*, and the combined total exceeds its memory limit —
  that's what triggers the OOMKill, not a slow leak.

—

## Deploy both

```bash
kubectl apply -f manifests/overprovisioned-load-generator-configmap.yaml
kubectl apply -f manifests/overprovisioned-load-generator-deployment.yaml

kubectl apply -f manifests/underprovisioned-load-generator-configmap.yaml
kubectl apply -f manifests/underprovisioned-load-generator-deployment.yaml
```

—

## Verify

```bash
kubectl get pods -n test-workload -l 'app in (overprovisioned-load-generator,underprovisioned-load-generator)'
```

Expect both `Running`.

Confirm traffic is actually moving usage on both targets:

```bash
kubectl top pods -n test-workload -l app=overprovisioned-app
kubectl top pods -n test-workload -l app=underprovisioned-app
sleep 30
kubectl top pods -n test-workload -l app=overprovisioned-app
kubectl top pods -n test-workload -l app=underprovisioned-app
```

Numbers should change between the two snapshots for both (not necessarily
up — the point is neither is flat-lined at a constant value).

If it's currently within the 08:00-20:00 window (host/UTC time — see the
`HOUR` check in `underprovisioned-load-generator-configmap.yaml`), you can
watch the OOM scenario happen directly instead of waiting:

```bash
kubectl get pods -n test-workload -l app=underprovisioned-app -w
```

A `RESTARTS` count ticking up with `OOMKilled` as the last state
(`kubectl describe pod <pod> -n test-workload`) confirms the mechanism is
working. Outside that window it should stay quiet — restarts clustering
inside business hours and going silent off-hours is the signal skill1 is
meant to pick up on later (spec §9's memory under-provisioning check plus
the OOM-event callout).

—

## Let it run

This is the step where you stop actively driving the cluster and let time
pass. skill1's confidence model (spec §10) treats:

- `< 24h` observation as `LOW` confidence regardless of anything else
- `24h`-`7 days` (or unstable variability) as `MEDIUM`
- `>= 7 days` with stable variability as `HIGH`

So for a meaningful test, leave both running for at least 24 hours, and
ideally a full 7 days if you want to exercise the `HIGH`-confidence path
for `overprovisioned-app` (note `underprovisioned-app`'s recurring OOM
events keep its own confidence capped regardless — see spec §10's
"highly variable"/critical-info conditions). Nothing further needs to
happen on the cluster during this window — just don't tear it down.

A quick way to sanity-check both are still alive without waiting the full
window:

```bash
kubectl get pods -n test-workload
kubectl logs -n test-workload deploy/overprovisioned-load-generator --tail=5
kubectl logs -n test-workload deploy/underprovisioned-load-generator --tail=5
```

Next: [06-collect-metrics-for-skill1.md](06-collect-metrics-for-skill1.md)
(only after the observation window above has elapsed)
