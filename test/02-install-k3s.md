# Step 2: Install k3s

—

## Install

Disable Traefik and the built-in `servicelb` — neither is needed for this
test (everything is reached via `kubectl port-forward` or in-cluster
`Service` DNS), and skipping them saves CPU/RAM on a 2 vCPU box:

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable servicelb --write-kubeconfig-mode 644" sh -
```

k3s ships `metrics-server` by default — that's fine to leave enabled; it's
useful for quick `kubectl top` checks even though it can't provide the
historical data skill1 needs (that's what step 3 adds).

—

## Verify the node is ready

```bash
sudo kubectl get nodes
```

Expect a single node in `Ready` state within ~30-60 seconds.

```bash
kubectl top nodes
kubectl top pods -A
```

`kubectl top` may return `error: metrics not available yet` for the first
minute or two — retry until it populates.

—

## kubeconfig access

**Option A — drive the cluster from the server itself** (simplest): k3s
already wrote `/etc/rancher/k3s/k3s.yaml` readable by any user (because of
`--write-kubeconfig-mode 644` above). Point `kubectl`/`helm` at it:

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
```

**Option B — drive it from your laptop:** copy the kubeconfig off the
server and rewrite the server address from `127.0.0.1` to the server's real
IP:

```bash
scp k8sadmin@<SERVER_IP>:/etc/rancher/k3s/k3s.yaml ~/.kube/k3s-skill1-test.yaml
sed -i '' 's/127.0.0.1/<SERVER_IP>/' ~/.kube/k3s-skill1-test.yaml   # macOS sed; drop the '' on Linux
export KUBECONFIG=~/.kube/k3s-skill1-test.yaml
```

This requires the `6443/tcp` firewall rule from step 1. Every subsequent
`kubectl`/`helm` command in this guide works the same regardless of which
option you pick — just run it wherever `KUBECONFIG` is pointed.

—

## Verify

```bash
kubectl get nodes -o wide
kubectl get pods -A
```

All system pods (`kube-system` namespace: coredns, local-path-provisioner,
metrics-server) should be `Running`.

Next: [03-install-monitoring-stack.md](03-install-monitoring-stack.md)
