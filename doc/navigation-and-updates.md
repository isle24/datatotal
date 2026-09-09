# 服务导航、NAS 工作区与客户端更新

## NAS 界面

连接 NAS 后，可在顶部选择“客户端”或“网页”。客户端模式有独立侧栏、实时流量曲线和资源卡片；所有网络、历史、系统、Docker、监控、设置、AI 功能使用同一套业务组件和 NAS API。网页模式是客户端内置的 NAS 网页布局；“在浏览器中打开”访问 NAS 自己提供的网页。不会向远端网页开放 Tauri IPC 权限。

每台 NAS 分别记住界面模式，默认客户端。切换布局保留当前页面；切换 NAS 后请求、会话和数据互相隔离。主题同步更新曲线，布局变化后图表重新计算尺寸。

## 服务导航

- NAS 网页、NAS 客户端模式、本机桌面模式均有导航入口。
- 支持名称、HTTP/HTTPS 地址、图标、分组、备注与排序，支持搜索、分组筛选、删除。
- 在 Docker 卡片展开端口后，Web 端口旁选择“加入导航”。非 Web 端口先在端口配置中明确设置为 Web。Redis 等原生协议端口不会错误地生成 HTTP 入口。
- 导入沿用容器名、端口标签与图标。以容器名、协议和宿主端口去重，容器重建更换 ID 不影响导航记录，重复添加保留手工编辑。端口或服务地址改变后可在导航编辑。
- 本机导航存入本机 `desktop.db`；NAS 导航存入该 NAS 的 `traffic.db`。互不复制，不会把 NAS 导航误存进本机库或另一台 NAS。NAS 的浏览器和不同桌面客户端共享同一批导航。
- 图标在前端生成 96px 位图缩略图，避免每次加载完整原图。允许上传 PNG/JPEG/WebP/GIF；Docker 内置 SVG 只在图像解码中使用，最终存为 PNG。页面不抓取外部 favicon，不做后台可用性探测。每个实例最多 200 个服务，缩略图最多 32 KiB，避免接口无界增长。
- 数据库新增独立 `navigation` 表，不替换既有 settings、监控规则、通知渠道、AI 聊天或历史表。现有 `/data` 挂载即可，不增加 Compose 环境变量。

NAS 服务端最低版本为 `2026.09.09-2`。旧版会将未知 API 路径回退成 HTML；客户端 0.3.1 对此显示升级提示并禁用添加，而非 JSON 解析错误。更新 NAS 镜像并重建容器后点击“更新后重试”。保留原有 data/logs 映射。

## 自动更新

桌面设置提供启动检查开关、手动检查、版本说明、下载进度、错误重试和安装重启。默认启动检查一次，无定时高频后台轮询；安装须点击确认以避免中断未保存的编辑。0.2.0 不包含更新模块，需要手动安装新版一次。

更新入口固定为 GitHub `desktop-update` Release 的 `latest.json`，与 Docker Releases 的 latest 排序无关。清单分别指向 `darwin-aarch64`、`darwin-x86_64` 和 `windows-x86_64` 的版本化包；默认拒绝降级。

Tauri 内置公钥验证每个更新包的 Minisign 签名，验证失败不会安装。macOS 使用 `.app.tar.gz` 进行更新、DMG 用于首次安装；Windows 使用 NSIS EXE。更新会保留用户目录中的 SQLite 和 OS 凭据。

## 维护者发布

1. 同步修改 `server/desktop/Cargo.toml` 与 `server/desktop/app/tauri.conf.json` 的桌面版本。
2. 更新 `doc/desktop-release-notes.md`。推送 `desktop-vX.Y.Z` 标签，或手动运行 `Signed desktop release`，传入已存在的标签。
3. `.github/workflows/desktop-release.yml` 在 Windows x64、Mac arm64/x64 runner 上运行测试、编译、签名和验签。全部成功后发布预览版，再更新桌面通道清单。单个平台失败不会更新通道。
4. 私钥只保存在本机私有目录或 `TAURI_SIGNING_PRIVATE_KEY` Actions Secret；如有密码，使用 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` Secret。普通分支/PR 的 Windows CI 禁用发布签名，不读取密钥。
5. 本地正式更新包构建前，设置 `TAURI_SIGNING_PRIVATE_KEY` 为私钥路径、`TAURI_SIGNING_PRIVATE_KEY_PASSWORD` 为其密码。公钥必须与 `tauri.conf.json` 一致。然后运行 `npm --prefix front-end run desktop:mac` 或 Windows `desktop:build -- --bundles nsis`。
6. `scripts/desktop-artifacts.mjs collect <bundle目录> <updater target>` 整理文件名；`manifest <release目录>` 必须找到三个平台的更新包和签名才生成清单与 SHA256SUMS。验签使用 `cargo run --manifest-path server/desktop/Cargo.toml -p traffic-lens-core --example verify_update -- <tauri配置> <更新包> <签名>`。

发布签名不同于 Apple Developer ID/公证和 Windows Authenticode。当前仍是临时签名预览版本，不宣称已取得公开发行证书。macOS 局域网访问仍需系统授权；测试曾遇到拒绝连接，之后实际 NAS 的打包客户端概览与 Docker 页面已验证可用。

## 验证

Python 测试先安装 `server/requirements-dev.txt`，设置 `FRONTEND_DIR` 为构建后的 `front-end/dist`。导航测试覆盖 SQLite CRUD、重复导入、不覆盖原配置、非法 URL/图标、认证和未知 API JSON 404。Rust 测试覆盖本机导航与每 NAS 布局隔离。前端测试覆盖 Docker 地址/IPv6、旧服务端 HTML 响应、更新并发、重试和发布清单完整性。
