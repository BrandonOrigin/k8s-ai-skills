import json
from pathlib import Path

from scripts import schema

SAMPLE_INPUT_PATH = Path(__file__).resolve().parent.parent / "examples" / "sample-input.json"


def _load_sample():
    return json.loads(SAMPLE_INPUT_PATH.read_text())


def test_workload_config_is_valid():
    data = _load_sample()
    assert schema.validate_workload_config(data["workloadConfig"]) == []


def test_each_metrics_entry_is_valid():
    data = _load_sample()
    for metrics_entry in data["metrics"]:
        assert schema.validate_runtime_metrics(metrics_entry) == []


def test_cross_validation_has_zero_errors_and_one_warning_for_sidecar():
    data = _load_sample()
    errors, warnings = schema.validate_cross(data["workloadConfig"], data["metrics"])
    assert errors == []
    assert len(warnings) == 1
    assert "log-shipper" in warnings[0]
