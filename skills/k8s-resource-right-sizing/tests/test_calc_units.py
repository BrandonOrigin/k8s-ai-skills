import pytest

from scripts import calc


@pytest.mark.parametrize(
    "quantity, expected_millicores",
    [
        ("500m", 500),
        ("1", 1000),
        ("2", 2000),
    ],
)
def test_parse_cpu_quantity(quantity, expected_millicores):
    assert calc.parse_cpu_quantity(quantity) == expected_millicores


@pytest.mark.parametrize(
    "quantity, expected_bytes",
    [
        ("128Mi", 134217728),
        ("1Gi", 1073741824),
        ("700Mi", 734003200),
    ],
)
def test_parse_memory_quantity(quantity, expected_bytes):
    assert calc.parse_memory_quantity(quantity) == expected_bytes


def test_format_cpu_millicores_round_trip():
    assert calc.format_cpu_millicores(500) == "500m"


def test_format_memory_bytes_round_trip():
    assert calc.format_memory_bytes(134217728) == "128Mi"
