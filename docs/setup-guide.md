# Setup Guide: Claude Code CLI on Ubuntu + Testing Skill1

This guide covers two things:

1. Installing the Claude Code CLI on an Ubuntu server.
2. Installing **Skill1** (`k8s-resource-right-sizing`) so you can test it with Claude Code.

—

## 0. Status check before you start

Skill1's implementation is tracked by three documents in this repo:

- `docs/PRD/skill1.md` — product requirements
- `docs/specs/skill1-technical-spec.md` — technical design
- `docs/plan.md` — the task-by-task implementation plan (`T0`-`T17`)

As of this writing, **the `skills/k8s-resource-right-sizing/` package described in the plan has not landed yet** — there is no `SKILL.md` in this repo. Follow the steps below to get Claude Code CLI ready now; the "Install Skill1" section will work as soon as the package (starting with `T0` scaffolding) is merged. If you just want to confirm the CLI + skill-loading mechanics work today, you can create a minimal placeholder `SKILL.md` yourself (see §4.1) and swap in the real package later — the install steps don't change.

—

## 1. Prerequisites

On the Ubuntu server:

```bash
sudo apt update
sudo apt install -y curl git
```

Claude Code requires Node.js 18+ if you install via npm. Check what you have:

```bash
node -v
```

If Node is missing or too old, install a current LTS via `nvm`:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install --lts
```

—

## 2. Install the Claude Code CLI

Two supported install paths — pick one.

### Option A: Native installer (recommended, no Node.js required)

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

This installs a standalone `claude` binary to `~/.local/bin` (make sure that's on your `PATH`).

### Option B: npm (if you already manage Node tooling)

```bash
npm install -g @anthropic-ai/claude-code
```

### Verify the install

```bash
claude --version
```

—

## 3. Authenticate

Run `claude` in any directory and follow the login prompt (this opens a browser-based OAuth flow, or accepts an API key if you're on a headless box):

```bash
claude
```

If the server has no browser access, use an API key instead:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
claude
```

Confirm you're logged in with `/status` inside the `claude` REPL, or just send a test message.

—

## 4. Get the repo

```bash
git clone https://github.com/BrandonOrigin/k8s-ai-skills.git
cd k8s-ai-skills
```

—

## 4.1 Install Skill1 for testing

Claude Code discovers Skills from `SKILL.md` files under either:

- **Project-level**: `<project>/.claude/skills/<skill-name>/SKILL.md` — only active when you run `claude` inside that project.
- **Personal-level**: `~/.claude/skills/<skill-name>/SKILL.md` — active across every project for your user.

For testing Skill1 against this repo, project-level is simplest: symlink the skill package into `.claude/skills/` so future updates in `skills/k8s-resource-right-sizing/` are picked up automatically.

```bash
mkdir -p .claude/skills
ln -s ../../skills/k8s-resource-right-sizing .claude/skills/k8s-resource-right-sizing
```

Then start Claude Code from the repo root:

```bash
claude
```

**If `skills/k8s-resource-right-sizing/` doesn't exist yet** (see §0), you can stand up a throwaway placeholder to confirm the loading mechanics work, then delete it once the real package lands:

```bash
mkdir -p skills/k8s-resource-right-sizing
cat > skills/k8s-resource-right-sizing/SKILL.md <<'EOF'
---
name: k8s-resource-right-sizing
description: >
  Analyze a running Kubernetes Deployment, StatefulSet, or DaemonSet using
  historical CPU/memory usage metrics and generate container-level resource
  request/limit recommendations with confidence levels. Use when a user asks
  to right-size, optimize, or reduce resource waste for an existing workload.
---

(placeholder body — replace with the real skill once implemented)
EOF
```

### Verify the skill is discovered

Inside the `claude` REPL:

```
/skills
```

This lists all Skills Claude Code found (project + personal). Confirm `k8s-resource-right-sizing` appears with the description from its frontmatter.

You can also just ask Claude directly, e.g. `"do you have a skill for right-sizing Kubernetes resources?"` — it should recognize the Skill from its description and offer to use it.

—

## 5. Test the skill

Once the real implementation (per `docs/plan.md`) is in place, drive a test conversation by asking Claude to analyze a workload, e.g.:

```
Use the k8s-resource-right-sizing skill to analyze the Deployment "checkout-api"
in namespace "prod". Here's its config and metrics: <paste from
skills/k8s-resource-right-sizing/examples/sample-input.json>
```

Confirm:

- It asks follow-up questions for any missing required fields (workload config, CPU/memory metrics) rather than guessing.
- It stops early and explains itself if you point it at an unsupported workload kind (e.g. a `CronJob`).
- The final report follows the structure in `skills/k8s-resource-right-sizing/references/report-template.md` and matches the numbers in `skills/k8s-resource-right-sizing/examples/sample-report.md` when run against the sample input.

—

## 6. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `claude: command not found` | `~/.local/bin` (native installer) or your npm global bin dir isn't on `PATH`. Add it to `~/.bashrc`/`~/.profile`. |
| Skill doesn't show up in `/skills` | Wrong path (`.claude/skills/<name>/SKILL.md`, not just `.claude/skills/SKILL.md`), missing/invalid YAML frontmatter, or `claude` wasn't started from the project root. |
| Login fails on a headless server | Use `ANTHROPIC_API_KEY` instead of the browser OAuth flow. |
| Claude doesn't pick the skill from natural language | Its `description` in the frontmatter needs to clearly state what it's for and when to use it — check against §2 of `docs/specs/skill1-technical-spec.md`. |
