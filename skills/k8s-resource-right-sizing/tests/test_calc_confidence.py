from scripts import calc


def test_variability_ratio_zero_p50_is_inf_no_exception():
    assert calc.variability_ratio(0, 100) == float("inf")


def test_variability_ratio_normal():
    assert calc.variability_ratio(100, 200) == 2.0


def test_variability_class_stable_at_boundary():
    assert calc.variability_class(2) == "stable"


def test_variability_class_variable_just_above_stable_boundary():
    assert calc.variability_class(2.0001) == "variable"


def test_variability_class_variable_at_boundary():
    assert calc.variability_class(4) == "variable"


def test_variability_class_highly_variable_just_above_boundary():
    assert calc.variability_class(4.0001) == "highly_variable"


def test_confidence_low_below_24_hours():
    assert (
        calc.confidence_level(
            observation_hours=23.999,
            overall_variability="stable",
            workload_info_complete=True,
            critical_info_missing=False,
        )
        == "LOW"
    )


def test_confidence_medium_at_24_hours_boundary():
    assert (
        calc.confidence_level(
            observation_hours=24,
            overall_variability="stable",
            workload_info_complete=True,
            critical_info_missing=False,
        )
        == "MEDIUM"
    )


def test_confidence_high_at_168_hours_boundary():
    assert (
        calc.confidence_level(
            observation_hours=168,
            overall_variability="stable",
            workload_info_complete=True,
            critical_info_missing=False,
        )
        == "HIGH"
    )


def test_confidence_medium_just_below_168_hours():
    assert (
        calc.confidence_level(
            observation_hours=167.999,
            overall_variability="stable",
            workload_info_complete=True,
            critical_info_missing=False,
        )
        == "MEDIUM"
    )


def test_confidence_critical_info_missing_forces_low_even_with_high_qualifying_conditions():
    assert (
        calc.confidence_level(
            observation_hours=200,
            overall_variability="stable",
            workload_info_complete=True,
            critical_info_missing=True,
        )
        == "LOW"
    )


def test_confidence_incomplete_workload_info_caps_at_medium_not_low():
    assert (
        calc.confidence_level(
            observation_hours=200,
            overall_variability="stable",
            workload_info_complete=False,
            critical_info_missing=False,
        )
        == "MEDIUM"
    )


def test_confidence_highly_variable_forces_low_regardless_of_hours():
    assert (
        calc.confidence_level(
            observation_hours=200,
            overall_variability="highly_variable",
            workload_info_complete=True,
            critical_info_missing=False,
        )
        == "LOW"
    )
