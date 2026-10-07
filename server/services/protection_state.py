"""Durable action history; sample windows deliberately start fresh on boot."""

import copy


def durable_states(states: dict, rule_ids: set) -> dict:
    def durable(state):
        row = {field: copy.deepcopy(value) for field, value in state.items()
               if field not in {"metrics", "active", "lastStatsAt", "lastCheckedAt", "metricDetails"}}
        if isinstance(state.get("containers"), dict):
            row["containers"] = {key: durable(value) for key, value in state["containers"].items()}
        return row
    return {
        key: durable(state)
        for key, state in states.items() if key in rule_ids
    }


def restore_states(value, rule_ids: set) -> dict:
    if not isinstance(value, dict):
        return {}
    def restore(state):
        row = copy.deepcopy(state)
        row.update(metrics={}, active=False)
        row.pop("lastStatsAt", None)
        row.pop("lastCheckedAt", None)
        row.pop("metricDetails", None)
        row.update(monitorStatus="locked" if row.get("locked") else "waiting", monitorReason="")
        if row.get("pending"):
            row.update(locked=True, monitorStatus="locked", reason="action outcome unknown after restart; manual reset required")
        if isinstance(row.get("containers"), dict):
            row["containers"] = {key: restore(value) for key, value in row["containers"].items() if isinstance(value, dict)}
        return row
    result = {}
    for key, state in value.items():
        if key not in rule_ids or not isinstance(state, dict):
            continue
        result[key] = restore(state)
    return result


def release_legacy_restart_limits(states: dict, rules: list) -> bool:
    """Release known legacy count-limit stops, preserving action history."""
    changed = False
    def release(state):
        nonlocal changed
        if state.get("locked") and state.get("lastAction") == "stop" and not state.get("pending"):
            state.update(locked=False, active=False, metrics={}, monitorStatus="waiting",
                         reason="旧版重启次数上限已取消，已恢复阈值监控", monitorReason="")
            state.pop("stopAttempts", None)
            state.pop("actionFailed", None)
            changed = True
        for child in (state.get("containers") or {}).values():
            if isinstance(child, dict):
                release(child)
    for rule in rules:
        if rule.get("action", "restart") == "restart":
            state = states.get(rule.get("id"))
            if isinstance(state, dict):
                release(state)
    return changed
