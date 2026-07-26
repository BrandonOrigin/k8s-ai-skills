# Step 3: Install Prometheus + kube-state-metrics

This is what gives skill1 the **historical** CPU/memory data it needs —
`metrics-server` alone (installed by default in step 2) only exposes
current usage and can't answer "what was P95 over the last 7 days."

—

## Install Helm

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
```

—

## Install the stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

kubectl create namespace monitoring

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f manifests/prometheus-values.yaml
```

(Run this from the repo root so the relative `-f` path resolves; adjust the
path if you're running it elsewhere.)

This deploys Prometheus, the Prometheus Operator, kube-state-metrics, and
node-exporter — Grafana and Alertmanager are disabled per
`manifests/prometheus-values.yaml`.

—

## Verify

```bash
kubectl get pods -n monitoring
```

Expect (naming may vary slightly by chart version):

```
kube-prometheus-stack-operator-...        Running
kube-prometheus-stack-prometheus-node-... Running   (DaemonSet, one per node)
kube-state-metrics-...                    Running
prometheus-kube-prometheus-stack-prometheus-0   Running
```

Check resource usage stays reasonable on the 2 vCPU box:

```bash
kubectl top pods -n monitoring
```

—

## Confirm targets are being scraped

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import json, sys
data = json.load(sys.stdin)['data']['activeTargets']
for t in data:
    print(t['labels'].get('job', '?'), '->', t['health'])
"
```

You should see `kube-state-metrics`, `node-exporter`, and `kubelet`/`cadvisor`
jobs reporting `up`. Leave the port-forward running (or re-run it later) —
step 6 uses the same `localhost:9090` endpoint.

Kill the background port-forward when you're done poking around:

```bash
kill %1
```

—

## If 2GB RAM is all you have

The full chart (operator + CRDs + Prometheus) is comfortable at 4GB but
tight below that. A lower-memory alternative is to skip the operator
entirely and install the `prometheus-community/prometheus` chart (no CRDs)
plus the standalone `prometheus-community/kube-state-metrics` chart. The
PromQL queries in step 6 are unaffected either way — only the install
method changes.

Next: [04-deploy-target-workload.md](04-deploy-target-workload.md)
