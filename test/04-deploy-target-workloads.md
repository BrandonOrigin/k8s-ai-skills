# Step 4: Deploy the Target Workloads

Two Deployments, each built to land skill1 on a different branch of its
threshold logic (spec §9):

| Deployment | Scenario | How | skill1 should flag |
|---|---|---|---|
| `overprovisioned-app` | Requests far more CPU/memory than it needs | `app`'s requests set high; the load generator (step 5) keeps real usage well below them | CPU/memory over-provisioning (`current > recommended × 2` / `× 1.5`) |
| `underprovisioned-app` | Requests too little memory, OOMKilled at peak | `limits.memory` sized for off-peak traffic only; step 5's peak-hour burst pushes concurrently-held memory past the limit | Memory under-provisioning + OOM events |

—

## Deploy both

```bash
kubectl apply -f manifests/00-namespace.yaml

kubectl apply -f manifests/overprovisioned-app-configmap.yaml
kubectl apply -f manifests/overprovisioned-app-deployment.yaml
kubectl apply -f manifests/overprovisioned-app-service.yaml

kubectl apply -f manifests/underprovisioned-app-configmap.yaml
kubectl apply -f manifests/underprovisioned-app-deployment.yaml
kubectl apply -f manifests/underprovisioned-app-service.yaml
```

—

## Verify

```bash
kubectl get pods -n test-workload -o wide
```

Expect 3 `overprovisioned-app` pods (2/2 containers: `app` + `log-agent`)
and 2 `underprovisioned-app` pods (1/1 container: `app`), all `Running`.

```bash
kubectl exec -n test-workload deploy/overprovisioned-app -c app -- python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/?work=100000').read())"

kubectl exec -n test-workload deploy/underprovisioned-app -c app -- python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/?size_kb=10&hold_ms=10').read())"
```

Both should print `b'ok\n'`.

Confirm the deliberate sizing is in effect:

```bash
kubectl get deployment overprovisioned-app -n test-workload -o jsonpath='{.spec.template.spec.containers[*].resources}' | python3 -m json.tool
kubectl get deployment underprovisioned-app -n test-workload -o jsonpath='{.spec.template.spec.containers[*].resources}' | python3 -m json.tool
```

`underprovisioned-app` shouldn't be OOMKilled yet at this point — it only
gets real traffic once step 5's load generators are running. If you see
restarts already, something other than the intended peak-hour burst is
hitting it; check `kubectl describe pod` before moving on.

—

## Resource budget on a 2 vCPU box

Running both scenarios plus their load generators (step 5) at once is
tighter than the single-workload setup from the original walkthrough. 2
vCPU / 4GB still fits, but with little headroom. If pods stay `Pending`:

```bash
kubectl describe nodes | grep -A5 "Allocated resources"
```

and if CPU is the constraint, the easiest fix is trimming
`overprovisioned-app`'s replica count (it doesn't need 3 to make its point):

```bash
kubectl scale deployment overprovisioned-app -n test-workload --replicas=2
```

—

## Tuning (optional)

- **Flip which resource is over/under-provisioned:** edit the
  `requests`/`limits` in `overprovisioned-app-deployment.yaml` /
  `underprovisioned-app-deployment.yaml` directly.
- **Stable vs. variable usage (variability ratio, spec's Confidence
  Model):** both load generators (step 5) default to a day/night pattern,
  which produces a "variable" ratio. Flattening either script to constant
  values regardless of hour produces a "stable" one instead.
- **How often `underprovisioned-app` OOMs:** driven by
  `underprovisioned-load-generator-configmap.yaml`'s peak-hour
  `CONCURRENCY`/`SIZE_KB`/`HOLD_MS` vs. `underprovisioned-app`'s
  `limits.memory` — raise the limit or lower those values if it's crashing
  too often to accumulate useful "normal" samples between OOMs; lower the
  limit or raise them if it's not triggering at all.

Re-apply with `kubectl apply -f manifests/<file>.yaml` after editing —
this restarts the pods, so only do it before starting the observation
window, not partway through.

Next: [05-deploy-synthetic-load-generators.md](05-deploy-synthetic-load-generators.md)
