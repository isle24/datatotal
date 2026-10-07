# 0.5.0 发布与验证记录

## 结论

- 源码：`0677261`（`test(ui): make source contracts line-ending agnostic`），已推送 `main`，桌面标签 `desktop-v0.5.0`。
- [桌面安装包](https://github.com/isle24/datatotal/releases/tag/desktop-v0.5.0)：Mac arm64 / Mac x64 的 DMG，Windows x64 NSIS 安装器，三个平台都带签名更新包，共 10 个产物；Release 已设为正式发布并标记 Latest。
- `desktop-update/latest.json` 已指向 0.5.0，包含 `darwin-aarch64`、`darwin-x86_64`、`windows-x86_64`。

## 工作流

- 运行 [37649969614](https://github.com/isle24/datatotal/actions/runs/37649969614)：三个构建 job 与 publish 全部成功。
- 版本一致性：`tauri.conf.json`、`server/desktop/Cargo.toml`、`Cargo.lock` 同步为 0.5.0，`cargo metadata --locked` 无警告。

## 本次修掉的问题

第一次运行（[37649179738](https://github.com/isle24/datatotal/actions/runs/37649179738)）在 **Windows** 上失败于 `npm --prefix front-end test`：

- 根因：仓库在 Windows 上检出为 CRLF，而前端契约测试里用 `\n` 写的多行正则会全部失配（macOS/Linux 上检出为 LF 所以本地一直通过）。
- 修复：8 个测试文件统一改用 `readSource()`，读入源码后先把 CRLF 归一化为 LF。
- 验证：本地把 `App.vue`、`console-theme.css`、`styles.css`、`index.html` 转成 CRLF 后重跑，75 项全部通过；再重跑 CI，Windows job 成功。
- 处理：取消第一次运行，删除并重新推送 `desktop-v0.5.0` 标签指向修复后的提交，重新触发工作流。

## 本版内容

- 运维助手（只读 Agent）：一句话查流量/进程/容器，结果渲染成小卡与排行条。
- 首页改为门户：品牌 + 实时状态 + 六个入口卡片 + 服务直达与搜索；顶栏按钮默认隐藏。
- 手风琴卡片改为层叠 3D 牌堆；全局浅蓝配色；系统页新增 GPU / NPU / VPU 卡片（含 ARM 的 devfreq 与 `/proc/mpp_service` 适配）。
- 界面按设计审计优化：自托管 Geist 字体与等宽数字、噪点与环境光晕、1480px 内容宽度、按下反馈与焦点环、合成空态与骨架屏。
- 配套 NAS 镜像：`isle204/nas-traffic-lens:2026.10.07-12`（amd64 + arm64）。

## 截图

README 的「界面预览」已换成新截图（门户、运维助手、流量总览明暗、加速器卡片与 VPU 明细、设置、手机端门户），取自实际运行的极空间 NAS（镜像 2026.10.07-12）。
