# 0.3.1 发布与验证记录

## 发布产物

- 源码：`1ebab64cbfce0bbb2f139d7d3a6838aaa2013f95`，已推送 `main`，桌面标签 `desktop-v0.3.1`。
- [桌面安装包](https://github.com/isle24/datatotal/releases/tag/desktop-v0.3.1)：Mac arm64、Mac x64 的 DMG，以及 Windows x64 NSIS 安装器。三个平台均包含签名更新包。
- [发布工作流](https://github.com/isle24/datatotal/actions/runs/34326032107)：三个平台的测试、编译、更新包验签及发布全部成功。
- [普通 Windows CI](https://github.com/isle24/datatotal/actions/runs/34326006245) 成功。
- `desktop-update/latest.json` 已指向 0.3.1，包含三个平台，内容与版本 Release 的清单一致。公开下载的全部产物通过 SHA256SUMS 校验，三个更新包再次通过本地 Minisign 验签。
- NAS 镜像 `isle204/nas-traffic-lens:2026.09.09-2` 和 `latest` 均已发布，包含 `linux/amd64`、`linux/arm64`。同时发布 `2026.09.09-2-amd64`、`2026.09.09-2-arm64`、`latest-amd64`、`latest-arm64`、`amd64`、`arm64`。
- NAS 版本与 latest 的多架构清单摘要相同：`sha256:3c597604b2cb7316bfa69f5acf519b5defabf06b1ca8cdf7e4cebb3eded088a7`。

## 导航报错与升级

实际测试的 NAS 仍运行 `2026.09.09-1`，没有 `/api/navigation`，未知路径会返回 HTML。这是 `JSON Parse error: Unrecognized token '<'` 的原因。

客户端 0.3.1 会显示明确的 NAS 升级提示，并禁用不受支持的导航写入；不会将这台 NAS 的导航存到本机作为替代。新版 NAS 对未知 API 返回 JSON 404，避免网页内容被当成 JSON。

NAS 使用者可将镜像改为 `isle204/nas-traffic-lens:2026.09.09-2`，拉取并重建容器。也可使用已经更新的 `latest`。保留原有 data/logs 映射，无需新增 Compose 环境变量或挂载。此次验证没有修改实际 NAS 的设置、规则、通知渠道或运行中的容器。

## 已完成验证

- 99 项 Python、19 项前端、18 项 Rust 测试通过；Rust clippy 无警告。前端构建仍有既有 bundle 大小提示，Python 仍有既有 FastAPI lifespan 弃用提示。
- NAS 和桌面前端构建成功；两种 NAS 镜像通过版本、导入和镜像内容检查。SQLite 导航 CRUD 已验证，NAS 镜像不包含 Rust 构建目录。
- 测试 NAS 的 Docker Web 端口可加入导航，图标转为 96px 位图，编辑名称和备注后刷新及重启服务仍保留。
- 网页导航已检查浅色、暗色和窄屏布局，没有横向溢出。
- 实际 NAS 的客户端概览、Docker 列表和客户端/网页布局切换已验证；27 个容器正常显示，切换布局保留当前页面。
- 本机 Mac 从 0.3.0 通过公开 GitHub 更新通道发现 0.3.1，下载、验签、安装完成；安装目录中的版本为 0.3.1。重新打开后本机导航记录和 NAS 连接配置保留，本机 CPU、内存、网卡数据显示正常。
- 已发布的 Mac 0.3.1 再次连接实际 NAS 成功：概览正常显示实时流量、67 条公网连接及 27 个容器。进入导航后显示“需要更新 NAS 服务端”与最低版本说明，添加按钮禁用，不再出现 JSON 解析错误。这里只做登录和读取，没有修改实际 NAS 数据。

## 验证边界

Mac 自动安装后的第一次“重启客户端”出现了进程存活但 UI 自动化无法取得窗口的情况。进程采样显示主事件循环正常，未发现该进程卡在采集或数据库操作；退出后重新打开可以显示 0.3.1。窗口自动恢复仍需继续验证，不将本次安装成功等同于完整重启链路已通过。遇到相同情况可先退出应用，再从应用程序目录重新打开，无需删除本地数据。

Windows 与 Intel Mac 已完成 CI 编译和更新包验签，未在对应实体设备上运行。Mac 尚未 Apple Developer ID 签名或公证，Windows 尚未 Authenticode 签名；更新包签名不等于操作系统发行者签名。本机公网分类、进程网络流量及硬件传感器仍属于桌面预览版的既有功能边界。
