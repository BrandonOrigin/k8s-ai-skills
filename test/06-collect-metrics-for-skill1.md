# Step 6: Collect Metrics for skill1

Run this after the observation window from step 5 has elapsed (24h
minimum, 7 days preferred). It produces, for **each** of the two
Deployments from step 4, the two JSON documents skill1's `VALIDATE` state
expects (spec §3): runtime metrics (§4.2) and workload config (§4.1) — four
files in total.

—

## 1. Ad-hoc sanity checks in Prometheus

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
```

P95 CPU (millicores) over the last 7 days, `overprovisioned-app`'s `app`
container — expect this to sit well *below* its `500m` request:

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=quantile_over_time(0.95, (rate(container_cpu_usage_seconds_total{namespace="test-workload",container="app",pod=~"overprovisioned-app-.*"}[5m]) * 1000)[7d:5m])' \
  | python3 -m json.tool
```

P95 memory (bytes, working set) over the last 7 days,
`underprovisioned-app`'s `app` container — expect this to sit *close to or
above* its `128Mi` limit during peak windows:

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=quantile_over_time(0.95, container_memory_working_set_bytes{namespace="test-workload",container="app",pod=~"underprovisioned-app-.*"}[7d])' \
  | python3 -m json.tool
```

OOM events — expect **empty** for `overprovisioned-app`, **non-empty** for
`underprovisioned-app`:

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=kube_pod_container_status_last_terminated_reason{namespace="test-workload",pod=~"overprovisioned-app-.*",reason="OOMKilled"}' \
  | python3 -m json.tool

curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=kube_pod_container_status_last_terminated_reason{namespace="test-workload",pod=~"underprovisioned-app-.*",reason="OOMKilled"}' \
  | python3 -m json.tool
```

Restart counts, and whether they cluster in the 08:00-20:00 window (a
quick eyeball check that OOMs really are peak-correlated, not random):

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="test-workload",pod=~"underprovisioned-app-.*"}' \
  | python3 -m json.tool
```

If `underprovisioned-app` shows **zero** OOM events after a full peak
window has passed, its memory limit is currently high enough to absorb the
burst — lower `limits.memory` or raise the peak-hour
`CONCURRENCY`/`SIZE_KB` in `underprovisioned-load-generator-configmap.yaml`
per the tuning note in step 4/5 and try again.

—

## 2. Extract the full runtime-metrics history

With the port-forward from above still running, once per Deployment:

```bash
python3 scripts/extract_metrics.py \
  --namespace test-workload --workload overprovisioned-app \
  --containers app log-agent \
  --hours 168 \
  --out overprovisioned-app-runtime-metrics.json

python3 scripts/extract_metrics.py \
  --namespace test-workload --workload underprovisioned-app \
  --containers app \
  --hours 168 \
  --out underprovisioned-app-runtime-metrics.json
```

Use `--hours 24` instead if you're only at the 24h minimum rather than the
full 7-day window. Each run writes an array with one entry per container,
matching spec §4.2's shape, including that container's `oomEvents` —
`underprovisioned-app-runtime-metrics.json`'s `app` entry should have a
non-empty `oomEvents` array if step 5's scenario worked as intended.

—

## 3. Assemble the workload configs

Prometheus doesn't track desired-state config (requests/limits/replica
count) — pull that straight from each live Deployment:

```bash
for WORKLOAD in overprovisioned-app underprovisioned-app; do
  kubectl get deployment "$WORKLOAD" -n test-workload -o json \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
spec = d['spec']['template']['spec']
print(json.dumps({
    'kind': 'Deployment',
    'name': d['metadata']['name'],
    'namespace': d['metadata']['namespace'],
    'replicas': d['spec']['replicas'],
    'containers': [
        {
            'name': c['name'],
            'requests': c['resources'].get('requests', {}),
            'limits': c['resources'].get('limits') or None,
        }
        for c in spec['containers']
    ],
    'hpa': None,
    'restartHistory': [],
    'platformRequiresLimits': None,
    'platformLimitPolicy': None,
}, indent=2))
" > "${WORKLOAD}-workload-config.json"
done
```

This fills in the required fields (`kind`, `name`, `namespace`, `replicas`,
per-container `requests`) automatically. The optional fields are seeded
with placeholder "confirmed absent" values per spec §4.1's presence
convention (`hpa: null`, `restartHistory: []`) — edit
`platformRequiresLimits`/`platformLimitPolicy` by hand if you want to
exercise the resource-limit decision logic (spec §12) rather than leave
them `null` ("not yet asked").

—

## Result

You now have, in the repo root (or wherever you ran these commands):

- `overprovisioned-app-runtime-metrics.json` / `overprovisioned-app-workload-config.json`
- `underprovisioned-app-runtime-metrics.json` / `underprovisioned-app-workload-config.json`

Each pair is exactly what skill1's guided workflow collects during
`COLLECT_CONFIG`/`COLLECT_METRICS` (spec §3) for one workload. Paste a pair
into a conversation invoking the skill to validate its analysis against
real, accumulated cluster data — once against the over-provisioned
workload, once against the under-provisioned/OOMKilled one, to exercise
both branches of the threshold and confidence logic.
