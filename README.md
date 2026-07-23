# k8s-ai-skills
A collection of production-grade AI Skills for Kubernetes Platform Engineering.

`k8s-ai-skills` is an open repository of reusable AI Skills that help analyze Kubernetes resources, identify operational issues, and generate actionable recommendations.

The goal of this project is to explore how Large Language Models (LLMs) can assist platform engineers by encapsulating Kubernetes operational knowledge into reusable, transparent, and verifiable Skills.

—

## Why this project?

Modern AI coding assistants support reusable Skills through `SKILL.md`, allowing domain knowledge to be packaged into structured instructions.

Instead of building another Kubernetes tool, this project focuses on answering a more fundamental question:

> **Can AI Skills reliably perform real-world Kubernetes operational analysis?**

Each Skill is designed, tested, and refined against practical Kubernetes scenarios to understand:

- What information should be collected?
- What prompts produce the most reliable results?
- Where do LLMs make mistakes?
- What recommendations are actually useful for platform engineers?

The lessons learned here may eventually inform future AI tooling, but this repository is intentionally focused on experimentation and knowledge sharing.

—

## Project Goals

- Build production-oriented Kubernetes AI Skills
- Evaluate the strengths and limitations of LLM-based analysis
- Capture Kubernetes operational best practices in reusable Skills
- Share prompts, examples, and evaluation results with the community

—

## Repository Structure

```text
skills/
    dockerfile-rightsize/
    namespace-security/
    deployment-review/
    resource-rightsize/
    ingress-review/

examples/
    sample-inputs/
    generated-reports/

docs/
    design-notes.md
    evaluation.md
```

—

## Skill Lifecycle

Every Skill follows a simple workflow:

```text
Collect Facts
      ↓
Prepare Context
      ↓
AI Analysis
      ↓
Generate Report
      ↓
Human Review
```

Each Skill documents:

- Purpose
- Required inputs
- Analysis instructions
- Expected outputs
- Known limitations
- Example reports

—

## Design Principles

- Markdown-first
- Human-readable
- AI-friendly
- Vendor-neutral
- Reproducible
- Production-oriented

—

## Current Status

🚧 This project is in its early research phase.

The current focus is validating whether AI Skills can consistently provide valuable Kubernetes operational insights before introducing any execution framework or automation.

—

## Contributing

Contributions are welcome.

Ideas include:

- New Kubernetes Skills
- Improved prompts
- Better evaluation methods
- Sample manifests
- Real-world case studies
- Report improvements

—

## License

Apache License 2.0