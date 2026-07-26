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
