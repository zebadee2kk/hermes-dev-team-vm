# Deployment profiles

The application architecture is portable; deployment profiles change trust, resources and network policy.

## Local trusted / Proxmox

Preferred full-capability profile. Local Ollama may service routine tasks. The VM still denies arbitrary LAN access by default because project workers are untrusted.

Suggested starting allocation: 4 vCPU, 12–16 GB RAM, 80+ GB disk; scale workers independently based on build workload.

## OCI Always Free

Current Oracle documentation describes the Always Free Ampere A1 allowance as 1,500 OCPU-hours and 9,000 GB-hours monthly, equivalent for an Always Free tenancy to **2 OCPUs and 12 GB RAM total**, plus Always Free block-storage allocation. The instance is ARM.

Design implications:

- multi-arch images only;
- one heavy worker at a time by default;
- no useful local LLM expectation;
- PostgreSQL/Redis/LiteLLM/controller/Hermes must be resource-conscious;
- keep source/state recoverable because Oracle documents reclamation of idle Always Free compute under its policy.

Always validate the current OCI terms/limits at deployment time.

## Portable laptop VM

Same logical topology, smaller concurrency. Local models may be enabled when host resources support them.

## Cloud isolated

No LAN trust. Public ingress denied except explicitly mediated owner UI/tunnel. Workers receive proxy-only outbound network.

## Client safe

Free/public providers are restricted to PUBLIC data unless provider terms and client policy explicitly permit more. Prefer local/approved enterprise inference for confidential work. Worker privilege may be reduced.

## Portability requirements

- arm64 + amd64 controller images
- configuration through environment/profile files
- no cloud-specific assumptions in domain code
- backup/restore scripts tested independently of VM provider
