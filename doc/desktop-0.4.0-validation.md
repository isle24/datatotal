# 0.4.0 发布与验证记录

## 发布产物

- 源码：`37dd7f0`（`chore(desktop): release 0.4.0 with the new console UI`），已推送 `main`，桌面标签 `desktop-v0.4.0`。
- [桌面安装包](https://github.com/isle24/datatotal/releases/tag/desktop-v0.4.0)：Mac arm64、Mac x64 的 DMG，以及 Windows x64 NSIS 安装器，三个平台都带签名更新包，共 10 个产物。
- [发布工作流](https://github.com/isle24/datatotal/actions/runs/37624799777)：三个平台的测试、编译、更新包验签和发布全部成功，用时约 15 分钟（2026-10-07T12:57:36Z → 13:12:14Z）。
- `desktop-update/latest.json` 已指向 0.4.0，包含 `darwin-aarch64`、`darwin-x86_64`、`windows-x86_64` 三个平台。
- 工作流默认把版本 Release 建为 preview；本次按 0.3.1 的最终状态把 0.4.0 标为正式发布并设为 Latest（`gh release edit desktop-v0.4.0 --prerelease=false --latest`），否则仓库首页的 Latest 仍会停留在 0.3.1。
- 三个更新包在本地再次通过 Minisign 验签（`cargo run -p traffic-lens-core --example verify_update`），与 `tauri.conf.json` 内置公钥一致。

## 本地校验

- 前端 `node --test` 49 项通过；Rust `cargo test --locked -p traffic-lens-core` 18 项通过。
- `Cargo.toml`、`tauri.conf.json`、`Cargo.lock` 三处版本同步为 0.4.0，`cargo metadata --locked` 无警告；工作流的版本/标签一致性检查通过。
- `npm run build:desktop` 构建通过。

## 更新说明来源修正

发布说明中 `latest.json` 的 `notes` 原来写死在 `scripts/desktop-artifacts.mjs`，值为 0.3.1 时代的文案。现改为读取 `doc/desktop-release-notes.md` 的第一行（含版本号校验，可用 `DESKTOP_UPDATE_NOTES` 覆盖），并用新脚本重新生成、上传了 `latest.json` 与 `SHA256SUMS.txt`。三个平台的 `signature` 与 `url` 与工作流产物逐字节一致，只修正了 `notes`。

## 界面预览与仓库简介

- README 新增“界面预览”章节，5 张截图取自实际运行 `2026.10.07-3` 的极空间 NAS：桌面浅色/暗色概览、常用设置、容器保护勾选列表、手机端下拉导航。
- 仓库 About 更新为“极空间/NAS 网络监控面板：实时公网流量、进程与 Docker 归因、容器保护与告警通知；Docker Hub 提供 amd64/arm64 镜像，另有 Windows/macOS 桌面客户端。”，并添加 `nas`、`docker`、`monitoring`、`zspace`、`network-monitor`、`fastapi`、`vue3`、`tauri` 主题标签。

## 配套 NAS 版本

桌面 0.4.0 与新控制台配套的 NAS 镜像为 `isle204/nas-traffic-lens:2026.10.07-3`（多架构索引 `sha256:0d03bfe9c83e28a2450738f7d706cf2525e0f56dfef37120e0644612dd29b789`），已部署在极空间 NAS 并通过验收：版本、设置、容器保护状态和 301904 条以上的历史记录均保留。

## 未完成项

- Mac 仍为 ad-hoc 签名，未做 Apple Developer ID 签名与公证；Windows 未做 Authenticode 签名。
- Windows 安装器与 Mac DMG 未在真实设备上做安装验证，只完成构建、签名与清单校验。
