# ADR-0001: Separate trusted control plane from YOLO workers

**Status:** Accepted

## Context
The system needs broad autonomy to install packages, run browsers, compile code and modify development environments. Giving the same process unrestricted access to secrets, policy and audit makes its guardrails self-modifiable.

## Decision
Run arbitrary/generated project work in disposable worker sandboxes. Permit root inside those sandboxes when the deployment profile allows it. Keep Hermes control logic, Forge, secrets, policy, quota/budget controls and durable state outside and inaccessible to worker credentials.

## Consequences
- More sandbox lifecycle engineering.
- Stronger containment and simpler recovery.
- A worker may be destroyed/rebuilt without destroying project/control state.
- Container isolation must be hardened and may later be replaced by microVMs for higher-threat deployments.
