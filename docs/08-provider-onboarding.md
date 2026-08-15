# Provider onboarding

Adding a free API provider is a controlled engineering change, not just adding an API key.

## Checklist

1. Confirm provider is permitted and account/key is owned by the operator.
2. Record cost class (`free_api`, `local`, `paid`, `trial`, `promotional`).
3. Review current data retention/training/privacy terms; assign privacy class conservatively.
4. Identify supported model/catalog endpoint and features.
5. Implement quota/error adapter using documented headers/error bodies.
6. Implement health probe and smoke test.
7. Add model capability discovery/benchmarks.
8. Add egress domains.
9. Add tests for exhaustion, auth failure and reset.
10. Enable in `config/providers.yaml` only after validation.

## Free-tier rule

Free tiers are legitimate capacity, but the system must not create extra accounts, rotate identities or otherwise evade service quotas. Promotional/free-trial capacity is opportunistic and may not be treated as a continuity dependency.

## Privacy rule

Unknown terms => `public_only`. A model's benchmark score can never upgrade its data classification.

## Model catalogue churn

Do not hardcode a list of fashionable model names into application logic. Provider adapters should discover current candidates and the capability graph should determine fit. Configuration may hold explicit pins for testing/reproducibility, but discovery is the normal production path.
