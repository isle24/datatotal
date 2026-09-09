# Traffic Lens 桌面预览版

桌面版本与 NAS Docker 版本独立。桌面代码修改不更新根目录 `VERSION`，不发布 Docker `latest`。

## 安装与使用

- macOS：打开对应架构的 DMG，将 Traffic Lens 拖入 Applications，再启动应用。已生成 Apple Silicon 和 Intel 两种包；本地原生运行验收使用 Apple Silicon。使用系统 WebView，无需 Docker、Python 或 Node.js。
- 从 [桌面版 Releases](https://github.com/isle24/datatotal/releases?q=desktop-v) 下载对应系统安装包。Windows 使用 `*-setup.exe`，Mac 使用 `macOS-arm64.dmg`（Apple Silicon）或 `macOS-x64.dmg`（Intel）。Windows 安装到当前用户目录；需要 WebView2 Runtime，安装器会在缺少时引导安装。
- 测试包没有公开发行证书或 Apple 公证。macOS 使用临时签名；Windows 安装器未签名。请从本仓库构建记录下载，并遵循系统对未知开发者应用的操作提示。
- 首次启动进入本机概览。顶部选择数据来源；右上角设置可添加、编辑或删除 NAS 地址，并配置后台监控、开机启动和历史保留时间。
- 添加 NAS 时输入完整服务地址，例如 `http://192.168.1.10:8088`，不包含 API 路径。切换到此 NAS 后输入其访问密码；未开启认证时可留空。
- macOS 首次访问局域网需要系统授权。macOS 27 测试机的 GUI 请求遇到 `No route to host`，同时系统日志记录本地网络阻止和临时签名缺少 Team ID，没有出现应用授权条目；相同 Rust 核心在开发命令行成功登录、读取、退出 NAS。签名与系统授权仍需进一步验证，不能据此认定所有 Mac 的局域网访问都必须购买开发者会员。应用不绕过系统保护。
- 默认不保存密码。只有勾选“保存到系统凭据库”后才写入 macOS Keychain / Windows Credential Manager。之后可使用“使用已保存的密码”。取消保存后重新登录会删除旧凭据；修改或删除连接也会移除原凭据。
- 最多保存 20 台 NAS。每台可以设置不同名称、地址和密码。顶部切换数据源；切换会取消旧页面请求，同时保留该 NAS 在本次应用运行中的独立登录会话。设置里的断开按钮退出指定 NAS；重启应用后重新认证。每台 NAS 的 AI、历史、规则和操作都留在对应服务器，不能跨 NAS 混用。
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
| AI 配置、模型发现、流式 Markdown 对话 | 已支持，聊天保存在本机 SQLite | 使用各 NAS 已有的 AI 和聊天记录 |
| AI 设置助手 | 提议修改保留天数、默认网卡、关闭窗口行为；确认后应用 | 使用该 NAS 支持的配置能力 |
| Docker、通知、保护规则 | 不执行本机容器或进程操作 | 复用远端功能 |

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
- SQLite 保存连接地址、显示名称、非敏感设置、本机历史与 AI 聊天。聊天可能包含监控数据，请保护数据目录。API Key 和可选保存的 NAS 密码只进入系统凭据库。清空流量历史不会删除聊天、连接与设置。NAS 数据不复制到本地历史库。
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

Tauri 配置版本与 Rust workspace 版本均为桌面 `0.2.0`，两者需同步修改；顶部版本由 Rust 编译时的包版本返回。前端 NAS 版本仍取 NAS API。

## GitHub Actions

工作流为 `.github/workflows/desktop.yml`。桌面代码在 `main` 分支或 Pull Request 变动时自动运行，也可以在 Actions 页面选择 `Desktop preview` → `Run workflow`，指定分支手动执行。

流水线在 Windows 原生 runner 上安装依赖，运行 Rust 核心与前端回归测试，构建 NAS Web 确保兼容，再构建桌面安装器并保存 30 天 Artifact。工作流只需要仓库读取权限，不需要 DockerHub 凭据、NAS 密码或发行证书。

0.2.0 的主分支构建为 [Actions run 34319823942](https://github.com/isle24/datatotal/actions/runs/34319823942)，源码提交 `fdd6d06`，Windows 安装包保存在该运行的 `Traffic-Lens-Windows-x64-3` Artifact。GitHub Release 中的 EXE 使用便于下载校验的名称 `Traffic-Lens-0.2.0-Windows-x64-setup.exe`，与 Actions 安装器内容一致。后续重新构建请使用工作流页面，以免下载已过期的 Artifact。

## 验收边界

自动化覆盖首个采样、计数重置、休眠间隔、SQLite 清理隔离、持久化恢复、历史时区对齐、NAS 地址限制、认证失败、cookie 隔离、重定向拒绝、响应上限和请求取消。Mac 已打开原生应用检查实时数据、进程搜索、历史切换、深浅色模式、数据恢复、关闭后继续采集及退出；GUI 的真实 NAS 登录受上述签名限制。Windows Actions 通过仅证明 Windows 编译与自动化测试成功，不代表在用户 Windows 硬件上实测。短时测试不等同于多日内存稳定性测试。

更完整的本机公网分类、按进程网络归属、硬件传感器和本机告警属于后续阶段。当前预览版不安装抓包驱动、提权助手或系统扩展。

## 本机 AI

桌面设置中的“本机 AI”支持 OpenAI、Claude、DeepSeek、Kimi、Qwen、MiniMax 和自定义兼容接口。预设与 Docker 版共享，模型是否可用以厂商账号权限与当前 `/models` 结果为准。配置支持 OpenAI Chat Completions 和 Anthropic Messages 两种协议，不能把 Responses-only 接口当作 Chat Completions 使用。

1. 选择厂商，填写地址、API Key 和模型，启用 AI 并保存。切换服务地址不会自动转移旧地址的 Key，防止误发凭据。可信本地免鉴权服务可不填 Key。
2. “保存并读取模型”请求该地址的 `/models`，读取不到时可以手动输入模型 ID。“测试连接”发送一个短提示验证实际流式模型，可能产生少量 API 费用，不附带监控数据。
3. 从概览/历史/进程/系统点击 AI 分析，或打开 AI 中心。选择网卡、今日/本周/本月/近 30 天/自定义范围。只有勾选进程摘要才临时采样并发送最多 30 个按 CPU 排序的进程；不发送进程命令行或文件内容。
4. Enter 发送，Shift+Enter 换行；中文输入法组词时不会误发送。支持停止生成；离开 AI 页会取消请求。每个对话保存在本机，重新打开可恢复，较长对话分批查看，可新建和删除。
5. “设置助手”只生成变更预览，点击“确认应用”才修改本机默认网卡、历史保留天数、关闭窗口行为。建议 10 分钟失效；设置在此期间发生变化会拒绝旧建议。不开放任意 shell、文件读写、凭据修改、开机启动、停止进程或跨 NAS 操作。

最大输出可配置 128–393216 tokens，具体模型可能有更低上限；DeepSeek 使用 Docker 版现有预设。输出 token 上限不等于上下文长度。一次分析最多约 240 个历史桶、最近 20 条且合计约 48 KB 的聊天上下文；保留完整聊天不代表每次发送全部内容。

AI 默认关闭、无后台请求。最多 1 路本机聊天，额外的模型读取/测试请求受并发限制。等待时间是连续无响应超时（默认 180 秒、可配置 10–600 秒），聊天总时长最多 30 分钟。流式响应最多 8 MiB，正文最多 2 MiB；达到模型输出上限与异常断流会分别标记。流式正文约每 2 秒保存一次，崩溃可能丢失最近一次保存后的文字。每个对话最多 400 条消息、最多 100 个对话，达到后明确提示新建/清理，不静默删除聊天。

## 开发者账号与签名

- 自己编译与本机测试：免费 Apple Account 可登录 Xcode 使用开发测试能力；不需要为了编译本项目购买 Enterprise 账号。
- 通过 GitHub 向其他 Mac 用户公开分发：加入 [Apple Developer Program](https://developer.apple.com/programs/enroll/)，个人开发者选择 Individual 即可；官方年费为 99 USD，实际按注册地区显示。账号开启双重认证，使用真实姓名；组织身份有额外验证要求。
- 在会员账号生成 **Developer ID Application** 证书（含对应私钥），用于签名 `.app`，再通过 Apple notary service 公证并 stapler。`.dmg` 中直接放 `.app` 不要求 Developer ID Installer 证书；只有另外发布签名 `.pkg` 才涉及 Installer 证书。不需要上架 Mac App Store，也不需要 Enterprise Program。
- 本地测试的 Apple Development 签名和用于外部分发的 Developer ID 不相同。可在 [Apple Developer ID 说明](https://developer.apple.com/developer-id/) 和 [会员比较](https://developer.apple.com/support/compare-memberships/) 核对要求。
- Windows 在 GitHub 分发 EXE 无需 Microsoft 开发者账号。正式发行可配置 Authenticode 代码签名以减少未知发布者提示；即使有签名，也不能保证 SmartScreen 从不提示。
- 0.2.0 仍为未公证的预览包：Mac 临时签名，Windows 未签名。当前构建机没有 Developer ID 证书，因此本次不能标记为已正式签名/公证。证书和私钥应留在本机钥匙串或 GitHub Actions Secrets，绝不提交仓库或贴在聊天中。
