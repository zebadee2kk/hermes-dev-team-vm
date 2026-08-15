# Trusted GitHub capability broker

This is the first generic external-write broker for M4. It turns an authenticated Forge capability grant into one exact GitHub operation without giving the Hand a GitHub credential or arbitrary API client.

## Boundary

The worker may carry a `CapabilityGrantEnvelope`, but the envelope is HMAC-authenticated by Forge. A structurally valid raw grant is not authority. The broker verifies the envelope, checks revocation and runs `preauthorize(...)` before it performs even the repository-metadata lookup.

The broker then resolves facts the worker must not control:

- repository default branch from GitHub;
- task workspace from a trusted `workspace_resolver`;
- expected Git common directory from trusted workspace state;
- actual workspace HEAD/cleanliness from Git itself.

## Push flow

```text
signed grant envelope
 -> authenticate envelope + revocation
 -> pre-authorize project/task/subject/repo/branch/branch.push
 -> mint repo-scoped metadata-read installation token
 -> resolve current default branch
 -> full authorization (default-branch push forbidden)
 -> resolve trusted workspace
 -> verify top-level, git-common-dir, clean tree, expected HEAD
 -> reject dangerous local Git config
 -> mint repo-scoped Contents:write installation token
 -> host-side git push HEAD -> exact granted task branch
 -> revoke write token
 -> mint repo-scoped Contents:read token
 -> verify remote branch SHA == authorized HEAD
 -> revoke verification token
```

The Git command uses:

- an absolute trusted Git binary;
- an absolute root-owned askpass helper;
- no worker/global Git configuration;
- `core.hooksPath=/dev/null`;
- no credential helper;
- `--no-verify` to avoid workspace-controlled push hooks;
- a fixed `https://github.com/<owner>/<repo>.git` destination;
- `HEAD:refs/heads/<exact granted branch>`;
- the installation token only in the trusted subprocess environment.

The broker rejects local Git config capable of rewriting/proxying credentials or execution (`include*`, `url.*`, `credential.*`, `http.*`, `protocol.*`, `core.sshCommand`, `core.hooksPath`, remote proxy settings).

## Pull-request flow

The worker cannot select the PR base. The broker resolves the current default branch, verifies the granted remote head SHA, then creates a PR from the exact task branch to that default branch with a repository-scoped `Pull requests: write` installation token. The response is checked against repository, head ref/SHA and base ref before it is accepted.

## GitHub App credential source

`GitHubAppTokenProvider` expects a root-owned, mode-0600 private key and a configured installation owner/id. It generates an App JWT only inside the trusted process, asks GitHub for an installation token reduced to the exact repository and requested permissions, and never serializes the returned token into Forge contracts.

Current GitHub documentation states that installation access tokens can be limited to selected repositories and reduced permissions, expire after one hour, can authenticate HTTP Git when the App has Contents permission, and can be revoked through the installation-token API. The broker revokes every request-scoped token after use rather than relying on natural expiry.

## Deployment prerequisites

Before enabling this broker on a real Forge host:

1. create/install a dedicated GitHub App on the repositories Forge may manage;
2. grant only the App permissions required for the broker operations (initially Contents and Pull requests);
3. place the App private key outside project/workspace mounts, root-owned and mode 0600;
4. install `infra/github/git-askpass.sh` root-owned, executable and non-writable by service/worker identities;
5. run the broker under a dedicated trusted service identity; Hands must not share its PID namespace or environment;
6. back `workspace_resolver` from Forge/Hermes trusted task state, never a path supplied by the worker;
7. produce live Reality Anchors for scope denial, token non-disclosure/revocation, exact branch push and PR creation before declaring the GitHub write capability production-ready.

The broker is intentionally not an arbitrary GitHub REST forwarding proxy. Additional GitHub operations require new typed requests, capability templates and negative tests.
