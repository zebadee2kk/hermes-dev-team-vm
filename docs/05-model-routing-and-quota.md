# Model routing and quota intelligence — Revision 2

## Atomic routing unit: Inference Deployment

Route and evaluate `provider + model + account/tier + endpoint`, not provider or abstract model alone. The same provider/model can have different privacy terms, quotas, context/tool support or billing depending on tier/endpoint.

## Responsibility split

**Hermes:** requests a capability for a task/worker lane.

**Forge Compute Broker:** applies data policy, capability, measured outcomes, budget, quota state and review-independence constraints; selects an eligible deployment/runtime.

**Quota Intelligence:** interprets long-lived exhaustion/reset/health state and wake timing.

**LiteLLM:** common provider API, request execution, telemetry and short request-level retry/cooldown/fallback behaviour.

## Deployment eligibility

Exclude when any is true:
- disabled/quarantined/development-only conflict;
- deployment data policy cannot accept task sensitivity/taint;
- capability/tool/context/structured-output requirement unmet;
- `retry_at` is in future or health unacceptable;
- cost policy/authority does not permit it;
- terms/tier identity is unknown under restrictive policy;
- independent-review requirement would reuse a prohibited correlated deployment/provider.

## States

`AVAILABLE`, `THROTTLED_SHORT`, `QUOTA_EXHAUSTED`, `CREDIT_EXHAUSTED`, `PROVIDER_DEGRADED`, `OFFLINE`, `AUTH_FAILED`, `POLICY_BLOCKED`, `QUARANTINED`.

Observations store provider signal, timestamp, parsed limit, `retry_at`, confidence and provenance. Exact limits are discovered/observed rather than treated as durable constants.

## Model failover

Task identity survives model loss:

```text
Hermes task -> Task Capsule -> deployment A
                         quota exhausted
                              |
                    availability update
                              |
                    deployment B + same capsule
```

Do not depend on replaying the old chat. The capsule and workspace are the handoff boundary.

## All compute unavailable

Forge records `WAITING_COMPUTE`, Hermes blocks the task with a structured compute reason, unrelated work continues, and the scheduler wakes at the earliest credible reset plus jitter. QUIESCENT mode stops disposable Hands but leaves Brain/Session alive.

## Free compute discovery

Scheduled discovery should enumerate catalogs/pricing where available, identify free/free-credit candidates, determine actual account/tier, smoke-test, classify terms/privacy/capabilities and create probationary inference deployments. Unknown candidates remain disabled until policy evidence exists.

Prefer specifically identified free deployments for learned routing. Opaque/free-router products may be used as opportunistic fallback when exact model selection is impossible; log the actual returned model where the provider exposes it.

Never automate account creation or identity/key rotation to circumvent limits.

## Evaluation

Initial external benchmarks provide only priors. Real routing weights come primarily from this Forge's observed outcomes: anchored acceptance success, escaped defects, rework, reviewer rejection, attempts, latency and quota efficiency. Policy/privacy/security constraints are never learnable overrides.