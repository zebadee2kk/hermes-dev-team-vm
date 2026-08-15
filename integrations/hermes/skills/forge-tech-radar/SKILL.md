---
name: forge-tech-radar
description: Triage and test new agent technology before adoption.
platforms: [linux, macos, windows]
---

# Forge Technology Radar

Use this Skill when new frameworks, protocols, model runtimes, memory systems, security findings or agent techniques appear worth investigating.

## Filter first

Do not equate novelty or social engagement with signal. Prefer evidence in this order:

- primary specification, repository, gist, paper or advisory;
- reproducible artifact;
- production deployment/postmortem;
- measurable outcomes;
- independent corroboration;
- credible security research.

Rumor-only, marketing-only or artifact-free claims normally stay `ignore` or `watch`.

## Candidate workflow

A technology that reaches `test` becomes a structured candidate, not a dependency:

`observed -> triaged -> sandbox_tested -> probation -> promoted | rejected`

Record the problem it solves, integration seam, replacement scope, acceptance criteria, test plan, risks and rollback path.

## Experiments

1. Create a Hermes Kanban task and Task Capsule for the experiment.
2. Use the Sandbox Broker for executable third-party code.
3. Test against a real Forge/Hermes workflow where practical, not only the vendor demo.
4. Record cost, latency, regressions, compatibility and security observations.
5. Record executable Reality Anchors for passing claims.
6. Write a `CandidateEvaluation` record.

Promotion is prohibited until configured probation/evidence gates pass. An agent may recommend promotion, but cannot waive Owner Charter, security or human-decision gates. Frameworks that duplicate Hermes Kanban, Forge routing, assurance, observability or sandbox boundaries carry a high replacement burden and should be rejected unless they demonstrate a specific missing primitive.
