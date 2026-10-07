const maximumUsableLimit = 150;

export function temperatureGroupKey(group) {
  return group?.rawName || group?.name || "";
}

export function fanCardKey(fan) {
  return fan?.id || [fan?.rawName, fan?.rawLabel].filter(Boolean).join(":") || fan?.name || "";
}

export function temperatureValue(item) {
  const raw = item?.current;
  if (raw === null || raw === undefined || raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function maxTemperature(group) {
  const values = (group?.items || []).map(temperatureValue).filter(value => value !== null);
  return values.length ? Math.max(...values) : null;
}

export function hottestTemperatureItem(group) {
  const items = (group?.items || []).filter(item => temperatureValue(item) !== null);
  return items.reduce((best, item) => best === null || temperatureValue(item) > temperatureValue(best) ? item : best, null);
}

// hwmon reports sentinel limits such as 65261.85 for NVMe sensors; they are not a usable scale.
export function temperatureLimit(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 && number <= maximumUsableLimit ? number : null;
}

export function temperatureScale(item) {
  const limits = [temperatureLimit(item?.critical), temperatureLimit(item?.high)].filter(limit => limit !== null);
  return limits.length ? Math.min(...limits) : 100;
}

export function temperatureBarWidth(item) {
  const value = temperatureValue(item);
  if (value === null) return "0%";
  const percent = Math.max(4, Math.min(100, (value / temperatureScale(item)) * 100));
  return `${percent.toFixed(1)}%`;
}

export function sortTemperatureGroups(groups) {
  return [...(groups || [])].sort((left, right) => {
    const difference = (maxTemperature(right) ?? -Infinity) - (maxTemperature(left) ?? -Infinity);
    return difference || String(temperatureGroupKey(left)).localeCompare(String(temperatureGroupKey(right)));
  });
}

export function hottestTemperatureGroup(groups) {
  return sortTemperatureGroups(groups)[0] || null;
}

export function fanPeakRpm(fans) {
  const values = (fans || []).map(fan => Number(fan?.rpm)).filter(Number.isFinite);
  return values.length ? Math.max(...values) : 0;
}

export function fanSpeedBarWidth(fan, fans) {
  const peak = fanPeakRpm(fans);
  const rpm = Number(fan?.rpm);
  if (!peak || !Number.isFinite(rpm)) return "0%";
  const percent = Math.max(4, Math.min(100, (rpm / peak) * 100));
  return `${percent.toFixed(1)}%`;
}
