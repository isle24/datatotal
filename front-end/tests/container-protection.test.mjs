import assert from "node:assert/strict";
import test from "node:test";
import { normalizeProtectionRule, protectionRulePayload, toggleProtectionTarget, hasProtectionTarget,
  newUploadRule, monitorWindow } from "../src/utils/container-protection.js";

test("legacy single-container rules retain identity and use readable memory units", () => {
  const row = { id: "old", containerId: "aaa", containerName: "alpha", conditions: [
    { metric: "memoryUsedBytes", threshold: 1024 ** 3, durationSeconds: 30 },
  ] };
  const form = normalizeProtectionRule(row);
  assert.equal(form.targetMode, "single");
  assert.equal(form.conditions[0].thresholdValue, 1);
  assert.equal(form.conditions[0].thresholdUnit, "GB");
  assert.equal(protectionRulePayload(form).conditions[0].threshold, 1024 ** 3);
});

test("multi-selection survives container recreation and preserves unavailable targets", () => {
  const form = normalizeProtectionRule({ id: "multi", targetMode: "selected", containers: [
    { containerId: "old", containerName: "alpha" }, { containerId: "absent", containerName: "beta" },
  ] });
  assert.equal(hasProtectionTarget(form, { id: "new", name: "alpha" }), true);
  toggleProtectionTarget(form, { id: "new", name: "alpha" });
  assert.deepEqual(form.containers.map(t => t.containerName), ["beta"]);
  toggleProtectionTarget(form, { id: "ccc", name: "gamma", composeProject: "media", composeService: "gamma" });
  assert.deepEqual(protectionRulePayload(form).containers.map(t => t.containerName), ["beta", "gamma"]);
});

test("percentage and I/O thresholds serialize without UI-only fields", () => {
  const form = normalizeProtectionRule({ id: "all", targetMode: "all", conditions: [
    { metric: "cpuPercent", threshold: 90 }, { metric: "blkWriteBps", threshold: 0 },
  ] });
  form.conditions[1].thresholdValue = 12.5;
  form.conditions[1].thresholdUnit = "MB/s";
  const result = protectionRulePayload(form);
  assert.equal(result.targetMode, "all");
  assert.equal(result.conditions[0].threshold, 90);
  assert.equal(result.conditions[1].threshold, 12.5 * 1024 ** 2);
  assert.equal(result.conditions[1].thresholdValue, undefined);
});

test("new upload rules default to natural-day WAN totals and metric changes update window", () => {
  const rule = newUploadRule("new");
  assert.equal(rule.metric, "daily_wan_tx_bytes");
  assert.equal(rule.window, "day");
  assert.equal(rule.enabled, false);
  assert.equal(monitorWindow("wan_tx_bps"), "realtime");
  assert.equal(monitorWindow("stage_wan_tx_bytes"), "stage");
});

test("selecting one Compose replica leaves other replicas unchecked", () => {
  const form = normalizeProtectionRule({ containers: [{ containerId: "aaa", containerName: "worker-1", composeProject: "project", composeService: "worker" }] });
  assert.equal(hasProtectionTarget(form, { id: "bbb", name: "worker-2", composeProject: "project", composeService: "worker" }), false);
});
