# Content trust, capabilities and secure handoffs

## Content Trust Envelope

Every externally influenced artefact passed into an agent should carry metadata:
- source/provenance;
- acquisition tool/time;
- trust level;
- taint labels (web, repository, package, user-supplied, generated, connector, etc.);
- data sensitivity;
- integrity/hash where useful;
- prompt-injection/suspicion findings;
- transformation lineage.

A summary inherits the strongest relevant taint of its source. `researcher -> architect` does not magically turn untrusted web instructions into trusted internal policy.

## Authority order

Owner Charter / protected policy > explicit owner decision > repository-local protected project policy > trusted system contracts > ordinary agent output > external/retrieved content.

No content from a lower tier can instruct an agent to alter a higher tier.

## Capability Gateway

Network destination is not authority. Sensitive actions require a capability grant that scopes:
- requesting subject/task;
- service/destination;
- resource (for example one repository/project);
- operation/method;
- credential binding managed outside Hand;
- expiry/one-shot/usage limits;
- data classification permitted;
- audit requirements.

Example: `git.push` to repository X and branch `forge/T184`, not generic `github.com` access.

## Secret injection

Prefer brokers/proxies that add credentials after policy validation. If a tool cannot operate without a secret inside the Hand, issue the narrowest short-lived credential possible, prevent prompt/log exposure and revoke it at task end. Master provider and repository credentials stay in Zone B.

## Destination controls

Retain DNS/IP/domain/network filtering as defence-in-depth, including hard deny of metadata/link-local/RFC1918 unless profile allows it. `config/egress-allowlist.yaml` is therefore a bootstrap destination registry, **not a trust list**.

## Auto-add policy

Automatic destination additions require a deterministic pre-authorised trust chain and must result in a narrow capability. An LLM confidence score can never be the sole basis for auto-authorisation.

## Denial semantics

Policy returns `DENIED(reason, alternatives, retry/escalation_hint)`. Worker should continue using allowed alternatives. Repeated denial loops trigger a circuit breaker and, only when material, an owner decision.