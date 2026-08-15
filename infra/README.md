# Infrastructure

Infrastructure-as-code will implement the profiles in `config/deployment-profiles.yaml`.

## Planned layout

```text
infra/
  terraform/
    modules/
      oci-vm/
      proxmox-vm/
  ansible/
    roles/
      forge-host/
      hardening/
      hermes/
      docker/
      egress/
```

M0 intentionally avoids committing untested cloud/provider Terraform that looks executable but is not. M8 will add provider-specific modules with CI validation and a rebuild drill.

## Host requirements

- Ubuntu LTS or equivalent Linux
- Docker Engine + Compose plugin
- Python 3.11+ for direct controller development
- outbound access to explicitly approved model/package/source domains
- no direct inbound exposure of LiteLLM/PostgreSQL/Redis

## Reference security posture

- SSH key auth only
- firewall default deny inbound
- LiteLLM/controller bound to loopback unless fronted by authenticated gateway/tunnel
- worker network isolated from host/LAN
- automatic security updates where operationally appropriate
- persistent state backed up separately from disposable worker storage
