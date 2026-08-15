import ipaddress

import pytest

from forge_controller.capability_proxy import CapabilityProxyPolicy


def policy() -> CapabilityProxyPolicy:
    return CapabilityProxyPolicy({"chatgpt.com", "auth.openai.com"})


def test_codex_proxy_allows_only_exact_openai_https_targets() -> None:
    target = policy().parse_target("chatgpt.com:443")
    assert target.host == "chatgpt.com"
    assert target.port == 443

    device_auth = policy().parse_target("AUTH.OPENAI.COM.:443")
    assert device_auth.host == "auth.openai.com"


@pytest.mark.parametrize(
    "authority",
    [
        "chatgpt.com:80",
        "evil.example:443",
        "sub.chatgpt.com:443",
        "1.1.1.1:443",
        "[2606:4700:4700::1111]:443",
        "user@chatgpt.com:443",
        "chatgpt.com",
    ],
)
def test_codex_proxy_rejects_out_of_scope_authorities(authority: str) -> None:
    with pytest.raises((PermissionError, ValueError)):
        policy().parse_target(authority)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
    ],
)
def test_codex_proxy_rejects_private_loopback_and_metadata_resolution(address: str) -> None:
    with pytest.raises(PermissionError):
        policy().validate_resolved_ip(address)


def test_codex_proxy_accepts_globally_routable_resolution() -> None:
    address = "8.8.8.8"
    assert ipaddress.ip_address(address).is_global
    assert policy().validate_resolved_ip(address) == address
