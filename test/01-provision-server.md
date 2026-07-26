# Step 1: Provision the Server

—

## Sizing

| Resource | Minimum | Notes |
|---|---|---|
| vCPU | 2 | k3s idles around 0.3-0.5 vCPU; the monitoring stack (step 3) and test workload (steps 4-5) leave enough headroom on 2 vCPU |
| RAM | 4GB | Prometheus + kube-state-metrics + node-exporter idle around 600MB-1GB; **RAM is the tighter constraint than CPU** for this setup. If you only have 2GB, use the manifest-only alternative noted in `03-install-monitoring-stack.md` instead of the full Helm chart. |
| Disk | 20GB | Prometheus retention is capped at 10 days in step 3's config; 20GB is comfortable headroom |
| OS | Ubuntu 22.04 LTS | Any 2 vCPU / 4GB cloud VM works (e.g. Hetzner CX22, DigitalOcean Basic Droplet, AWS Lightsail, EC2 t3.medium) — the provider doesn't matter, only the spec |

This server needs to stay up and reachable **continuously** for the
observation window in step 5 (24h minimum, 7 days preferred) — prefer a
cloud VM or always-on host over a laptop that sleeps or changes networks.

—

## OS prep

SSH into the server, then:

```bash
sudo apt update && sudo apt upgrade -y
sudo hostnamectl set-hostname k3s-skill1-test
```

Create a non-root sudo user if you're currently root-only (skip if you
already have one):

```bash
sudo adduser k8sadmin
sudo usermod -aG sudo k8sadmin
```

—

## Firewall

If the provider or OS firewall is enabled, open only what's needed:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 6443/tcp        # k3s API server — only if you'll reach kubectl from off-box
sudo ufw enable
```

Skip the `6443` rule if you'll only ever run `kubectl`/`helm` on the server
itself (see `02-install-k3s.md` for the alternative of copying kubeconfig to
your laptop, which does need this port open).

—

## Verify

```bash
nproc                # expect 2 (or more)
free -h              # expect ~4GB total
lsb_release -a       # expect Ubuntu 22.04
df -h /              # expect >= 20GB available
```

Next: [02-install-k3s.md](02-install-k3s.md)
