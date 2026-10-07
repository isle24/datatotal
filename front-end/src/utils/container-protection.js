import { notificationMode } from "./settings-ux.js";
const factors = { "%": 1, B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, "B/s": 1, "KB/s": 1024, "MB/s": 1024 ** 2, "GB/s": 1024 ** 3 };

export function protectionUnitOptions(metric) {
  if (metric === "memoryUsedBytes") return ["B", "KB", "MB", "GB"];
  if (String(metric).startsWith("blk")) return ["B/s", "KB/s", "MB/s", "GB/s"];
  return ["%"];
}

export function normalizeProtectionCondition(condition = {}) {
  const units = protectionUnitOptions(condition.metric);
  const bytes = Math.max(0, Number(condition.threshold || 0));
  const unit = units.length > 1 ? units[bytes >= 1024 ** 3 ? 3 : bytes >= 1024 ** 2 || !bytes ? 2 : bytes >= 1024 ? 1 : 0] : units[0];
  return { ...condition, thresholdValue: bytes / factors[unit], thresholdUnit: unit };
}

export function normalizeProtectionRule(rule = {}) {
  return { targetMode: "single", containers: [], ...rule, channelMode: notificationMode(rule),
    containers: (rule.containers || []).map(target => ({ ...target })),
    conditions: (rule.conditions || []).map(normalizeProtectionCondition) };
}

function matches(target, container) {
  return (target.containerName && target.containerName === container.name)
    || (target.containerId && target.containerId.slice(0, 12) === String(container.id || "").slice(0, 12))
    || (!target.containerName && !target.containerId && target.composeProject && target.composeService && target.composeProject === container.composeProject && target.composeService === container.composeService);
}

export function hasProtectionTarget(rule, container) {
  return (rule.containers || []).some(target => matches(target, container));
}

export function toggleProtectionTarget(rule, container) {
  if (hasProtectionTarget(rule, container)) {
    rule.containers = rule.containers.filter(target => !matches(target, container));
  } else {
    rule.containers = [...(rule.containers || []), { containerId: String(container.id || "").slice(0, 12),
      containerName: container.name || "", composeProject: container.composeProject || "", composeService: container.composeService || "",
      composeContainerNumber: container.composeContainerNumber || "" }];
  }
}

export function protectionRulePayload(rule) {
  const { containerSearch, ...payload } = rule;
  return { ...payload, containerId: String(rule.containerId || "").slice(0, 12),
    channelMode: notificationMode(rule), channelIds: notificationMode(rule) === "selected" ? rule.channelIds || [] : [],
    cooldownSeconds: Number(rule.cooldownSeconds || 0),
    conditions: (rule.conditions || []).map(({ thresholdValue, thresholdUnit, ...condition }) => ({ ...condition,
      threshold: Math.round(Math.max(0, Number(thresholdValue ?? condition.threshold ?? 0)) * (factors[thresholdUnit] || 1)),
      durationSeconds: Math.max(0, Number(condition.durationSeconds || 0)) })) };
}

export function monitorWindow(metric) {
  return metric === "daily_wan_tx_bytes" ? "day" : metric === "stage_wan_tx_bytes" ? "stage" : "realtime";
}

export function newUploadRule(id) {
  return { id, name: "每日公网上传超限", metric: "daily_wan_tx_bytes", operator: "gte", threshold: 0,
    durationSeconds: 0, scope: "wan", direction: "tx", window: "day", enabled: false, channelIds: [] };
}
