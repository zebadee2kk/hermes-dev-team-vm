# Deployment profiles — Revision 2

The application architecture is portable; profiles change resource ceilings, sandbox strength, ingress, data routing and recovery policy. All profiles preserve Brain / Session / Hands separation.

## Local trusted / Proxmox

Preferred full-capability engineering profile. Local Ollama may handle routine work. Normal autonomous arbitrary-code Hands still use gVisor where supported because trusted infrastructure does not make generated/package code trustworthy.

Starting point: 4 vCPU, 12–16 GB RAM, 80+ GB disk. Increase resources based on concurrent builds rather than model inference, which is normally remote.

## OCI Always Free / low-cost ARM

Treat the host as disposable. Current resource assumptions remain profile metadata and must be revalidated at deployment time.

Design rules:
- arm64 multi-arch images;
- gVisor/runtime support validated on the chosen kernel/image;
- one heavy Hand by default;
- no dependency on local LLM inference;
- resource-conscious Hermes/PostgreSQL/Redis/LiteLLM/Forge;
- persistent state backed up/replicated so host reclamation does not lose project progress;
- automated rebuild using Terraform/Ansible plus encrypted state restore.

## Portable laptop VM

Same logical topology with smaller concurrency. Local models are optional. LAN access stays deny-by-default for Hands even when the VM runs on a trusted home/client network.

## Cloud isolated

Strict control plane; no implicit LAN trust. Public ingress is denied except a deliberately mediated owner interface/tunnel. All Hand egress is through the capability/network gateway.

## Client safe

Use a restrictive data-routing profile, approved inference deployments only, stronger isolation where client policy requires it, and explicit connector/repository scopes. Public/free inference remains PUBLIC-only unless the exact deployment terms and client policy allow more.

## Recovery objective

The VM is not the system of record. A replacement host must be reconstructable from:
1. Git/release/IaC;
2. encrypted PostgreSQL/Forge state backup;
3. Hermes/Kanban/session backup as required by upstream storage layout;
4. append-only event replication/checkpoint;
5. secrets restored separately from a trusted vault/broker.

M8 is not complete until a checkpointed project resumes on a rebuilt host.

## Portability requirements

- amd64 + arm64 controller images;
- no cloud-specific assumptions in domain code;
- sandbox runtime selected by profile/capability detection;
- configuration from versioned non-secret policy + external secrets;
- backup/restore tested independently of VM provider;
- workers/Hermes must tolerate runtime concurrency being reduced to one.