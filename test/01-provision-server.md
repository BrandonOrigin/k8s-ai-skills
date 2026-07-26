# Step 1: Provision the Server

—

## Sizing

| Resource | Minimum | Notes |
|---|---|---|
| vCPU | 2 (3 more comfortable) | k3s idles around 0.3-0.5 vCPU. Steps 4-5 now deploy **two** scenario workloads plus their load generators; 2 vCPU still fits but with little headroom — see the "Resource budget" note in `04-deploy-target-workloads.md` if pods stay `Pending`. |
| RAM | 4GB (6GB more comfortable) | Prometheus + kube-state-metrics + node-exporter idle around 600MB-1GB; **RAM is the tighter constraint than CPU** for the monitoring stack specifically. If you only have 2GB, use the manifest-only alternative noted in `03-install-monitoring-stack.md` instead of the full Helm chart. |
| Disk | 20GB | Prometheus retention is capped at 10 days in step 3's config; 20GB is comfortable headroom |
| OS | Ubuntu 22.04 LTS | Any 2-3 vCPU / 4-6GB cloud VM works (e.g. Hetzner CX22/CX32, DigitalOcean Basic Droplet, AWS Lightsail, EC2 t3.medium) — the provider doesn't matter, only the spec |

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
