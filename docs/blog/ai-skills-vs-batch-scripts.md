# AI Agent Skills vs. Batch Scripts: Picking the Right Tool for Kubernetes Resource Right-Sizing

A question came up while building [k8s-ai-skills](https://github.com/BrandonOrigin/k8s-ai-skills), an open-source library of Claude Agent Skills for Kubernetes platform engineering: if you're running hundreds of workloads across dozens of namespaces, isn't it expensive to call an LLM every time you want a resource right-sizing recommendation?

The honest answer is yes — if you're using the LLM for the wrong part of the job. The more interesting answer is that the question exposes a design decision every "AI-powered ops tool" eventually has to make: **what should the model actually be doing?**

## The insight: separate the math from the judgment

The first version of the right-sizing Skill made a deliberate architectural choice: the LLM never computes a number itself. Percentile calculations, safety-factor sizing, rounding rules, over/under-provisioning thresholds, memory-trend detection, confidence scoring — all of it lives in a small, deterministic Python module (`calc.py`) with a unit test for every formula. The model's job is the conversation: asking a platform engineer the right follow-up questions, deciding whether a workload is even in scope, and writing the final report in plain language.

That separation turned out to be the key to answering the cost question, because it meant the "expensive" part — the LLM call — was never where the actual computation happened. Once the math is already a pure function, nothing stops you from calling that same function a thousand times a night without an LLM anywhere in the loop. That's exactly what we built as a companion: a batch script that pulls historical CPU/memory data from Prometheus, runs it through the identical `calc.py`/`schema.py` engine, and produces a report for every workload in a namespace — for the cost of a few Prometheus queries.

Two tools, same underlying engine, very different economics. Here's how they actually compare.

## Head-to-head

| | **AI Skill (Claude Code)** | **Batch script (no LLM)** |
|---|---|---|
| Cost per workload | LLM tokens + latency | Effectively free — pure Python + one metrics query |
| Throughput | Fine for a handful of workloads in a session | Scans an entire namespace or fleet in seconds |
| Handles incomplete data by | Asking a follow-up question | Degrading confidence, or excluding the container — never guessing |
| Output | Narrated Markdown report, in plain English | Structured JSON, ready for dashboards, tickets, or CI gates |
| Best interaction model | A human is actively in the loop | Scheduled, unattended, fire-and-forget |
| Auditability | Depends on report quality and phrasing | Deterministic — same input always produces the same output |
| Handles ambiguity / policy questions | Yes — can ask "does your platform require limits?" | No — must be supplied up front via config, or the run degrades gracefully instead of guessing |

The two are not competitors so much as two different consumers of the same deterministic core. That core doesn't change; only who's driving does.

## When to reach for the AI Skill

Use the conversational Skill when a human is genuinely in the loop and the value is in judgment or explanation, not raw throughput:

- **A developer is investigating one workload** and wants to understand *why* a number is what it is, push back on an assumption, or ask "what if I added an HPA?"
- **The inputs are incomplete or ambiguous.** Nobody's sure whether the platform enforces a limit ratio, or what the DaemonSet's actual node count is. A script can't ask; a conversation can.
- **You need a narrated, shareable report** — something you'd paste into a Slack thread or attach to a PR description, not just a number in a spreadsheet.
- **The workload doesn't fit the mold.** A CronJob, a VM, a manifest with no live metrics — cases that need judgment about whether the analysis even applies.

## When to reach for the batch script

Use the deterministic, no-LLM path when volume and repeatability matter more than nuance:

- **You're scanning an entire fleet on a schedule.** A nightly CronJob across every namespace in a large cluster is exactly the workload an LLM-per-container approach can't afford, and doesn't need to.
- **You want it wired into CI/CD.** A batch script has a clean exit code and structured JSON output — it can gate a pull request or fail a pipeline. A conversation can't.
- **You need deterministic, reproducible numbers.** Compliance and cost-review processes want the same input to always produce the same output, with no variance introduced by a model's phrasing.
- **The policy questions are already known.** If your organization's limit-to-request ratio is a fixed, documented rule, there's no ambiguity left for a conversation to resolve — it's just a lookup.

## The real answer is usually both

In practice, the two form a pipeline rather than a choice. Run the batch script nightly across the whole fleet at near-zero marginal cost — it flags the workloads worth a closer look (active under-provisioning, OOM risk, stale requests) and produces an audit trail. Reserve the AI Skill for the long tail: the handful of flagged workloads each week where a human actually wants to sit down, ask questions, and get a narrated explanation, or where the platform's own policy is genuinely unresolved.

That's "AI for the last-mile judgment and explanation, deterministic code for the bulk computation" — and it's a pattern worth generalizing well beyond Kubernetes right-sizing. Any time you're tempted to route every request through an LLM, it's worth asking: how much of this task is actually a judgment call, and how much of it is math that's just been dressed up as one?

---

*k8s-ai-skills is an open-source (Apache 2.0) exploration of what AI Skills can and can't reliably do for Kubernetes operations — code, tests, and both implementations of the right-sizing analysis are in the [GitHub repo](https://github.com/BrandonOrigin/k8s-ai-skills).*
