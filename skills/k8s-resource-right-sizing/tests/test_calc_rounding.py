import pytest

from scripts import calc


@pytest.mark.parametrize(
    "millicores, expected",
    [
        (264, 300),
        (310, 350),
        (501, 550),
    ],
)
def test_round_cpu_millicores(millicores, expected):
    assert calc.round_cpu_millicores(millicores) == expected


@pytest.mark.parametrize(
    "quantity, expected_quantity",
    [
        ("300Mi", "384Mi"),
        ("700Mi", "768Mi"),
        ("875Mi", "896Mi"),
        ("1.1Gi", "1.25Gi"),
        ("1.6Gi", "1.75Gi"),
    ],
)
def test_round_memory_bytes(quantity, expected_quantity):
    rounded = calc.round_memory_bytes(calc.parse_memory_quantity(quantity))
    assert calc.format_memory_bytes(rounded) == expected_quantity


def test_round_limit_from_ratio_end_to_end():
    # request 1000m / limit 2000m (ratio 2x), P95 = 250m.
    recommended = calc.recommended_cpu_millicores(250)  # 300 (250 * 1.2)
    rounded_request = calc.round_cpu_millicores(recommended)  # 300
    ratio = 2000 / 1000
    limit = calc.round_limit_from_ratio(rounded_request, ratio, calc.round_cpu_millicores)
    assert rounded_request == 300
    assert limit == 600
