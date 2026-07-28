# AI Agent or Plain Script? A Decision Framework for Platform Engineering Automation

Every platform team experimenting with AI right now is running into the same fork in the road, just wearing different clothes each time. Should code review run through an AI agent, or stay with static analysis tools? Should cloud cost anomalies get triaged by an LLM, or flagged by a rules engine? Should security checks be an AI-driven audit, or a deterministic scanner wired into the pipeline?

The instinct in 2026 is to reach for an agent by default — it's the interesting new tool, and "AI-powered" sells better than "cron job." But teams that do this for every check end up with a bill that scales linearly with usage, a compliance team that can't get a straight answer twice in a row, and an "AI code reviewer" that's really just an expensive way to run a linter. The teams getting real value have learned to ask a sharper question first, and then route accordingly.

## The wrong question and the right one

"Is AI better than scripts?" is the wrong question — it assumes one tool wins across the board. The right question is per-task: **how much of this check is actually a judgment call, and how much of it is deterministic computation that's been dressed up as one?**

Most operational checks — code review, cost analysis, security scanning, resource right-sizing — are really two things bolted together: a mechanical part (parse the input, apply a rule, compute a number, compare against a threshold) and a judgment part (is this actually a problem *here*, what should we do about it, can you explain it to a human who'll push back). Conflating them is what produces both failure modes: scripting the judgment part gives you a rule engine full of brittle special cases; routing the mechanical part through an LLM gives you a slow, expensive, occasionally-wrong version of a function you could have written in ten lines.

This came up concretely while building [k8s-ai-skills](https://github.com/BrandonOrigin/k8s-ai-skills), an open-source library of Claude Agent Skills for Kubernetes platform engineering — worth walking through as a worked example before generalizing.

## A worked example: Kubernetes resource right-sizing

The first Skill in that repo recommends CPU/memory requests and limits for a running workload. The natural instinct is to hand the whole thing to the model: paste in usage data, ask for a recommendation. Instead, the implementation draws a hard line: **the LLM never computes a number.** Percentile calculations, safety-factor sizing, rounding rules, over/under-provisioning thresholds, confidence scoring — all of it lives in a small, deterministic, unit-tested Python module. The model's job is the conversation: asking the right follow-up questions, judging whether a workload is even in scope, writing the final report in plain language.

That separation is what made it possible to answer the obvious follow-up question — *isn't this expensive if you're running it across hundreds of workloads?* — cleanly. Because the math was already a pure function, nothing stopped us from calling that same function from a batch script instead of a conversation: pull historical metrics from Prometheus, run them through the identical engine, scan an entire namespace on a cron schedule, for the cost of a few metrics queries and zero LLM calls. Same underlying logic, two very different economics, because only one of them needed a model in the loop at all.

| | **AI Agent Skill** | **Plain script (no LLM)** |
|---|---|---|
| Cost per check | Tokens + latency, every run | Effectively free — pure code + a data query |
| Throughput | Fine for a handful of items in a session | Scans an entire fleet/repo/account in seconds |
| Handles incomplete input by | Asking a follow-up question | Degrading confidence, or excluding the item — never guessing |
| Output | Narrated explanation, in plain language | Structured data — dashboards, tickets, CI gates |
| Best interaction model | A human is actively in the loop | Scheduled, unattended, fire-and-forget |
| Auditability | Depends on the model's phrasing that run | Deterministic — same input always produces the same output |
| Handles ambiguity / policy questions | Yes — can ask what the script can't | No — must be resolved up front, or the run degrades gracefully |

## The same fork shows up everywhere

Swap "resource right-sizing" for whatever your team is actually building an AI tool for, and the same split holds:

**Code review.** Linters, static analysis, dependency and secret scanning are rule-based and cheap — they belong in CI, running on every commit, with a clean pass/fail. That's not a job for an LLM call per line of every diff; it's a job a tool like a linter or Semgrep already does deterministically. Where an AI agent earns its cost is the judgment layer on top: is this abstraction actually appropriate for this codebase's conventions, does this change match what the PR description claims it does, can someone explain *why* a flagged pattern is risky to a developer who's going to ask "yeah but why does it matter here." That's contextual reasoning a rule can't express — and it's exactly the kind of thing not worth running on every line of every commit, only on the PRs a human actually opens.

**Cloud cost analysis.** Idle-resource detection, tagging compliance, budget-threshold alerts are deterministic queries against your billing API — run them nightly across the entire account, for free, and feed a dashboard. An LLM doesn't improve a threshold comparison. What it's good for is the harder question underneath the numbers: *why* did this team's spend jump 40% this month, correlating that against a deploy history and an incident timeline, and writing the explanation a VP will actually read. Scripted anomaly detection finds the spike; an agent investigates it.

**Security checks.** CVE matching, CIS benchmark compliance, misconfiguration scanning must be deterministic — a compliance auditor needs the same input to produce the same finding every time, and non-determinism in a pass/fail security gate is a liability, not a feature. Run these as scanners, not conversations. Where an agent helps is triage: a scanner that returns 400 findings a week is not itself the deliverable — prioritizing which of those are actually exploitable in this environment, drafting a remediation PR, or explaining a specific CVE to the engineer who owns the affected service is real judgment work a scanner's rule set was never designed to do.

## A framework for the decision

Before deciding, ask these about the specific check you're automating — not about the domain as a whole:

1. **Is the core logic deterministic?** If the same inputs should always produce the same output — a threshold, a rule match, a formula — that's a function, not a conversation. Write it once, test it, and don't put a model between it and its inputs.
2. **What's the volume?** Checking one PR, one workload, one account interactively is a different cost profile than scanning every PR, every workload, every account on a schedule. Volume is usually the deciding factor on its own.
3. **Do you need reproducibility or an audit trail?** Compliance, security gates, and cost reporting want the same answer twice. If a wrong or inconsistent answer has real consequences, keep the model out of the decision path — use it only to explain a decision the deterministic layer already made.
4. **Are the inputs complete, or genuinely ambiguous?** A script can't ask a clarifying question; it has to either guess (bad) or degrade gracefully (better) when something's missing. If resolving the ambiguity requires actually talking to a human, that's where a conversational agent belongs.
5. **What does a human do with the output?** A number on a dashboard doesn't need narration. A recommendation someone has to act on, evaluate, or push back on usually does.

If the answers land on "deterministic, high-volume, needs an audit trail, inputs are known" — write the script. If they land on "judgment call, low-volume, ambiguous inputs, someone needs it explained" — that's the Skill.

## The pattern that actually works at scale

In practice, the answer usually isn't "pick one" — it's a pipeline. Run the deterministic layer continuously and cheaply across everything: every workload, every PR, every account, every night. It does the bulk computation and flags the subset that's actually worth a closer look. Route only that flagged subset — the long tail of ambiguous, high-stakes, or "someone needs this explained" cases — through the AI agent.

That's "AI for the last-mile judgment and explanation, deterministic code for the bulk computation," and it holds regardless of whether the domain is Kubernetes cost, code quality, or security posture. The expensive mistake isn't using AI — it's using it as the front door for a problem that was arithmetic the whole time.

---

*k8s-ai-skills is an open-source (Apache 2.0) exploration of what AI Agent Skills can and can't reliably do for Kubernetes operations, including both the conversational Skill and its no-LLM batch counterpart described above — code, tests, and RBAC manifests are in the [GitHub repo](https://github.com/BrandonOrigin/k8s-ai-skills).*
