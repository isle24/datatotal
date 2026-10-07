"""Container identities shared by protection evaluation and Docker display."""


def target_matches_row(target: dict, row: dict) -> bool:
    cid = str(target.get("containerId") or "").strip().lstrip("/")[:12]
    if cid and cid == str(row.get("id") or "").strip()[:12]:
        return True
    project, service = target.get("composeProject"), target.get("composeService")
    if project and service and project == row.get("composeProject") and service == row.get("composeService"):
        return not target.get("composeContainerNumber") or target["composeContainerNumber"] == row.get("composeContainerNumber")
    name = str(target.get("containerName") or "").strip().lstrip("/")
    return bool(name and name == str(row.get("name") or "").strip().lstrip("/"))


def rule_matches_row(rule: dict, row: dict) -> bool:
    if rule.get("targetMode") == "all":
        return row.get("state", "running") == "running"
    if rule.get("targetMode") == "selected":
        return any(target_matches_row({**target, "composeProject": "", "composeService": ""}, row)
                   if target.get("containerId") or target.get("containerName") else target_matches_row(target, row)
                   for target in rule.get("containers") or [])
    return target_matches_row(rule, row)


def target_state_key(target: dict) -> str:
    if target.get("stateKey"):
        return target["stateKey"]
    if target.get("name"):
        return "name:" + str(target["name"])
    if target.get("composeProject") and target.get("composeService"):
        suffix = "/" + str(target["composeContainerNumber"]) if target.get("composeContainerNumber") else ""
        return f"compose:{target['composeProject']}/{target['composeService']}{suffix}"
    return "id:" + str(target.get("id") or "")[:12]


def new_state() -> dict:
    return {"count": 0, "lastActionAt": None, "lastAction": "", "reason": "",
            "active": False, "locked": False, "metrics": {}}


def row_protection_state(rule: dict, states: dict, row: dict) -> dict:
    state = states.get(str(rule.get("id") or "")) or {}
    if rule.get("targetMode", "single") == "single":
        return state
    children = list((state.get("containers") or {}).values())
    cid = str(row.get("id") or "")[:12]
    exact = next((s for s in children if cid and cid == str(s.get("containerId") or "")[:12]), None)
    exact = exact or next((s for s in children if row.get("name") and row["name"] == s.get("containerName")), None)
    return exact or {}


def prepare_group_states(group: dict) -> None:
    if "containers" not in group:
        children = {}
        if group.get("containerId") or group.get("containerName"):
            identity = {"id": group.get("containerId"), "name": group.get("containerName")}
            children[target_state_key(identity)] = dict(group)
        group.clear()
        group.update(new_state(), containers=children)


def state_for_target(group: dict, target: dict, multiple: bool) -> dict:
    if multiple:
        prepare_group_states(group)
    if multiple or "containers" in group:
        key = target_state_key(target)
        children = group["containers"]
        if key not in children:
            exact = row_protection_state({"id": "r", "targetMode": "all"}, {"r": group}, target)
            if exact:
                key = next(k for k, state in children.items() if state is exact)
                target["stateKey"] = key
        return children.setdefault(key, new_state())
    return group
