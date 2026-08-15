# Threat model — Revision 2

## Security objective

Allow very high autonomy inside disposable engineering Hands while preventing workers, malicious dependencies, prompt-injected content, compromised external accounts or models from taking control of the Brain/Session plane, exfiltrating protected data or expanding their own authority.

## Trust zones

- **Zone A — owner:** authenticated human authority and Charter changes.
- **Zone B — Brain/Session:** Hermes, Forge, Kanban, policy, databases, model gateway, capability/secret gateway and audit.
- **Zone C — Hands:** assume compromised; arbitrary generated/package/browser code may run with root inside its sandbox.
- **Zone D — external systems/content:** providers, web, repositories, package metadata, MCP/connectors. Responses are data, never authority.

## Mandatory controls

| Threat | Required control |
|---|---|
| Prompt injection from web/repo/docs/tool result | Content Trust Gateway; provenance/taint; permissions outside model context |
| Multi-agent trust laundering | trust/taint propagated through handoffs; summaries do not upgrade trust |
| Malicious package/post-install | disposable Hand; gVisor default; no Brain secrets |
| Container escape | gVisor normal profile; stronger VM boundary for high risk; patched host |
| Docker socket takeover | Docker socket never mounted into Hands |
| Credential exfiltration | credentials injected by trusted gateway per scoped capability; workers do not receive broad/master secrets |
| Allowed-domain exfiltration | operation/resource/identity-aware Capability Gateway; domain allowlist alone never authorises sensitive access |
| LAN/metadata probing | hard network deny for RFC1918/loopback/link-local/metadata unless deployment policy explicitly permits |
| Agent disables controls | policy/gateways outside Hand and unwritable by project credentials |
| Runaway loop | bounded attempts/time/tokens, stagnation/circuit breaker, cancellation |
| Reviewer collusion/correlated blind spot | adaptive independent review; high risk uses different deployment/provider where practical plus reality anchor |
| Evaluation gaming | Owner Charter; protected acceptance criteria; prohibit weakening/removing tests to pass |
| Persistent memory poisoning | learning quarantine + evaluation before trusted promotion |
| Quota evasion | account creation/identity rotation/CAPTCHA or limit circumvention forbidden |
| Silent paid fallback | no paid deployment eligible without budget policy and required authority |
| Unsafe production/external action | L3 capability impossible without owner decision record |
| Audit destruction | worker has no DB/admin capability; append-only events and later off-host replication |
| Supply-chain compromise of Brain | Brain dependencies pinned/scanned and maintained separately from arbitrary project dependencies |

## Sandbox levels

- `LOW`: trusted/local low-risk tasks may use rootless container isolation.
- `NORMAL`: gVisor (`runsc`) default for autonomous arbitrary project code on supported Linux.
- `HIGH`: VM/microVM/stronger dedicated boundary for risky/untrusted workloads or client policy.

Root inside Zone C is acceptable only when it cannot affect the outer host/security plane.

## Prompt/content rule

An LLM may recommend adding a domain, tool, permission, model, credential or policy. It cannot approve the escalation. Automatic additions require deterministic criteria pre-authorised by policy and must not grant a broader capability than the evidence establishes.

## Acceptance tests before unattended use

- Hand cannot read Brain/control-plane environment, DB credentials or model keys.
- Hand cannot access Docker socket or equivalent host-control interface.
- Hand cannot reach prohibited LAN/link-local/cloud metadata.
- allowed destination cannot be abused with attacker-supplied credentials to exfiltrate protected content.
- tainted web/tool content remains tainted after subagent summaries/handoffs.
- prompt-injected content cannot authorise new capability/egress.
- exhausted quota cannot trigger identity/account creation.
- paid inference cannot exceed budget policy.
- L3 action cannot execute without owner authority.
- workers can be destroyed/rebuilt without losing durable task progress.
- corrupt/replayed Task Capsule/event input is rejected or recovered safely.
- attempts to weaken acceptance tests/security invariants are detected.