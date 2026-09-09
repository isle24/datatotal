Traffic Lens 0.3.1 桌面预览版

- 多 NAS 支持客户端布局和网页布局，分别记忆界面模式。客户端布局包含 Docker、AI、流量、历史、系统和监控设置。
- 新增服务导航，支持分组、搜索、地址、备注和上传图标。NAS 的 Docker Web 端口可一键加入该 NAS 导航。
- 启动时检查桌面更新；支持下载、签名校验、安装和重启。更新失败可重试。0.2.0 需手动安装本版一次。
- 各台 NAS 与本机独立保存导航，不修改原有规则、通知渠道和历史记录。NAS 导航需要 NAS 服务端 2026.09.09-2 或更新版本。
- 连接旧 NAS 时显示明确的服务端升级提示；HTML 或 500 响应不再显示 JSON 解析错误。

下载：macOS Apple Silicon 用 arm64 DMG，Intel 用 x64 DMG，Windows 用 x64 setup.exe。

预览限制：Mac 为 ad-hoc 签名，尚未 Apple Developer ID 签名或公证；Windows 尚未 Authenticode 签名。测试 Mac 曾因系统局域网权限拒绝连接，后续打包 GUI 已连接实际 NAS。遇到 No route to host 时应检查路由与系统本地网络权限；两种界面模式共享这些权限。

本机暂未提供公网分类、进程网络流量、Docker 控制、GPU/NPU、温度和风扇采集；这些能力在连接 NAS 后使用 NAS 端采集结果。自动更新签名与 Apple/Windows 开发者签名彼此独立。
