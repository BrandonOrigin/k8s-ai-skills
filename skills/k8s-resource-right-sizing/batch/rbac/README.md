# RBAC for k8s-ai-skills

Read-only Kubernetes RBAC for whichever identity runs `kubectl` on behalf
of this project — the batch scanner's `ServiceAccount` in CI/CD or a
`CronJob` (see `../README.md`), or a human's own `kubectl` context while
following the manual test steps in `../../../test/`. It grants exactly the
API calls those two paths actually make: `get`/`list`/`watch` on
workloads, HPAs, pods, pod logs, nodes, namespaces, events, and the
`metrics.k8s.io` API (for `kubectl top`). No write verbs anywhere, and no
access to Secrets, ConfigMaps, or RBAC objects.

## Option A: cluster-wide (multi-namespace scanning, `kubectl top nodes`)

```bash
kubectl apply -f serviceaccount.yaml
kubectl apply -f clusterrole.yaml
kubectl apply -f clusterrolebinding.yaml
```

Use this if the batch script scans more than one namespace, or you want
node-level context (`kubectl get nodes`, `kubectl top nodes` — both
cluster-scoped, so only a `ClusterRole` + `ClusterRoleBinding` can grant
them).

## Option B: single-namespace, least privilege

```bash
NAMESPACE=prod
sed "s/CHANGE-ME/$NAMESPACE/" role-namespaced.yaml | kubectl apply -f -
sed "s/CHANGE-ME/$NAMESPACE/" rolebinding-namespaced.yaml | kubectl apply -f -
kubectl apply -f serviceaccount.yaml -n "$NAMESPACE"
```

Scoped to one namespace; `kubectl get/top nodes` will not work under this
role (see the comment in `role-namespaced.yaml`). Repeat per namespace if
you want to scan several without granting cluster-wide read.

## Binding to a User instead of a ServiceAccount

For a human running the batch script or the `test/` steps from their own
machine rather than from CI, bind the same `ClusterRole`/`Role` to their
identity instead of the `ServiceAccount`. Edit the `subjects:` block in
`clusterrolebinding.yaml` (or `rolebinding-namespaced.yaml`):

```yaml
subjects:
  - kind: User
    name: jane@example.com   # must match the identity your cluster's auth
                              # provider presents (OIDC subject, cert CN,
                              # cloud-IAM-mapped name, etc.) -- check with
                              # `kubectl auth whoami` if your cluster supports it
    apiGroup: rbac.authorization.k8s.io
```

Kubernetes has no `User` object to create — the name just has to match
whatever your cluster's authentication layer (OIDC, client certs, a cloud
provider's IAM mapping, ...) presents at request time.

## Getting kubectl talking as this identity

For the `ServiceAccount` (e.g. to test the binding, or to build a
kubeconfig for a runner that isn't itself a Pod):

```bash
kubectl create token rightsizing-scanner -n platform-tools --duration=1h
```

Use the resulting token as a bearer token in a kubeconfig, or — inside a
Pod that mounts this `ServiceAccount` (the CronJob example in
`../README.md`) — `kubectl` and the batch script's `subprocess.run(["kubectl", ...])`
calls pick it up automatically via the projected service account token,
no extra configuration needed.

## Verifying the grant

```bash
kubectl auth can-i list deployments -n prod --as=system:serviceaccount:platform-tools:rightsizing-scanner
kubectl auth can-i get nodes --as=system:serviceaccount:platform-tools:rightsizing-scanner
kubectl auth can-i delete pods -n prod --as=system:serviceaccount:platform-tools:rightsizing-scanner  # expect "no"
```
