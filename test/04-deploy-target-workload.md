# Step 4: Deploy the Target Workload

This is the Deployment skill1 will eventually analyze: 3 replicas, 2
containers per pod (`app` + `log-agent`), with `app`'s requests set higher
than the load in step 5 will actually use — a deliberate over-provisioning
case for skill1 to catch.

—

## Deploy

```bash
kubectl apply -f manifests/00-namespace.yaml
kubectl apply -f manifests/target-app-configmap.yaml
kubectl apply -f manifests/target-app-deployment.yaml
kubectl apply -f manifests/target-app-service.yaml
```

—

## Verify

```bash
kubectl get pods -n test-workload -o wide
```

Expect 3 pods, 2/2 containers ready, `Running`.

```bash
kubectl exec -n test-workload deploy/target-app -c app -- python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/?work=100000').read())"
```

Expect `b'ok\n'`.

Confirm the deliberately-oversized requests are in effect:

```bash
kubectl get deployment target-app -n test-workload -o jsonpath='{.spec.template.spec.containers[*].resources}' | python3 -m json.tool
```

—

## Tuning for other scenarios (optional)

The default `app` requests (`500m`/`256Mi`) plus step 5's default load
pattern produce an over-provisioning scenario. To exercise other branches
of skill1's threshold logic (spec §9), adjust before waiting for data to
accumulate:

- **Under-provisioning:** lower `app`'s `requests.cpu`/`requests.memory` in
  `target-app-deployment.yaml`, or raise the `WORK`/`CONCURRENCY` values in
  step 5's load script, so P95 usage exceeds the request.
  - **Stable vs. variable usage (variability ratio, spec's Confidence
  Model):** the default day/night pattern in step 5 already produces a
  "variable" ratio; flattening the script to a constant `WORK`/`SLEEP`
  regardless of hour produces a "stable" one instead.

Re-apply with `kubectl apply -f manifests/target-app-deployment.yaml` after
editing — this restarts the pods, so only do it before starting the
observation window, not partway through.

Next: [05-deploy-synthetic-load-generator.md](05-deploy-synthetic-load-generator.md)
