Traffic Lens 0.6.0 桌面预览版

- NAS 首页集中展示采集状态、常用服务和页面入口。按 `/` 聚焦搜索，按 `m` 打开页面菜单。
- 公网概览的光场随实际上下行速率变化。点击速率卡片可查看对应方向的连接，也可从概览直接启动 AI 分析。
- `⌘ / Ctrl + K` 搜索当前工作区的页面和服务。连接 NAS 时可按容器名或镜像名搜索 Docker 容器。
- Web 和桌面端采用同一套明暗主题。服务导航适配窄屏，流量图表区分上下行并跟随主题切换。
- 配套 NAS 镜像为 `isle204/nas-traffic-lens:2026.11.23-1`，提供 `linux/amd64` 和 `linux/arm64`。

macOS Apple Silicon 下载 arm64 DMG，Intel Mac 下载 x64 DMG，Windows 下载 x64 setup.exe。

更新包使用 Traffic Lens 自动更新签名。Mac 安装包采用 ad-hoc 签名，Windows 安装包尚未采用 Authenticode 签名。
