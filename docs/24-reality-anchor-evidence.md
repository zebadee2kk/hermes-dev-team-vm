# Reality Anchor evidence ingestion

Forge treats executable evidence as stronger than model opinion. This document defines the first machine path from a live report into a persisted `RealityAnchor`.

## Command

The package exposes:

```bash
forge-evidence --input REPORT.json [options]
```

The command validates the report, constructs a typed `RealityAnchor`, prints the anchor JSON, optionally writes it with `--output`, and optionally POSTs it to the controller's `/v1/anchors` endpoint with `--submit-url`.

By default, submission is allowed only to loopback (`localhost`, `127.0.0.1`, `::1`). A remote controller requires the explicit `--allow-remote-controller` flag so evidence cannot silently leave the host.

## Hash binding

Every source report is read as bytes and SHA-256 hashed before the anchor is created. The anchor records:

- the absolute source file path;
- the source report kind;
- the SHA-256 digest in `environment.evidence_sha256`;
- a `file://...#sha256=<digest>` artifact reference.

Changing the source report after anchor creation therefore breaks the recorded binding and must be treated as new evidence.

## Positive-anchor rule

`forge-evidence` does not turn a failed report into a passing Reality Anchor.

Known report adapters define their required success field:

| report kind | required field | anchor type | default claim |
|---|---|---|---|
| `forge-sandbox-live-smoke` | `passed == true` | `sandbox_compromise_smoke` | `M4:normal-hand-isolation` |
| `forge-codex-probation-preflight` | `ready == true` | `codex_app_server_preflight` | `Probation-001:codex-app-server-preflight` |

A negative security test should itself report `passed: true` only when the forbidden action was successfully denied. The evidence semantics describe whether the test passed, not whether the attempted unsafe action succeeded.

Unknown report kinds are permitted only when the caller supplies explicit `--project-id`, `--task-id`, `--type`, `--claim-ref` and `--executor` semantics. They still require an aware ISO-8601 `observed_at` and a passing boolean field (`--pass-field`, default `passed`).

## Credential hygiene

Before persistence, the evidence loader recursively rejects obvious credential-bearing JSON fields, including:

- `token` / `access_token` / `refresh_token`;
- `authorization`;
- `password`;
- `secret`;
- `api_key` / `apikey`;
- `cookie`.

This is a deterministic guard, not a complete secret scanner. Live probes must still avoid printing credentials in arbitrary strings, stderr, stack traces or filenames.

The Codex device-login flow intentionally does **not** use this generic report path for the displayed device code. Authentication state stays in the dedicated Codex volume; no token or transient login code should be stored in Forge evidence.

## Probation 001 pre-device collection

After the normal Hand image, Codex bridge/shim, internal proxy and probation workspace exist:

```bash
export FORGE_NORMAL_HAND_IMAGE='sha256:<normal-hand-image-id>'
export FORGE_CONTROLLER_URL='http://127.0.0.1:8000'  # optional
infra/sandbox/probation-001-preflight-evidence.sh
```

This produces four files under `/var/lib/forge/evidence/probation-001` by default:

```text
normal-hand-smoke.report.json
normal-hand-smoke.anchor.json
codex-preflight.report.json
codex-preflight.anchor.json
```

If the controller URL is supplied, both validated anchors are also persisted through the normal assurance API.

The script stops before the explicit ChatGPT device-authentication gate. After authentication, collect the remaining proxy, host-control, secret-boundary, cleanup and rollback evidence described in `docs/23-codex-capability-egress.md`.

## Freshness and task binding

A useful Reality Anchor must be bound to the exact project/task/workspace state it claims to verify. Prefer a repository commit or equivalent immutable workspace identifier via `--workspace-revision` for real probation workloads.

Do not reuse an anchor when any of these materially change:

- Hand or Codex image digest;
- gVisor/Docker/runtime configuration;
- capability proxy policy;
- workspace revision;
- acceptance criteria;
- security policy relevant to the claim.

Those changes require re-execution and a new observed timestamp/digest.
