# Step 6: Collect Metrics for skill1

Run this after the observation window from step 5 has elapsed (24h
minimum, 7 days preferred). It produces the two JSON documents skill1's
`VALIDATE` state expects (spec §3): runtime metrics (§4.2) and workload
config (§4.1).

—

## 1. Ad-hoc sanity checks in Prometheus

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
```

CPU (millicores) for the `app` container, current value:

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=rate(container_cpu_usage_seconds_total{namespace="test-workload",container="app"}[5m]) * 1000' \
  | python3 -m json.tool
```

P95 CPU over the last 7 days:

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=quantile_over_time(0.95, (rate(container_cpu_usage_seconds_total{namespace="test-workload",container="app"}[5m]) * 1000)[7d:5m])' \
  | python3 -m json.tool
```

P95 memory (bytes, working set) over the last 7 days:

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=quantile_over_time(0.95, container_memory_working_set_bytes{namespace="test-workload",container="app"}[7d])' \
  | python3 -m json.tool
```

OOM events, if any (should be empty for the default `app` sizing — expected
if you tuned the under-provisioning scenario in step 4):

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=kube_pod_container_status_last_terminated_reason{namespace="test-workload",reason="OOMKilled"}' \
  | python3 -m json.tool
```

Restart counts:

```bash
curl -sG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="test-workload"}' \
  | python3 -m json.tool
```

—

## 2. Extract the full runtime-metrics history

With the port-forward from above still running:

```bash
python3 scripts/extract_metrics.py \
  --namespace test-workload --workload target-app \
  --containers app log-agent \
  --hours 168 \
  --out skill1-runtime-metrics.json
```

Use `--hours 24` instead if you're only at the 24h minimum rather than the
full 7-day window. This writes an array with one entry per container,
matching spec §4.2's shape — ready to hand to skill1 once
`skills/k8s-resource-right-sizing/` exists.

—

## 3. Assemble the workload config

Prometheus doesn't track desired-state config (requests/limits/replica
count) — pull that straight from the live Deployment:

```bash
kubectl get deployment target-app -n test-workload -o json \
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
" > workload-config.json
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

You now have `skill1-runtime-metrics.json` and `workload-config.json` in
the repo root (or wherever you ran these commands) — the two inputs
skill1's guided workflow collects during `COLLECT_CONFIG`/`COLLECT_METRICS`
(spec §3). Paste them into a conversation invoking the skill to validate
its analysis against real, accumulated cluster data.
