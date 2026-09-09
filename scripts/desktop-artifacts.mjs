import {
  readFileSync,
  readdirSync,
  mkdirSync,
  copyFileSync,
  writeFileSync,
  existsSync,
} from "node:fs";
import { resolve, join } from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
export const targets = {
  "darwin-aarch64": "macOS-arm64",
  "darwin-x86_64": "macOS-x64",
  "windows-x86_64": "Windows-x64",
};
export function manifest(version, files, now = new Date().toISOString()) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw Error("Invalid desktop version");
  const platforms = {};
  for (const [target, name] of Object.entries(targets)) {
    const file = `Traffic-Lens-${version}-${name}${target.startsWith("darwin") ? ".app.tar.gz" : "-setup.exe"}`;
    const signature = files[file + ".sig"]?.trim();
    if (!signature || !files[file])
      throw Error(`Missing signed artifact: ${target}`);
    if (
      !Buffer.from(signature, "base64")
        .toString()
        .startsWith("untrusted comment:")
    )
      throw Error(`Invalid signature format: ${target}`);
    platforms[target] = {
      signature,
      url: `https://github.com/isle24/datatotal/releases/download/desktop-v${version}/${file}`,
    };
  }
  return {
    version,
    notes: "NAS 客户端/网页布局、服务导航和签名自动更新。",
    pub_date: now,
    platforms,
  };
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  const [mode, directory, target] = process.argv.slice(2);
  const version = JSON.parse(
    readFileSync(join(root, "server/desktop/app/tauri.conf.json"), "utf8"),
  ).version;
  if (mode === "collect") {
    if (!targets[target]) throw Error("Unknown platform");
    const output = join(root, "artifacts/release");
    mkdirSync(output, { recursive: true });
    const windows = target.startsWith("windows");
    const suffix = windows ? "-setup.exe" : ".app.tar.gz";
    const candidates = readdirSync(directory).filter((name) =>
      name.endsWith(suffix),
    );
    if (candidates.length !== 1)
      throw Error("Expected exactly one updater package");
    const stem = `Traffic-Lens-${version}-${targets[target]}`;
    for (const extra of ["", ".sig"]) {
      copyFileSync(
        join(directory, candidates[0] + extra),
        join(output, stem + suffix + extra),
      );
    }
    if (!windows)
      copyFileSync(
        join(root, "artifacts/desktop", stem + ".dmg"),
        join(output, stem + ".dmg"),
      );
  } else if (mode === "manifest") {
    const files = Object.fromEntries(
      readdirSync(directory)
        .filter((name) => !["latest.json", "SHA256SUMS.txt"].includes(name))
        .map((name) => [
          name,
          name.endsWith(".sig")
            ? readFileSync(join(directory, name), "utf8")
            : true,
        ]),
    );
    const result = manifest(version, files);
    for (const name of Object.values(targets).filter((name) =>
      name.startsWith("macOS"),
    )) {
      if (!existsSync(join(directory, `Traffic-Lens-${version}-${name}.dmg`)))
        throw Error(`Missing installer: ${name}`);
    }
    writeFileSync(
      join(directory, "latest.json"),
      JSON.stringify(result, null, 2) + "\n",
    );
    const names = [...Object.keys(files), "latest.json"].sort();
    writeFileSync(
      join(directory, "SHA256SUMS.txt"),
      names
        .map(
          (name) =>
            `${createHash("sha256")
              .update(readFileSync(join(directory, name)))
              .digest("hex")}  ${name}`,
        )
        .join("\n") + "\n",
    );
  } else
    throw Error("Use collect <bundle-dir> <target>, or manifest <release-dir>");
}
