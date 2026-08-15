# Operation-scoped capability grants

M4 treats external authority as a short-lived grant evaluated by trusted infrastructure. Network reachability, a successful login, or possession of a service hostname is never sufficient authority.

## Grant shape

`CapabilityGrant` binds authority to:

- one project;
- one task;
- one subject/worker identity;
- one service;
- one exact resource (`owner/repository` for GitHub);
- an explicit subset of operations;
- an exact branch when the template requires one;
- a trusted credential-binding **reference**, never credential material;
- an issue and expiry time;
- optional sensitivity/reason metadata.

The model uses `extra=forbid`, so a worker cannot add `token`, `authorization` or other undeclared credential fields to the grant object.

## GitHub task-branch write

The first write template is deliberately narrow:

```yaml
github_task_branch_write:
  operations: [branch.push, pr.create]
  resource_scope_required: true
  branch_scope_required: true
  credential_binding: trusted_gateway
  max_ttl_minutes: 30
  deny_default_branch_write: true
  allow_force_push: false
  pr_base_must_equal_default: true
```

`issue.comment` is a different authority and therefore a separate template; it is not smuggled into a branch grant.

For each attempted GitHub write, the trusted broker must supply current context and call `authorize(...)`. Authorization requires an exact match for project, task, subject, service, repository and operation. Branch-scoped operations additionally require the exact granted branch and the repository's current default branch.

Hard rules for this template:

1. no direct push to the default branch;
2. no force push;
3. PR head must be the exact task branch;
4. PR base must be the current default branch;
5. no operation that was not explicitly included when the grant was issued;
6. expired, future or revoked grants fail closed;
7. a worker cannot choose or alter the credential binding;
8. the grant itself contains no token/key/cookie/password.

## Credential boundary

This module authorises an operation but does **not** resolve a secret. `AuthorizedCapability.credential_binding` tells the trusted broker which host-side credential binding may be used after authorization.

The eventual GitHub broker must therefore follow this order:

```text
worker request
  -> validate task/capsule identity
  -> authorize CapabilityGrant
  -> resolve trusted credential binding host-side
  -> perform exact GitHub operation
  -> discard request-scoped credential material
  -> record audit/event + Reality Anchor where appropriate
```

Never return the resolved credential to the Hand, put it in the workspace, inject it as a long-lived worker environment variable, or configure a general Git credential helper accessible to the worker.

## Trust is separate from authority

`config/capability-policy.yaml` keeps external-content trust classification in `content_trust_bindings`, separate from capability templates. An operation being authorised does not make content returned by that service trusted. GitHub files, PR text, issue comments and web responses still enter through the Content Trust Gateway as external content.

## Next implementation slice

The authorization contract is the policy core. The next M4 slice is a trusted GitHub broker transport that:

- accepts only structured operations rather than arbitrary URLs or shell commands;
- resolves the repository default branch itself;
- performs `branch.push` and `pr.create` with a trusted credential binding;
- verifies the pushed head SHA / created PR as executable evidence;
- never exposes GitHub credentials to the Hand.
