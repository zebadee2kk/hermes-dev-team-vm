from pathlib import Path

import yaml

from forge_controller.sandbox import SandboxLimits

ROOT = Path(__file__).parents[1]


def test_normal_profile_matches_executable_fail_closed_defaults() -> None:
    config = yaml.safe_load((ROOT / "config/sandbox-profiles.yaml").read_text())
    normal = config["profiles"]["normal"]
    defaults = SandboxLimits()

    assert normal["enabled"] is True
    assert normal["runtime"] == "gvisor"
    assert normal["runtime_name"] == "runsc"
    assert normal["allow_root_inside"] is False
    assert normal["user"] == "65532:65532"
    assert normal["image_digest_required"] is True
    assert normal["read_only_rootfs"] is True
    assert normal["cap_drop"] == ["ALL"]
    assert normal["no_new_privileges"] is True
    assert normal["docker_socket"] == "never"
    assert normal["network"] == "none"
    assert normal["workspace_mounts"] == "task_scoped_only"
    assert normal["limits"] == {
        "cpus": defaults.cpus,
        "memory_mb": defaults.memory_mb,
        "pids": defaults.pids,
        "tmpfs_mb": defaults.tmpfs_mb,
        "timeout_seconds": defaults.timeout_seconds,
    }


def test_unimplemented_profiles_and_capability_gateway_fail_closed() -> None:
    config = yaml.safe_load((ROOT / "config/sandbox-profiles.yaml").read_text())
    assert config["profiles"]["low"]["enabled"] is False
    assert config["profiles"]["high"]["enabled"] is False
    assert config["future_capability_gateway"]["enabled"] is False
    assert "direct_worker_internet" in config["hard_denies"]
    assert "host_docker_socket" in config["hard_denies"]
    assert "host_containerd_socket" in config["hard_denies"]
