# Threat model

## Security objective

Permit very high autonomy inside disposable engineering workers while preventing those workers, model providers, malicious dependencies or prompt-injected content from taking control of the outer system.

## Trust zones

### Zone A — owner
Trusted human decisions and authenticated administration.

### Zone B — control plane
Hermes, Forge Controller, policy, graph state, scheduler, secret broker, LiteLLM and audit. Trusted code, least privilege, no arbitrary project code execution.

### Zone C — worker sandboxes
Assume compromised. May run arbitrary package scripts, generated code and browser content. Root inside the sandbox does not imply host privilege.

### Zone D — external providers/Internet
Untrusted. Responses are data, never authority.

## Primary threats and controls

| Threat | Control |
|---|---|
| Prompt injection from web/repo/docs | tool/permission policy outside model context; treat retrieved instructions as untrusted data |
| Malicious dependency post-install script | execute only in disposable worker; network mediation; no control-plane secrets |
| Worker escapes container | non-root host daemon boundary, hardened runtime, resource/capability restrictions; evaluate microVMs before hostile multi-tenant use |
| Secret exfiltration | secret broker/scoped credentials; scrub logs; no master keys in workers |
| LAN/metadata access | proxy-only egress; RFC1918/loopback/link-local hard deny; cloud metadata deny |
| Agent disables controls | controls run outside worker and are not writable by project credentials |
| Runaway loop | max attempts/time, stagnation detection, task cancellation and budget limits |
| Free-provider quota evasion | explicitly forbidden; one owned account/key pool per provider policy |
| Silent paid fallback | paid route unavailable unless budget + authority policy explicitly enable it |
| Unsafe production action | L3 gate for production deploy/public exposure/external communication/security-boundary changes |
| Supply-chain contamination of control plane | control plane dependencies pinned/scanned separately from arbitrary project workers |
| Audit destruction | append-only/event replication target in later milestone; worker has no DB admin credential |

## Prompt-injection rule

An LLM may recommend that a domain, tool, permission or credential be added. It may not self-authorise that change. Automatic policy changes require deterministic machine-verifiable criteria already authorised by policy.

## YOLO definition

`YOLO` means broad engineering freedom **inside Zone C**: root, compilers, browsers, package managers and nested project services. It does not mean privileged access to Zones A/B, unrestricted network routing, secret stores or billing controls.

## Acceptance tests before autonomous production use

- worker cannot read control-plane environment/secrets
- worker cannot reach RFC1918/LAN or cloud metadata unless an explicit profile permits it
- prompt-injected webpage cannot add arbitrary egress domain
- exhausted quota does not trigger account/key creation
- paid inference cannot exceed policy
- L3 actions cannot execute without an owner decision record
- worker deletion/rebuild preserves project progress from Git + graph/checkpoint state
