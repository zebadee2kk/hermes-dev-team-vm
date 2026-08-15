# Model routing and quota intelligence

## Responsibility split

**LiteLLM:** common API surface, request execution, short retries/fallbacks/cooldowns, usage/cost telemetry.

**Forge:** long-lived provider availability truth, quota-reset interpretation, capability/privacy policy, task placement and `WAITING_COMPUTE` scheduling.

This prevents a daily-exhausted provider being retried every short cooldown interval.

## Routing eligibility

A candidate is excluded if any is true:

- disabled or quarantined
- privacy class cannot accept task sensitivity
- capability below threshold
- required tool/response mode unsupported
- `retry_at` is in the future
- paid route exceeds current budget or lacks required gate
- provider terms/status are unknown under a restrictive policy

Eligible deployments are scored by capability, reliability, availability, latency/cost/locality policy and historical task outcomes.

## Provider states

`AVAILABLE`, `THROTTLED_SHORT`, `QUOTA_EXHAUSTED`, `CREDIT_EXHAUSTED`, `PROVIDER_DEGRADED`, `OFFLINE`, `AUTH_FAILED`, `POLICY_BLOCKED`.

## Observations

Adapters ingest HTTP status, provider error codes and rate-limit headers. Reset times must record provenance and confidence. Generic `Retry-After` is honoured. Provider-specific headers can classify a true daily/token exhaustion more precisely.

Examples of useful signals include Groq remaining/reset headers and OpenRouter `Retry-After` on 429/503 responses. Exact limits are never hardcoded as durable truth because account/model limits change.

## Failure sequence

```text
agent role -> candidate A
           -> quota exhausted
           -> checkpoint + availability update
           -> candidate B
           -> success
```

The agent role, project node and working state are unchanged by model failover.

## All compute unavailable

1. node -> `WAITING_COMPUTE`;
2. compute earliest credible retry time across otherwise-compatible deployments;
3. continue unrelated graph nodes if possible;
4. when no runnable work remains, enter QUIESCENT mode and stop disposable workers;
5. wake timer re-evaluates current state rather than blindly retrying the old model.

## Free compute discovery

A scheduled discovery job should query provider model/catalog/pricing endpoints where supported, detect zero-cost/free-tier candidates, run a smoke test, classify capabilities/terms and add candidates as disabled or probationary until policy permits them.

Never automate account creation or use multiple identities/keys to circumvent quotas.

## Benchmarking

Combine controlled micro-benchmarks with actual outcomes: tests passed, review result, retries, reverts, human rejection, latency and task type. Historical performance may influence routing but can never override data sensitivity or budget/security policy.
