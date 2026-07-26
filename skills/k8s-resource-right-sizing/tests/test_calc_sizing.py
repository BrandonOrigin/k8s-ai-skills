from scripts import calc


def test_recommended_cpu_millicores_default_safety_factor():
    assert calc.recommended_cpu_millicores(250) == 300


def test_recommended_memory_bytes_default_safety_factor():
    # 700Mi (734003200 bytes) * 1.25 = 875Mi (917504000 bytes), pre-rounding.
    assert calc.recommended_memory_bytes(734003200) == 917504000.0


def test_recommended_cpu_millicores_custom_safety_factor():
    assert calc.recommended_cpu_millicores(250, safety_factor=1.5) == 375


def test_recommended_memory_bytes_custom_safety_factor():
    assert calc.recommended_memory_bytes(1000, safety_factor=2.0) == 2000
