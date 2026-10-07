import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  temperatureGroupKey,
  fanCardKey,
  maxTemperature,
  hottestTemperatureItem,
  temperatureLimit,
  temperatureScale,
  temperatureBarWidth,
  sortTemperatureGroups,
  hottestTemperatureGroup,
  fanPeakRpm,
  fanSpeedBarWidth,
} from "../src/utils/system-cards.js";

const source = await readFile(new URL("../src/App.vue", import.meta.url), "utf8");
const theme = await readFile(new URL("../src/styles/console-theme.css", import.meta.url), "utf8");

const nvme = {
  name: "NVMe 1",
  rawName: "nvme",
  items: [
    { label: "控制器", rawLabel: "Composite", current: 42.85, high: 89.85, critical: 94.85, level: "ok" },
    { label: "控制器", rawLabel: "Sensor 1", current: 51.5, high: 65261.85, critical: 65261.85, level: "ok" },
  ],
};
const acpitz = {
  name: "主板/机箱",
  rawName: "acpitz",
  items: [{ label: "acpitz", rawLabel: "acpitz", current: 27.8, high: null, critical: null, level: "ok" }],
};
const fans = [
  { id: "acpi:1", name: "风扇 1", rawName: "acpi_ec_z425_fans", rawLabel: "", rpm: 998, status: "running" },
  { id: "acpi:2", name: "风扇 2", rawName: "acpi_ec_z425_fans", rawLabel: "", rpm: 3552, status: "running" },
];

test("temperature groups stack hottest first and keep stable keys", () => {
  assert.deepEqual(sortTemperatureGroups([acpitz, nvme]).map(temperatureGroupKey), ["nvme", "acpitz"]);
  assert.equal(hottestTemperatureGroup([acpitz, nvme]).rawName, "nvme");
  assert.equal(temperatureGroupKey({ name: "未命名组" }), "未命名组");
  assert.equal(maxTemperature(nvme), 51.5);
  assert.equal(maxTemperature({ items: [] }), null);
  assert.equal(hottestTemperatureItem(nvme).rawLabel, "Sensor 1");
  assert.equal(hottestTemperatureItem({ items: [] }), null);
});

test("sensor limits ignore hwmon sentinel values when scaling the bar", () => {
  assert.equal(temperatureLimit(89.85), 89.85);
  assert.equal(temperatureLimit(65261.85), null);
  assert.equal(temperatureLimit(null), null);
  assert.equal(temperatureScale(nvme.items[0]), 89.85);
  assert.equal(temperatureScale(nvme.items[1]), 100);
  assert.equal(temperatureBarWidth({ current: 44.925, high: 89.85 }), "50.0%");
  assert.equal(temperatureBarWidth({ current: 999, high: 89.85 }), "100.0%");
  assert.equal(temperatureBarWidth({ current: null }), "0%");
});

test("fan cards keep their identity and scale against the fastest fan", () => {
  assert.equal(fanCardKey(fans[1]), "acpi:2");
  assert.equal(fanCardKey({ rawName: "acpi_ec_z425_fans", rawLabel: "fan1" }), "acpi_ec_z425_fans:fan1");
  assert.equal(fanCardKey({ name: "风扇 9" }), "风扇 9");
  assert.equal(fanPeakRpm(fans), 3552);
  assert.equal(fanPeakRpm([]), 0);
  assert.equal(fanSpeedBarWidth(fans[0], fans), "28.1%");
  assert.equal(fanSpeedBarWidth({ rpm: 0 }, fans), "4.0%");
  assert.equal(fanSpeedBarWidth(fans[0], []), "0%");
});

test("system view renders stacked accordion cards instead of flat sensor lists", () => {
  assert.match(source, /class="accordion-stack system-stack"/);
  assert.match(source, /class="system-card-trigger"/);
  assert.match(source, /v-for="group in temperatureGroups"/);
  assert.match(source, /v-for="fan in systemFans"/);
  assert.match(source, /isSystemCardExpanded\('temp'/);
  assert.match(source, /isSystemCardExpanded\('fan'/);
  assert.match(source, /toggleSystemCard\('temp'/);
  assert.match(source, /toggleSystemCard\('fan'/);
  assert.match(source, /aria-expanded="isSystemCardExpanded/);
  assert.match(source, /temperatureBarWidth\(item\)/);
  assert.match(source, /fanSpeedBarWidth\(fan, systemFans\)/);
  assert.match(source, /watch\(temperatureGroups/);
  assert.match(theme, /\.system-card-trigger/);
  assert.match(theme, /\.system-card\.expanded/);
  assert.match(theme, /\.temp-reading-bar/);
  assert.match(theme, /\.fan-speed-bar/);
  assert.doesNotMatch(source, /class="temp-card"/);
  assert.doesNotMatch(source, /class="fan-card"/);
});
