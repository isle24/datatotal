const factors = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3,
  "B/s": 1, "KB/s": 1024, "MB/s": 1024 ** 2, "GB/s": 1024 ** 3 };

export function createSettingsDrafts() {
  const baselines = new Map();
  const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object"
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
  const signature = value => JSON.stringify(canonical(value));
  return {
    capture(key, value) { baselines.set(key, signature(value)); },
    isDirty(key, value) { return baselines.has(key) && baselines.get(key) !== signature(value); },
    hydrate(key, incoming, current, force = false) {
      if (!force && this.isDirty(key, current)) return current;
      const result = JSON.parse(signature(incoming));
      this.capture(key, result);
      return result;
    },
    applySaved(key, incoming, current, submitted) {
      if (signature(current) === signature(submitted)) return this.hydrate(key, incoming, current, true);
      this.capture(key, incoming);
      return current;
    },
  };
}

export function notificationMode(rule) {
  return ["all", "selected", "none"].includes(rule.channelMode)
    ? rule.channelMode : rule.channelIds?.length ? "selected" : "all";
}

export function monitorPayload(rule) {
  const { thresholdValue, thresholdUnit, ...result } = rule;
  return { ...result, channelMode: notificationMode(rule),
    channelIds: notificationMode(rule) === "selected" ? rule.channelIds || [] : [],
    window: rule.metric === "daily_wan_tx_bytes" ? "day" : rule.metric === "stage_wan_tx_bytes" ? "stage" : "realtime",
    threshold: Math.round(Math.max(0, Number(thresholdValue ?? rule.threshold ?? 0)) * (factors[thresholdUnit] || 1)) };
}

export function validateNotificationSelection(rule) {
  return notificationMode(rule) === "selected" && !rule.channelIds?.length ? "请选择通知渠道，或改为全部启用渠道 / 不发送通知" : "";
}

export function validateContainerRules(rules) {
  for (const rule of rules.filter(row => row.enabled)) {
    const prefix = `「${rule.name || "容器保护"}」`;
    if (rule.targetMode === "selected" && !rule.containers?.length) return prefix + "请选择至少一个容器";
    if ((rule.targetMode || "single") === "single" && !rule.containerId && !rule.containerName && !(rule.composeProject && rule.composeService)) return prefix + "请选择容器";
    if (!rule.conditions?.length || rule.conditions.some(c => !Number.isFinite(Number(c.thresholdValue ?? c.threshold)) || Number(c.thresholdValue ?? c.threshold) <= 0)) return prefix + "请输入大于 0 的占用阈值";
    const error = validateNotificationSelection(rule);
    if (error) return prefix + error;
  }
  return "";
}

export function validateMonitorRules(rules) {
  for (const rule of rules.filter(row => row.enabled)) {
    if (!Number.isFinite(Number(rule.thresholdValue ?? rule.threshold)) || Number(rule.thresholdValue ?? rule.threshold) <= 0) return `「${rule.name || "流量告警"}」请输入大于 0 的阈值`;
    const error = validateNotificationSelection(rule);
    if (error) return `「${rule.name || "流量告警"}」` + error;
  }
  return "";
}

export function validateTimeRange(start, end) {
  if (!start || !end) return "请选择开始和结束时间";
  const a = new Date(start).getTime(), b = new Date(end).getTime();
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) return "结束时间必须晚于开始时间";
  return "";
}

export function validateChannels(channels) {
  for (const channel of channels) {
    const prefix = `「${channel.name || '通知渠道'}」`;
    if (channel.url) {
      try { if (!['http:', 'https:'].includes(new URL(channel.url).protocol)) return prefix + '通知地址必须使用 HTTP 或 HTTPS'; }
      catch { return prefix + '请输入完整有效的通知地址'; }
    }
    if (channel.enabled && channel.type === 'webhook' && !channel.url) return prefix + '请填写 Webhook 通知地址';
    if (channel.enabled && channel.type !== 'webhook' && !channel.url && !channel.token?.trim()) return prefix + `请填写${channel.type === 'iyuu' ? ' IYUU Token' : ' MeoW 昵称'}`;
  }
  return '';
}

export function connectionDefaults(overrides = {}) {
  return { mode: "capture", iface: "all", scope: "all", proto: "all", direction: "all",
    owner: "", source: "", dest: "", minBytes: 0, minDuration: 0, ...overrides };
}
