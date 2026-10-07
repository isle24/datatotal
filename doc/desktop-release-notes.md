Traffic Lens 0.5.0 桌面预览版

- 新增运维助手（只读 Agent）：用一句话问"今天公网上传了多少流量""最近哪个进程上传最多""哪个容器在大量读写磁盘"，面板会展示选用的只读工具、参数、耗时与 token 估算，并把结果渲染成小卡与排行条，原始 JSON 可折叠查看。所有工具都是只读，不会修改配置或容器。
- 首页改为门户：居中品牌 + 一行实时状态 + 六个大入口卡片 + 一行次级入口，顶部按钮默认隐藏，鼠标移入才出现；导航、进程、设置等页面恢复常驻菜单。
- 服务直达：NAS 端「服务导航」里的服务会直接出现在首页，支持搜索（`/` 或 `⌘K` 聚焦，回车直达第一个命中）。
- 手风琴卡片改为层叠 3D 牌堆：滚动视差、悬停浮起、点击展开置顶；Docker、系统传感器、GPU/NPU/VPU、监控规则与设置编辑器全部接入。
- 全局配色统一为浅蓝，状态色不再使用绿色；系统页新增 GPU / NPU / VPU 卡片，ARM 机型（绿联云等）通过 devfreq 与 `/proc/mpp_service` 读取利用率。
- 界面细节按设计审计重做：自托管 Geist 字体与等宽数字、极淡噪点与环境光晕、1480px 内容宽度、按下反馈与焦点环、合成空态与骨架屏。
- 配套 NAS 镜像：`isle204/nas-traffic-lens:2026.10.07-12`，Docker Hub 同时提供 `linux/amd64` 与 `linux/arm64`；支持极空间（ZOS）、绿联云（UGOS Pro，ARM）与通用 Linux / 飞牛 OS。

下载：macOS Apple Silicon 用 arm64 DMG，Intel 用 x64 DMG，Windows 用 x64 setup.exe。

预览限制：Mac 为 ad-hoc 签名，尚未 Apple Developer ID 签名或公证；Windows 尚未 Authenticode 签名。遇到 No route to host 时应检查路由与系统本地网络权限。

本机暂未提供公网分类、进程网络流量、Docker 控制、GPU/NPU、温度和风扇采集；这些能力在连接 NAS 后使用 NAS 端采集结果。自动更新签名与 Apple/Windows 开发者签名彼此独立。
