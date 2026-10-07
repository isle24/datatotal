import assert from "node:assert/strict";
import test from "node:test";
import { createSettingsDrafts, connectionDefaults, validateTimeRange, validateContainerRules,
  notificationMode, monitorPayload, validateChannels } from "../src/utils/settings-ux.js";
import { selectionForRule, applyContainerSelection, addVisibleTargets, toggleContainerTarget,
  matchesContainerTarget, switchProtectionScope } from "../src/utils/container-selection.js";

test("saving one settings group preserves another group's unsaved draft", () => {
  const drafts = createSettingsDrafts();
  drafts.capture("channels", [{ id: "c", name: "original" }]);
  const edited = [{ id: "c", name: "edited" }];
  assert.deepEqual(drafts.hydrate("channels", [{ id: "c", name: "server" }], edited), edited);
  assert.equal(drafts.isDirty("channels", edited), true);
  assert.deepEqual(drafts.hydrate("channels", [{ id: "c", name: "server" }], edited, true), [{ id: "c", name: "server" }]);
  assert.equal(drafts.isDirty("channels", [{ id: "c", name: "server" }]), false);
});

test("equivalent form objects are clean regardless of server field order", () => {
  const drafts = createSettingsDrafts();
  drafts.capture("ai", { model: "configured", enabled: false, apiKey: "" });
  assert.equal(drafts.isDirty("ai", { apiKey: "", enabled: false, model: "configured" }), false);
});

test("a delayed save response preserves newer model and credential drafts", () => {
  const drafts = createSettingsDrafts();
  const submitted = { model: "submitted", apiKey: "fake-submitted" };
  const newer = { model: "newer", apiKey: "fake-local-draft" };
  const response = { model: "submitted", apiKey: "" };
  const result = drafts.applySaved("ai", response, newer, submitted);
  assert.deepEqual(result, newer);
  assert.equal(drafts.isDirty("ai", newer), true);
});

test("filtered bulk selection preserves unavailable and hidden selected containers", () => {
  const current = [{ containerId: "missing", containerName: "offline" }, { containerId: "hidden", containerName: "hidden" }];
  const selected = addVisibleTargets(current, [{ id: "aaa", name: "alpha", composeContainerNumber: "1" }]);
  assert.deepEqual(selected.map(t => t.containerName), ["offline", "hidden", "alpha"]);
  assert.equal(selected[2].composeContainerNumber, "1");
  assert.deepEqual(toggleContainerTarget(selected, { id: "new-aaa", name: "alpha" }).map(t => t.containerName), ["offline", "hidden"]);
});

test("single and multiple container selection preserve complete identity", () => {
  const rule = { targetMode: "single", containerId: "aaa", containerName: "alpha", composeProject: "p", composeService: "worker", composeContainerNumber: "1" };
  const target = selectionForRule(rule)[0];
  assert.equal(target.containerName, "alpha");
  applyContainerSelection(rule, [{ containerId: "bbb", containerName: "beta", composeProject: "p", composeService: "worker", composeContainerNumber: "2" }]);
  assert.equal(rule.composeContainerNumber, "2");
  assert.equal(matchesContainerTarget(target, { id: "bbb", name: "beta", composeProject: "p", composeService: "worker", composeContainerNumber: "2" }), false);
});

test("rule names and IDs cannot be mistaken for container identity", () => {
  const targets = selectionForRule({ id: "protection-id", name: "媒体服务保护", targetMode: "single", containerId: "aaa", containerName: "flaresolverr" });
  assert.equal(targets[0].containerId, "aaa");
  assert.equal(targets[0].containerName, "flaresolverr");
});

test("scope changes follow the current visible selection rather than old hidden identities", () => {
  const rule = { targetMode: 'selected', containerId: 'old', containerName: 'old-hidden', containers: [{ containerId: 'bbb', containerName: 'beta' }] };
  switchProtectionScope(rule, 'single');
  assert.equal(rule.containerName, 'beta');
  rule.containerId = 'ccc'; rule.containerName = 'gamma';
  switchProtectionScope(rule, 'selected');
  assert.deepEqual(rule.containers.map(t => t.containerName), ['gamma']);
});

test("notification policy makes an empty specified list different from all", () => {
  assert.equal(notificationMode({ channelIds: [] }), "all");
  assert.equal(notificationMode({ channelIds: ["iyuu"] }), "selected");
  assert.equal(notificationMode({ channelMode: "none", channelIds: [] }), "none");
  assert.equal(notificationMode({ channelMode: "selected", channelIds: [] }), "selected");
});

test("tiny saved byte thresholds survive display and save", () => {
  const result = monitorPayload({ metric: "daily_wan_tx_bytes", thresholdValue: 1, thresholdUnit: "B", threshold: 1 });
  assert.equal(result.threshold, 1);
  assert.equal(result.window, "day");
});

test("container validation allows saved unavailable identities and reports missing choices", () => {
  const rule = { id: "r", name: "rule", enabled: true, targetMode: "selected", containers: [{ containerName: "offline" }], conditions: [{ thresholdValue: 80 }] };
  assert.equal(validateContainerRules([rule]), "");
  assert.match(validateContainerRules([{ ...rule, containers: [] }]), /选择.*容器/);
});

test("connection drills start with no invisible retained filters and custom dates must be valid", () => {
  const defaults = connectionDefaults({ owner: "alpha" });
  assert.equal(defaults.proto, "all");
  assert.equal(defaults.minBytes, 0);
  assert.equal(defaults.minDuration, 0);
  assert.equal(defaults.owner, "alpha");
  assert.match(validateTimeRange("2026-10-07T12:00", ""), /开始.*结束/);
  assert.match(validateTimeRange("2026-10-07T12:00", "2026-10-06T12:00"), /结束/);
  assert.equal(validateTimeRange("2026-10-06T12:00", "2026-10-07T12:00"), "");
});

test("enabled notification channels require their usable address or recipient", () => {
  assert.match(validateChannels([{ type: 'webhook', enabled: true, url: '' }]), /Webhook/);
  assert.match(validateChannels([{ type: 'iyuu', enabled: true, url: '', token: '' }]), /Token/);
  assert.equal(validateChannels([{ type: 'iyuu', enabled: false, url: '', token: '' }]), '');
});
