# General secret / credential binding broker

M4 does not expose a general `get_secret` API to Hermes or Hands. Credentials are a trusted-gateway implementation detail selected only after capability authorization.

## Model

`AuthorizedCapability` already carries a non-secret `credential_binding` reference. `CredentialBindingRegistry` maps that reference plus service to:

- permitted operations;
- optional exact resources;
- one systemd credential filename;
- a maximum credential size.

The registry itself contains **no secret values** and must be owned by the trusted host administrator/control plane and not group/world writable.

`SystemdCredentialSecretBroker` then resolves the referenced file only from the service's systemd `CREDENTIALS_DIRECTORY`. The credential file must:

- be a regular file;
- be owned by root or the trusted service identity configured for the broker;
- have no group/world permissions;
- stay below the binding-specific size limit;
- be non-empty.

Path traversal is prevented by requiring the configured credential name to be a leaf filename and resolving it beneath the fixed systemd credential directory.

## No worker secret endpoint

There is intentionally no FastAPI/MCP/UDS method that returns a secret. Trusted broker code obtains a short-lived `SecretLease` only after it already holds an `AuthorizedCapability`.

A `SecretLease`:

- redacts its representation;
- holds the source bytes in a mutable buffer;
- refuses reads after close;
- overwrites that mutable buffer on context exit/close.

Python or downstream libraries may create their own copies when a trusted gateway converts the buffer to `bytes`/`str`; those copies cannot be reliably zeroized by this component. Therefore this primitive is for **trusted in-process adapters only**, never ordinary agent code.

## Example

Non-secret registry:

```yaml
version: 1
bindings:
  - binding_id: trusted_gateway
    service: github
    operations: [branch.push, pr.create]
    credential_name: github-app-private-key
    resources: [zebadee2kk/hermes-dev-team-vm]
```

Trusted adapter usage:

```python
with secret_broker.lease(authorized_capability) as lease:
    private_key = lease.text_copy()
    # use inside trusted adapter only; never return/log/store it
```

The production GitHub service already follows the stronger concrete version of this model by receiving its App private key through systemd `LoadCredential=` and minting short-lived installation tokens inside the trusted process. LiteLLM remains the analogous credential boundary for inference providers.

## Security invariant

An approved destination is not authority, and a credential binding is not authority. The required order is:

```text
signed grant
 -> capability authorization
 -> binding/service/operation/resource match
 -> trusted credential resolution
 -> exact service operation
 -> discard/revoke transient credential state
 -> audit / Reality Anchor
```

No component may reverse that order by fetching a secret first and asking policy afterward.
