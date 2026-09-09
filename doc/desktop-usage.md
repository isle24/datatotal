# Traffic Lens 桌面预览版

桌面版本与 NAS Docker 版本独立。桌面代码修改不更新根目录 `VERSION`，不发布 Docker `latest`。

## 安装与使用

- macOS：打开对应架构的 DMG，将 Traffic Lens 拖入 Applications，再启动应用。已生成 Apple Silicon 和 Intel 两种包；本地原生运行验收使用 Apple Silicon。使用系统 WebView，无需 Docker、Python 或 Node.js。
- Windows：从 GitHub Actions 的 `Desktop preview` 成功运行中下载 `Traffic-Lens-Windows-x64-*` Artifact，解压并运行 `*-setup.exe`。安装到当前用户目录；需要 WebView2 Runtime，安装器会在缺少时引导安装。
- 测试包没有公开发行证书或 Apple 公证。macOS 使用临时签名；Windows 安装器未签名。请从本仓库构建记录下载，并遵循系统对未知开发者应用的操作提示。
- 首次启动进入本机概览。顶部选择数据来源；右上角设置可添加、编辑或删除 NAS 地址，并配置后台监控、开机启动和历史保留时间。
- 添加 NAS 时输入完整服务地址，例如 `http://192.168.1.10:8088`，不包含 API 路径。切换到此 NAS 后输入其访问密码；未开启认证时可留空。
- macOS 首次访问局域网需要系统授权。在本次 macOS 27 测试中，系统因临时签名应用缺少 Team ID 拒绝连接，并且没有生成可切换的授权条目；Rust 连接核心的真实 NAS 登录、读取、退出测试成功。本机监控正常，但此机器上的 GUI 局域网连接尚需配置 Apple Development / Developer ID 签名后复验。应用会显示明确提示，不关闭系统安全保护或修改 NAS 的认证配置。
- 默认不保存密码。只有勾选“保存到系统凭据库”后才写入 macOS Keychain / Windows Credential Manager。之后可使用“使用已保存的密码”。取消保存后重新登录会删除旧凭据；修改或删除连接也会移除原凭据。
- 默认关闭窗口后继续本机采集。托盘菜单可重新打开应用，或“退出并停止本机监控”。应用采用单实例；重复启动打开已有窗口。开机启动默认关闭。

## 能力与统计口径

| 功能 | 本机模式 | NAS 模式 |
| --- | --- | --- |
| CPU、内存、磁盘空间 | 已支持；普通用户可见范围 | 使用远端 API |
| 进程 CPU、内存、磁盘读写速率 | 按需采样、搜索、排序、分页；受系统权限限制 | 使用远端 API |
| 网卡上下行速率、系统累计 | 已支持；包含公网和内网 | 使用远端 API |
| 今日、本周、本月、近 30 天历史 | 本地采样后持久化 | 使用 NAS 已保存的历史 |
| 公网归属、进程网络流量、连接明细 | 尚未接入，不显示虚构的公网数据 | 使用远端已有采集能力 |
| GPU、NPU、温度、风扇 | 尚未接入 | 取决于 NAS 设备和权限 |
| Docker、通知、保护规则、AI | 不执行本机容器或进程操作 | 复用远端功能，包括 AI 流式响应 |

本机概览默认选择一块有流量的常规网卡，也可自行选择。网卡类型为名称启发式标注，不能保证物理/虚拟识别完全准确。VPN、隧道与物理网卡可能重复观察同一流量，因此不合并为“公网总量”。系统累计来自网卡计数器，可能在系统或网卡重启后归零。

进程 CPU 百分比以整机全部逻辑核心为 100%，与采用单核心口径的系统工具不同。首次打开进程页需两个采样周期建立速率基线。硬盘读写是系统提供的进程 I/O 计数，不能视为网卡收发。进程只以 PID 与启动时间共同标识。

历史只记录应用实际观察到的流量，安装前、程序退出和系统睡眠期间不回填。计数器重置或超过 15 秒的采样间隔重新建立基线，不制造峰值。历史以分钟保存、按时间桶绘制；刚产生的流量最多约 30 秒后落库。多网卡历史按所选网卡查看。每个图表分别显示上行和下行。

## 数据、权限与性能

- Rust 业务核心在 `server/desktop/core`；Tauri 控制器在 `server/desktop/app`；Vue 桌面页面在 `front-end/src/desktop`。现有 NAS Web 入口独立构建。
- 本机每 2 秒读取基础采样，磁盘空间每分钟刷新。进程页每 2 秒请求一次；离开后最长 8 秒停止进程采样并释放进程列表。
- 本机历史 SQLite 使用 WAL、单写入锁、每 30 秒批量事务；退出正常刷新缓冲。默认保留 30 天，每小时删除过期记录。异常退出可能丢失最近一个写入批次。
- 实时图表最多 121 个点，历史查询最多 1500 个桶，单个 NAS 请求/响应最多 16 MiB，最多 24 个并发请求；普通请求 20 秒、AI 流式请求 10 分钟总超时，并有流式读超时。
- 前端只轮询当前打开的页面；最小化/关闭窗口后暂停页面请求。保留基础采集才能记录后台流量。
- 本机不启动 HTTP 监听端口。只允许加载随包发布的前端；未授予远端 WebView、任意 shell、文件系统读写等权限。外部 HTTP(S) 链接交给系统浏览器。
- 每个 NAS 独立 cookie 会话，禁止 HTTP 重定向，校验 HTTPS 证书；NAS 请求不读取系统代理，以免将局域网请求错误转交代理。HTTP 不加密，需由用户选择受信网络。
- SQLite 只保存连接地址、显示名称、非敏感设置和本机历史。清空历史不会删除连接与设置。NAS 数据不复制到本地历史库。
- 数据和日志可从桌面设置直接打开。macOS 数据位于 `~/Library/Application Support/cn.isle.traffic-lens/desktop.db`，日志位于 `~/Library/Logs/cn.isle.traffic-lens/`。Windows 数据使用当前用户 `%APPDATA%/cn.isle.traffic-lens/`，日志使用 Tauri 标准本地日志目录。日志每个文件约 1 MiB，保留 3 个轮转文件。

## 本地编译

要求：Node.js 24+、Rust stable、对应平台原生工具链。macOS 需 Xcode Command Line Tools 与 macOS SDK；Windows 需 Visual Studio C++ Build Tools、Windows SDK 和 WebView2。

```sh
npm --prefix front-end ci
cargo test --locked --manifest-path server/desktop/Cargo.toml -p traffic-lens-core
npm --prefix front-end test
npm --prefix front-end run build

# macOS：本机架构 .app 和 .dmg
npm --prefix front-end run desktop:mac

# Windows：在 Windows 上生成 x64 NSIS 安装程序
npm --prefix front-end run desktop:build -- --bundles nsis

# 桌面开发模式
npm --prefix front-end run desktop:dev
```

应用输出位于 `server/desktop/target/release/bundle/`。Mac 应用在 `macos/Traffic Lens.app`；Windows 安装器在 `nsis/`。`desktop:mac` 使用 `hdiutil` 生成 DMG 到 `artifacts/desktop/`，不依赖 Finder 自动化授权。

交叉编译 Intel Mac 时先安装 `x86_64-apple-darwin` Rust target，再增加 `--target x86_64-apple-darwin`；产物目录会增加该 target 层。编译成功不代表已在 Intel Mac 或 Windows 实机验收。

```sh
rustup target add x86_64-apple-darwin
npm --prefix front-end run desktop:build -- --target x86_64-apple-darwin --bundles app
node scripts/package-macos.mjs 'server/desktop/target/x86_64-apple-darwin/release/bundle/macos/Traffic Lens.app'
```

Tauri 配置版本与 Rust workspace 版本均为桌面 `0.1.0`，两者需同步修改；顶部版本由 Rust 编译时的包版本返回。前端 NAS 版本仍取 NAS API。

## GitHub Actions

工作流为 `.github/workflows/desktop.yml`。桌面代码在 `main` 分支或 Pull Request 变动时自动运行，也可以在 Actions 页面选择 `Desktop preview` → `Run workflow`，指定分支手动执行。

流水线在 Windows 原生 runner 上安装依赖，运行 Rust 核心与前端回归测试，构建 NAS Web 确保兼容，再构建桌面安装器并保存 30 天 Artifact。工作流只需要仓库读取权限，不需要 DockerHub 凭据、NAS 密码或发行证书。

0.1.0 的主分支验证构建为 [Actions run 34314618578](https://github.com/isle24/datatotal/actions/runs/34314618578)，源码提交 `6187873`，Windows 安装包保存在该运行的 `Traffic-Lens-Windows-x64-2` Artifact。后续重新构建请使用工作流页面，以免下载已过期的 Artifact。

## 验收边界

自动化覆盖首个采样、计数重置、休眠间隔、SQLite 清理隔离、持久化恢复、历史时区对齐、NAS 地址限制、认证失败、cookie 隔离、重定向拒绝、响应上限和请求取消。Mac 已打开原生应用检查实时数据、进程搜索、历史切换、深浅色模式、数据恢复、关闭后继续采集及退出；GUI 的真实 NAS 登录受上述签名限制。Windows Actions 通过仅证明 Windows 编译与自动化测试成功，不代表在用户 Windows 硬件上实测。短时测试不等同于多日内存稳定性测试。

更完整的本机公网分类、按进程网络归属、硬件传感器和本机告警/AI 属于后续阶段。当前预览版不安装抓包驱动、提权助手或系统扩展。
