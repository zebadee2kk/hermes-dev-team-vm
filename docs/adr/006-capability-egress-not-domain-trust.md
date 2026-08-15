# ADR-006: External authority is capability-scoped, not domain-scoped

**Status:** Accepted

## Context
A domain allowlist can still permit exfiltration or unintended actions when an attacker supplies credentials/content targeting an otherwise approved API.

## Decision
Destination/network allowlists are defence-in-depth only. Sensitive access is authorised by scoped capabilities covering subject/task, service, resource, operation, credential binding, expiry and data policy. Trusted gateways inject credentials outside workers wherever possible.

## Consequences
GitHub/package/cloud/model access requires operation-specific broker design. `egress-allowlist.yaml` becomes a bootstrap destination registry rather than a trust policy.