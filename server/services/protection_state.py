"""Durable action limits; sample windows deliberately start fresh on boot."""

import copy


def durable_states(states: dict, rule_ids: set) -> dict:
    return {
        key: {field: copy.deepcopy(value) for field, value in state.items() if field not in {"metrics", "active", "lastStatsAt"}}
        for key, state in states.items() if key in rule_ids
    }


def restore_states(value, rule_ids: set) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, state in value.items():
        if key not in rule_ids or not isinstance(state, dict):
            continue
        row = copy.deepcopy(state)
        row.update(metrics={}, active=False)
        if row.get("pending"):
            row.update(locked=True, reason="action outcome unknown after restart; manual reset required")
        result[key] = row
    return result
