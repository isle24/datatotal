import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const bundle = resolve(
  root,
  process.argv[2] ||
    "server/desktop/target/release/bundle/macos/Traffic Lens.app",
);
if (process.platform !== "darwin" || !existsSync(bundle))
  throw new Error("Build the Mac .app first.");
const version = spawnSync(
  "/usr/libexec/PlistBuddy",
  [
    "-c",
    "Print :CFBundleShortVersionString",
    join(bundle, "Contents/Info.plist"),
  ],
  { encoding: "utf8" },
);
if (version.status || !/^\d+\.\d+\.\d+/.test(version.stdout.trim()))
  throw new Error("Unable to read app version.");
const outputDir = join(root, "artifacts/desktop");
const architecture = spawnSync(
  "/usr/bin/lipo",
  ["-archs", join(bundle, "Contents/MacOS/traffic-lens-desktop")],
  { encoding: "utf8" },
);
if (architecture.status)
  throw new Error("Unable to inspect Mac app architecture.");
const arch = architecture.stdout.trim().includes(" ")
  ? "universal"
  : architecture.stdout.trim() === "x86_64"
    ? "x64"
    : "arm64";
mkdirSync(outputDir, { recursive: true });
const output = join(
  outputDir,
  `Traffic-Lens-${version.stdout.trim()}-macOS-${arch}.dmg`,
);
const stage = mkdtempSync(join(tmpdir(), "traffic-lens-dmg-"));
try {
  cpSync(bundle, join(stage, "Traffic Lens.app"), { recursive: true });
  symlinkSync("/Applications", join(stage, "Applications"));
  const result = spawnSync(
    "hdiutil",
    [
      "create",
      "-volname",
      "Traffic Lens",
      "-srcfolder",
      stage,
      "-format",
      "UDZO",
      "-ov",
      output,
    ],
    { stdio: "inherit" },
  );
  if (result.status) process.exitCode = result.status;
  else console.log(output);
} finally {
  rmSync(stage, { recursive: true, force: true });
}
