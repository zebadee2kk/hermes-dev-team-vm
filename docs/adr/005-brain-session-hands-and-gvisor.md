# ADR-005: Separate Brain, Session and Hands; gVisor is the normal autonomous worker boundary

**Status:** Accepted

## Context
Autonomous workers run generated code, package scripts and browser content and must be assumed compromised. Reasoning, durable state and arbitrary execution should fail independently.

## Decision
Separate Brain (Hermes/Forge reasoning/policy), Session (Kanban/DB/Git/event state) and Hands (disposable execution). On supported Linux, normal autonomous arbitrary-code Hands use gVisor. A stronger VM/microVM boundary is available for high-risk profiles; low-risk trusted tasks may use weaker rootless isolation. Never mount the host Docker socket into Hands.

## Consequences
Worker rebuilds and model swaps are ordinary recovery operations. Nested/container service needs should use a sandbox broker or explicitly supported contained mechanism rather than host-control interfaces.