"""Input validation (jsonschema) for workload config and runtime metrics.
See docs/specs/skill1-technical-spec.md."""

import jsonschema

# spec §4.1. `replicas` is optional at the schema level (not just "usually
# provided") because a DaemonSet whose replica count the user can't supply
# leaves it unset entirely (spec §13 item 4) rather than guessing a value.
WORKLOAD_CONFIG_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["kind", "name", "namespace", "containers"],
    "properties": {
        "kind": {"type": "string", "enum": ["Deployment", "StatefulSet", "DaemonSet"]},
        "name": {"type": "string"},
        "namespace": {"type": "string"},
        "replicas": {"type": "integer", "minimum": 1},
        "containers": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "requests"],
                "properties": {
                    "name": {"type": "string"},
                    "requests": {
                        "type": "object",
                        "required": ["cpu", "memory"],
                        "properties": {
                            "cpu": {"type": "string"},
                            "memory": {"type": "string"},
                        },
                    },
                    # object-shaped, presence convention (spec §4.1): key
                    # absent = never asked; null = confirmed no limits;
                    # populated = configured.
                    "limits": {
                        "type": ["object", "null"],
                        "properties": {
                            "cpu": {"type": "string"},
                            "memory": {"type": "string"},
                        },
                    },
                },
            },
        },
        # object-shaped, presence convention: absent = never asked; null =
        # confirmed no HPA; populated = configured.
        "hpa": {
            "type": ["object", "null"],
            "properties": {
                "min": {"type": "integer"},
                "max": {"type": "integer"},
                "targetCPUUtilization": {"type": "integer"},
            },
        },
        # array-shaped, no null variant: its "confirmed absent" state is
        # `[]`, not `null` (spec §4.1).
        "restartHistory": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "container": {"type": "string"},
                    "reason": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
        },
        # strictly two-valued (spec §4.1): true/false are confirmed
        # answers, absent-or-null means the question hasn't been asked.
        # There is no third "unknown" value.
        "platformRequiresLimits": {"type": ["boolean", "null"]},
        # object-shaped, presence convention: absent = never asked; null =
        # asked, user said "not sure"; populated = configured.
        "platformLimitPolicy": {
            "type": ["object", "null"],
            "properties": {
                "type": {"type": "string", "enum": ["ratio", "absolute"]},
                "cpu": {},
                "memory": {},
            },
        },
    },
}


def _format_error(error: jsonschema.exceptions.ValidationError) -> str:
    path = ".".join(str(p) for p in error.path) or "<root>"
    return f"{path}: {error.message}"


def validate_workload_config(data: dict) -> list[str]:
    """Validate a workload configuration payload (spec §4.1) against
    WORKLOAD_CONFIG_SCHEMA. Returns a list of human-readable error
    strings; an empty list means the payload is valid."""
    validator = jsonschema.Draft202012Validator(WORKLOAD_CONFIG_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.path)))
    return [_format_error(e) for e in errors]


# spec §4.2. `observationWindowHours` has a hard minimum of 1 (spec §4.3):
# below that is a rejection, not merely a confidence penalty (the <24h
# "minimum acceptable" penalty is a separate, softer §10 concern).
RUNTIME_METRICS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["container", "observationWindowHours", "cpu", "memory"],
    "properties": {
        "container": {"type": "string"},
        "observationWindowHours": {"type": "number", "minimum": 1},
        "cpu": {
            "type": "object",
            "required": ["samples"],
            "properties": {
                "samples": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "podName": {"type": "string"},
                            "timestampSeries": {},
                            "valuesMillicores": {"type": "array", "items": {"type": "number"}},
                        },
                    },
                },
            },
        },
        "memory": {
            "type": "object",
            "required": ["samples"],
            "properties": {
                "samples": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "podName": {"type": "string"},
                            "timestampSeries": {},
                            "valuesBytes": {"type": "array", "items": {"type": "number"}},
                        },
                    },
                },
            },
        },
        "oomEvents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "podName": {"type": "string"},
                    "timestamp": {"type": "string"},
                },
            },
        },
    },
}


def validate_runtime_metrics(data: dict) -> list[str]:
    """Validate a per-container runtime metrics payload (spec §4.2) against
    RUNTIME_METRICS_SCHEMA. Returns a list of human-readable error strings;
    an empty list means the payload is valid."""
    validator = jsonschema.Draft202012Validator(RUNTIME_METRICS_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.path)))
    return [_format_error(e) for e in errors]


def validate_cross(workload_config: dict, metrics_list: list[dict]) -> tuple[list[str], list[str]]:
    """Cross-validate a workload config against its runtime metrics per
    spec §4.3: rejects (errors) for schema violations, a metrics entry for
    a container absent from the workload config, or an out-of-range
    observation window; warns (does not reject) when a config container
    has no matching metrics entry."""
    errors = list(validate_workload_config(workload_config))
    warnings: list[str] = []

    container_names = {c.get("name") for c in workload_config.get("containers", [])}
    metrics_container_names: set = set()

    for metrics in metrics_list:
        errors.extend(validate_runtime_metrics(metrics))
        container_name = metrics.get("container")
        metrics_container_names.add(container_name)
        if container_name not in container_names:
            errors.append(
                f"metrics entry for container '{container_name}' does not match any "
                "container in the workload config"
            )

    for name in sorted(container_names - metrics_container_names, key=str):
        warnings.append(f"container '{name}' has no matching metrics — excluded from analysis")

    return errors, warnings


def workload_info_complete(workload_config: dict) -> bool:
    """spec §10's "complete workload info" checklist: every optional field
    is key-present (value doesn't matter beyond platformRequiresLimits'
    own two-valued rule) -- a missing key is the only "unresolved" state."""
    for container in workload_config.get("containers", []):
        if "limits" not in container:
            return False

    if "hpa" not in workload_config:
        return False

    if "restartHistory" not in workload_config:
        return False

    if "platformRequiresLimits" not in workload_config or workload_config["platformRequiresLimits"] is None:
        return False

    if workload_config["platformRequiresLimits"] is True and "platformLimitPolicy" not in workload_config:
        return False

    return True


def critical_info_missing(workload_config: dict, metrics_list: list[dict]) -> bool:
    """spec §10's critical-info check: True if any container lacks its
    required requests or has no matching metrics entry, or if `replicas`
    is unset -- per spec §4.1/§13's DaemonSet carve-out, an unknown
    replica count makes the Replica Impact Summary "not computable" and
    is itself treated as missing critical info."""
    metrics_container_names = {m.get("container") for m in metrics_list}
    for container in workload_config.get("containers", []):
        requests = container.get("requests") or {}
        if not requests.get("cpu") or not requests.get("memory"):
            return True
        if container.get("name") not in metrics_container_names:
            return True
    if "replicas" not in workload_config:
        return True
    return False
