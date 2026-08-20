# Docker Icons and AI Settings Assistant Design

## Goal

在 NAS Traffic Lens 中内置常见 Docker 容器图标，并增加一个安全的 AI 设置助手，让用户可以通过自然语言一次配置多个非敏感设置，同时保留人工确认和现有表单配置能力。

## Scope

### Docker icons

- 图标作为应用资源随镜像发布，不依赖运行时 CDN 或外部图片请求。
- 首批内置 qBittorrent、Redis、MySQL、MariaDB、PostgreSQL、MoviePilot、Nginx、MongoDB、Prometheus、Grafana、LinuxServer 和 Docker 等常见服务。
- 自动匹配容器名称、镜像名称和 Compose service 名称，并支持常见别名，例如 `qbittorrent-nox`、`qb`、`moviepolite`、`moviepilot` 和 `postgres`。
- 用户手动上传的图标优先于自动匹配图标；已有 SQLite 中的旧 `icon` 字段继续兼容。
- Docker 列表和详情响应增加稳定的 `iconKey`、`iconSource` 字段。未匹配时返回空图标，不阻塞容器列表。

### AI configuration assistant

- AI 配置请求首先生成结构化 proposal，不直接修改设置。
- 前端显示每个变更的路径、旧值、新值、解释和风险，用户点击一次确认后统一应用。
- proposal 使用随机不可猜测 ID、短有效期和单次应用语义；只保存在进程内，服务重启后全部失效。
- 后端在生成和应用两个阶段都执行白名单、类型、长度、范围和结构校验，不能信任模型输出或浏览器提交的变更内容。
- 应用成功后持久化到现有 SQLite 设置表，并记录不包含秘密值的审计记录。

## Supported AI-managed settings

AI 可以管理以下非敏感设置：

- 运行参数：采样间隔、历史保留、写入间隔、连接活动窗口、连接保留、conntrack 刷新间隔、阶段统计开关和 Docker 自动发现开关。
- 监控规则：新增、修改、启用、停用和删除规则；包括指标、比较符、阈值、持续时间、逻辑关系和渠道引用。
- 通知渠道：名称、类型、启用状态、超时、消息模板和标题模板；渠道地址可以修改，但秘密字段不能由 AI 设置或读取。
- 容器保护：容器选择引用、CPU/内存/磁盘条件、AND/OR、restart/stop、冷却时间和最大动作次数。
- Docker 展示：容器端口备注、服务标签、访问方式和图标选择。
- AI 偏好：启用状态、厂商、Base URL、模型、超时、最大输出和系统提示词，但不包括 API Key。

## Forbidden operations

AI proposal 和 apply 接口必须拒绝：

- Dashboard 密码、AI API Key、Webhook/IYUU/MeoW Token 或其他秘密凭据的读取、设置和删除。
- Docker socket 路径、数据库路径、日志路径、宿主文件路径和任意环境变量注入。
- 任意 SQL、任意宿主命令、任意 Docker 命令、任意网络请求代理或文件写入。
- 未知设置路径、未知规则字段、未知通知类型和超出后端模型约束的结构。

AI 可以读取用于分析的有限摘要，包括当前流量、按时间段历史、进程排行、告警证据、连接摘要、系统状态和最多 50 个 Docker 容器；完整连接表、密钥和原始日志不发送给模型。

## API design

### `GET /api/docker/icons`

返回内置图标清单：

```json
{
  "icons": [
    {"key": "qbittorrent", "label": "qBittorrent", "dataUrl": "data:image/svg+xml,..."}
  ]
}
```

### `POST /api/ai/configure`

请求包含自然语言和可选对话上下文。响应只包含 proposal 预览：

```json
{
  "ok": true,
  "requiresConfirmation": true,
  "proposal": {
    "id": "opaque-id",
    "expiresAt": 1780000000,
    "changes": [
      {
        "path": "runtime.sampleSeconds",
        "oldValue": 1,
        "newValue": 2,
        "summary": "将采样间隔调整为 2 秒",
        "risk": "低"
      }
    ],
    "message": "已生成配置预览，请确认后应用"
  }
}
```

### `POST /api/ai/configure/apply`

只接受服务端生成的 proposal ID。后端检查有效期、单次使用状态、当前用户会话和数据库版本，然后在一个设置更新操作中应用全部变更；失败时不应用部分变更。

### `GET /api/ai/configure/schema`

返回 AI 可配置路径、类型、范围、可用枚举和示例，供设置助手构建受约束的结构化请求。响应不包含任何秘密当前值。

## Architecture

- `server/services/docker_icons.py`：图标注册表、别名规范化和匹配函数；不依赖 FastAPI、数据库或 Docker socket。
- `server/services/ai.py`：现有 AI 厂商协议和模型请求保持不变；新增配置助手的结构化响应解析和长度限制辅助函数。
- `server/main.py`：Pydantic 请求模型、设置白名单、proposal 生命周期、SQLite 持久化、审计记录和 HTTP 路由。
- `front-end/src/App.vue`：AI 中心增加“数据分析”和“设置助手”模式，展示 proposal 变更卡片并提供一次性确认；Docker 页面使用后端返回的内置图标。
- SQLite：复用现有设置存储，新增轻量审计记录表或复用已有告警/设置记录机制，不保存 AI 密钥和 proposal 原文。

## Performance and security

- 内置 SVG 数据在进程启动时加载一次，图标响应有界，不在每次容器统计请求中访问外网。
- 自动匹配只对已返回的容器摘要做字符串归一化；容器 CPU、内存和磁盘统计仍保持按需请求。
- proposal 数量、请求上下文、模型响应、变更数量和字符串长度全部限制；过期 proposal 及时清理。
- 所有错误信息脱敏，不回显 API Key、Token、密码、完整 URL 查询参数或内部堆栈。
- AI 不是后台采集任务，只有用户主动提交时才发起模型请求。

## Verification

- Python 单元测试覆盖图标别名匹配、手动图标优先、proposal 白名单、敏感字段拒绝、过期和重复 apply。
- 前端契约测试覆盖图标展示、设置助手模式、变更预览、确认/取消和错误状态。
- 运行 Python 编译及测试、Go 测试、前端契约测试和构建、Compose 配置校验、`git diff --check`。
- 版本递增为 `2026.08.20-5`；构建 `linux/amd64` 和 `linux/arm64` 镜像及本地 tar，不主动推送 Docker Hub。
