export function containerTarget(container = {}) {
  return { containerId: String(container.id || container.containerId || "").slice(0, 12),
    containerName: container.name || container.containerName || "",
    composeProject: container.composeProject || "", composeService: container.composeService || "",
    composeContainerNumber: container.composeContainerNumber || "" };
}

export function matchesContainerTarget(target, container) {
  const row = containerTarget(container);
  if (target.containerId && target.containerId === row.containerId) return true;
  if (target.containerName && target.containerName === row.containerName) return true;
  return Boolean(!target.containerId && !target.containerName && target.composeProject && target.composeService
    && target.composeProject === row.composeProject && target.composeService === row.composeService
    && (!target.composeContainerNumber || target.composeContainerNumber === row.composeContainerNumber));
}

export function selectionForRule(rule) {
  if (rule.targetMode === "selected") return rule.containers || [];
  const target = containerTarget({ containerId: rule.containerId, containerName: rule.containerName,
    composeProject: rule.composeProject, composeService: rule.composeService, composeContainerNumber: rule.composeContainerNumber });
  return target.containerId || target.containerName || (target.composeProject && target.composeService) ? [target] : [];
}

export function applyContainerSelection(rule, targets) {
  if (rule.targetMode === "selected") rule.containers = targets;
  else Object.assign(rule, containerTarget(targets[0] || {}));
}

export function switchProtectionScope(rule, mode) {
  const previous = rule.targetMode || 'single';
  const targets = selectionForRule(rule);
  rule.targetMode = mode;
  if (mode === 'single' && previous === 'selected') applyContainerSelection(rule, targets.slice(0, 1));
  if (mode === 'selected' && previous === 'single') rule.containers = targets;
  if (mode === 'selected' && previous === 'all' && !rule.containers?.length) rule.containers = targets;
}

export function toggleContainerTarget(selected, container) {
  return selected.some(target => matchesContainerTarget(target, container))
    ? selected.filter(target => !matchesContainerTarget(target, container))
    : [...selected, containerTarget(container)];
}

export function addVisibleTargets(selected, containers) {
  const result = [...selected];
  for (const container of containers) {
    if (!result.some(target => matchesContainerTarget(target, container))) result.push(containerTarget(container));
  }
  return result;
}
