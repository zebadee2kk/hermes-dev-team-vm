# Evaluation, learning and continuous gardening

## Outcome-based evaluation

Do not optimise activity proxies such as number of tasks, commits, lines or tokens. Primary signals are anchored acceptance success, regressions/escaped defects, rework, human rejection, security findings, latency/cost where relevant and actual project completion.

External coding benchmarks initialise priors only. Routing quality is learned mainly from this system's own real tasks and acceptance anchors.

## Learning quarantine

Project experience never writes directly into a globally trusted Skill/policy/template.

Lifecycle:
`observation -> candidate lesson -> quarantine -> offline/cross-task evaluation -> review/policy check -> promoted skill/prior OR rejected`.

Promotion records provenance, evaluation set, expected domain, expiry/revalidation criteria and rollback path. Security/Charter constraints are non-learnable.

## Capability learning

Score inference deployments and worker runtimes by task class. Maintain uncertainty/confidence and avoid overreacting to tiny samples. Detect regressions and quarantine deteriorating deployments. Keep exploration bounded so scarce free quota is not wasted merely to benchmark.

## Independent evaluation

For medium/high-risk tasks, reviewer independence is an eligibility constraint. Prefer a different deployment/provider/runtime when the expected value justifies the quota cost. Executable anchors still outrank reviewer agreement.

## Continuous gardening

Autonomous throughput creates entropy. Schedule low-priority maintenance work opportunistically, especially when cheap/local capacity is available:
- documentation freshness;
- dependency health;
- architecture-invariant checks;
- security-policy drift;
- dead code;
- test quality/flakiness;
- technical debt and duplicated abstractions;
- stale graph/evidence cleanup without deleting history.

Generated projects should carry small enforceable repository contracts (`AGENTS.md`, architecture/security/quality docs and structural tests/linters where useful) rather than relying on prose reminders alone.