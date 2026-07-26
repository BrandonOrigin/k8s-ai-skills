from scripts import calc


def test_ratio_policy_cpu():
    policy = {"type": "ratio", "cpu": 2, "memory": 1.5}
    limit, used_default = calc.apply_limit_policy(300, policy, "cpu", calc.round_cpu_millicores)
    assert limit == 600
    assert used_default is False


def test_ratio_policy_memory():
    policy = {"type": "ratio", "cpu": 2, "memory": 1.5}
    rounded_request = calc.parse_memory_quantity("128Mi")
    limit, used_default = calc.apply_limit_policy(rounded_request, policy, "memory", calc.round_memory_bytes)
    # 128Mi * 1.5 = 192Mi raw, rounded up to the next 128Mi step -> 256Mi.
    assert calc.format_memory_bytes(limit) == "256Mi"
    assert used_default is False


def test_absolute_policy_cpu_ignores_request_value():
    policy = {"type": "absolute", "cpu": "2000m", "memory": "1Gi"}
    limit, used_default = calc.apply_limit_policy(50, policy, "cpu", calc.round_cpu_millicores)
    assert limit == 2000
    assert used_default is False


def test_absolute_policy_memory_ignores_request_value():
    policy = {"type": "absolute", "cpu": "2000m", "memory": "1Gi"}
    limit, used_default = calc.apply_limit_policy(1, policy, "memory", calc.round_memory_bytes)
    assert calc.format_memory_bytes(limit) == "1Gi"
    assert used_default is False


def test_no_policy_cpu_uses_conservative_default_ratio():
    limit, used_default = calc.apply_limit_policy(300, None, "cpu", calc.round_cpu_millicores)
    assert limit == 600  # 300 * DEFAULT_CONSERVATIVE_CPU_RATIO (2.0)
    assert used_default is True


def test_no_policy_memory_uses_conservative_default_ratio():
    rounded_request = calc.parse_memory_quantity("128Mi")
    limit, used_default = calc.apply_limit_policy(rounded_request, None, "memory", calc.round_memory_bytes)
    # 128Mi * DEFAULT_CONSERVATIVE_MEMORY_RATIO (1.5) = 192Mi raw, rounded up to 256Mi.
    assert calc.format_memory_bytes(limit) == "256Mi"
    assert used_default is True


def test_used_conservative_default_only_true_when_policy_is_none():
    policy = {"type": "ratio", "cpu": 2.0, "memory": 1.5}
    _, used_default = calc.apply_limit_policy(300, policy, "cpu", calc.round_cpu_millicores)
    assert used_default is False
