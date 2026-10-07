# 工作台首页 + 运维 Agent 设计（待讨论）

> 状态：设计稿，未实现。本文只给方案与默认值，代码改动需确认后再动。
> 关联现状：`front-end/src/App.vue`（导航与视图）、`server/main.py`（`docker_api_request`、容器保护动作、设置 API、AI 提案链路）、`server/services/ai.py`、`docker-compose.nas.yml`。

## 1. 需求与目标

1. **首页工作台**：概览页改成纯净的工作台，左侧菜单默认隐藏，进入其他页面时才显示。
2. **运维 Agent**：能查流量、改设置、维护 Docker（创建容器、改 compose），适配极空间目录结构，**直接把 compose 写到磁盘再启动**。

## 2. 现状（代码事实，2026-10-07 核实）

| 事项 | 现状 |
| --- | --- |
| 导航 | `App.vue` 的 `navItems` 共 10 项；`<aside v-if="!native" class="sidebar">` 常驻；手机端是 `select` 下拉切换 |
| 视图切换 | `activeView` + `setView()`；每个视图按需要启动各自的轮询定时器 |
| AI 能力 | `server/services/ai.py` 只有 chat completion（OpenAI / Anthropic 两种协议），**没有 function calling**；已有"设置助手"的 `create_ai_configuration_proposal` → `/api/ai/configure/apply` 提案-确认-应用链路 |
| Docker 访问 | `docker_api_request(method, path, body)` 直接走 unix socket；已有白名单动作 `docker_container_action(id, restart\|stop)` |
| socket 权限 | compose 里是 `:ro`，但**只读挂载不限制 API 写操作**（ro 只约束文件系统，不影响 socket 通信）。也就是说现在就已经具备改容器的能力，安全边界靠代码白名单，不靠挂载 |
| 容器内工具链 | **容器里没有 `docker` CLI，也没有 compose 插件**；宿主是 Docker Compose v2.29.7 |
| 文件系统 | 容器只挂了 `./data`、`./logs`、socket，**看不到宿主 compose 目录** |
| 极空间目录 | 宿主 `<docker root>` = `/tmp/zfsv3/nvme16/18181998187/data/docker/`，下面每个应用一个目录（`alist`、`autofilm`、`nas-traffic-lens`…），这正是极空间的应用布局 |

## 3. Part A：工作台首页与按需菜单

### 3.1 工作台包含什么

概览页从"指标仪表盘"升级为可操作的工作台，但保持视觉克制（沿用现有 3D 牌堆与浅蓝主题）：

1. **状态条**：采集状态、Docker 连接、今日公网累计、活跃告警数（一行胶囊）。
2. **实时大卡**：当前公网速率（上/下行）+ 快捷"查看连接"/"AI 分析"。
3. **常用入口磁贴**：Docker、历史、进程、监控中心、设置——点击进入对应页面（这时才出现侧边栏）。
4. **告警与事件**：最近告警 + （后续）容器健康事件。
5. **运维助手入口**：一句话输入框（"查一下今天上传最多的进程"/"给 qbittorrent 加一个端口"），点击后展开 Agent 面板。

### 3.2 菜单显示策略（两种，需拍板）

| 方案 | 行为 | 优点 | 缺点 |
| --- | --- | --- | --- |
| **A. 仅工作台隐藏（推荐）** | 首页无侧边栏；点任意磁贴/进入其他页面后，侧边栏恢复常驻 | 实现简单、行为可预期；用户"点其他页面才显示菜单"的原话就是这个 | 从其他页面回首页时菜单会收起 |
| B. 全站抽屉 | 侧边栏默认全部隐藏，靠汉堡按钮/快捷键随时呼出；可在设置里"固定" | 内容区最宽 | 每次切页面多一步；NAS 用户常年用侧边栏，可能觉得别扭 |

实现要点（两种方案共用）：

- 侧边栏容器改为 `:class="{ 'sidebar-hidden': !menuVisible }"`，用 `grid-template-columns: 0 minmax(0,1fr)` + `translateX(-100%)` 动画；移动端沿用现有 `select`。
- 抽屉模式：右上角汉堡按钮 + `Esc`/点击遮罩关闭 + 焦点陷阱；`settings` 增加 `ui.sidebarPinned`（默认关）。
- 视图切换仍用 `activeView`，但建议**同步 `location.hash`**（`#/docker`），这样刷新和桌面端嵌入能保持页面；不改路由库。
- 键盘：`g` 然后 `o/d/s/...` 快捷跳转，`/` 聚焦 Agent 输入（可选，P3）。
- 桌面端（Tauri）：`DesktopShell.vue` 有自己的 `ds-tabs`，建议桌面保持现状，只有 NAS 内嵌视图跟随本次改动。

### 3.3 验收

- 首页无侧边栏、无横向滚动；进入任意其他页面侧边栏出现；返回首页再收起；移动端与明暗主题无回归。
- 刷新后停留在同一页面（如启用 hash 同步）。

## 4. Part B：运维 Agent

### 4.1 定位（重要）

**不是自主 Agent，而是"受限工具 + 提案确认"**：

- AI 只做两件事：把自然语言变成**结构化计划 JSON**、把工具执行结果解释成人话。
- 执行只发生在后端白名单工具里，且**必须由人工在前端确认一次**。
- AI 永远拿不到 shell、拿不到任意文件路径、不直接调用工具。

### 4.2 工具清单（白名单 + 风险分级）

| 工具 | 作用 | 风险 | 确认 | 备注 |
| --- | --- | --- | --- | --- |
| `traffic.summary` | 当前公网/内网速率与累计 | R0 只读 | 否 | 复用 `/api/overview` |
| `traffic.history` | 按时间段的历史聚合 | R0 | 否 | 复用 `/api/history` |
| `traffic.connections` | 当前连接与端口归因 | R0 | 否 | 复用 `/api/connections` |
| `traffic.processes` | 进程排行 | R0 | 否 | 复用 `/api/processes` |
| `system.status` | CPU/内存/温度/GPU/NPU | R0 | 否 | 复用 `/api/system` |
| `docker.list` / `docker.inspect` / `docker.logs` | 容器清单、详情、日志尾部 | R0 | 否 | 日志做长度与脱敏处理 |
| `compose.list` / `compose.read` | 列出/读取某个应用的 compose | R0 | 否 | 路径 jail 到 compose 根 |
| `settings.read` | 读取当前设置 | R0 | 否 | 敏感项（密码/Token/Key）永不返回 |
| `settings.propose` | 生成设置变更提案（不落盘） | R1 写 | 是 | 复用现有设置助手校验 |
| `docker.container.start/stop/restart` | 容器生命周期 | R2 | 是 | 白名单动作，沿用冷却与次数上限 |
| `docker.container.remove` | 删除容器 | R3 破坏性 | 是（加强确认） | 默认关闭，需显式开启 |
| `compose.create` | 新建应用目录 + compose + `up -d` | R2 | 是 | 核心需求 |
| `compose.update` | 改现有 compose 并重建 | R2 | 是 | 先备份、diff 预览 |
| `compose.down` / `compose.remove` | 停止/删除应用 | R3 | 是（加强确认） | 默认关闭 |
| `notification.test` | 发测试通知 | R1 | 是 | 复用现有接口 |

风险档位可在设置里逐级放开：**只读 → +设置 → +Docker 生命周期 → +compose 创建/更新 → +删除**，默认只到"只读 + 设置提案"。

### 4.3 执行管线

```
用户自然语言
  → ① 计划：AI 输出 {intent, tool, args, assumptions, questions?}（严格 JSON Schema）
  → ② 校验：工具白名单、参数类型/范围、路径 jail、端口冲突、镜像存在性、权限档位
  → ③ 预览：生成 diff（compose 文件 diff / settings diff）+ 影响面（新建/重建/停止哪些容器）
  → ④ 确认：前端确认卡片（[执行] [取消]，破坏性操作需二次确认）
  → ⑤ 执行：后端按 proposalId 执行（不接受自然语言参数）
  → ⑥ 验证：健康检查 / `docker compose ps` / 接口回读
  → ⑦ 审计：写 ops_agent_audits，并回显给 Agent 解释
```

关键点：**提案与执行分离**，`proposalId` 一次性、有 TTL（默认 10 分钟），执行接口只认 id 不认内容，避免"确认后被换内容"。

### 4.4 极空间 Compose 落盘与启动

**目录约定**（沿用极空间布局）：

```
<compose root>/<app-name>/docker-compose.yml     # 主文件
<compose root>/<app-name>/.env                   # 可选，变量
<compose root>/<app-name>/data/                  # 数据目录（如需绑定）
```

默认 `<compose root>` = 宿主 `/tmp/zfsv3/nvme16/18181998187/data/docker`（即极空间 Docker 应用根），容器内挂到 `/compose`。

**写入流程**：

1. 生成 YAML（AI 给参数，后端用固定模板拼，不让 AI 直接写文件）。
2. 写 `<app>/.docker-compose.yml.tmp` → `docker compose -f tmp config --quiet` 校验语法与变量。
3. 备份旧文件到 `<compose root>/.backups/<app>/<时间戳>/`。
4. 原子替换 `docker-compose.yml`（`os.replace`），保留原文件权限与属主。
5. `docker compose -p <app> -f <path> up -d`。
6. 回读 `docker compose ps --format json` + 容器健康，失败则回滚文件并 `up -d` 旧版本。

**极空间适配要点**：

- 绑定路径必须落在 ZFS 数据集下（`/tmp/zfsv3/...`），且**禁止 `/proc` 挂载**（极空间会以 `invalid volume path: /proc` 拒绝，历史踩过）。
- 端口冲突检测：`network_mode: host` 的应用不映射端口，改由应用自身端口设置；bridge 应用要检查宿主已占用端口。
- 应用名规范：小写字母、数字、`-`；项目名 = 目录名，便于和极空间界面里的容器对照。
- 由我们创建的 compose 应用会以**容器**形式出现在极空间 Docker 里，但**不一定出现在极空间的"应用"列表**（那是它自己的元数据）。见待确认问题 7。

**执行 `docker compose` 的方式（需拍板）**：

- 容器里没有 docker CLI，要真正"写文件后启动"，需要在镜像内加入 `docker` CLI + `compose` 插件（约 +40MB，或使用静态二进制），并把 socket 与 compose 根挂进容器。
- 备选：完全不走 CLI，直接用 Docker API 复刻 `compose up`（创建网络、卷、容器）——能创建容器，但**不会生成 compose 文件**，与用户需求不符，不推荐。

### 4.5 AI 使用与 token 控制

- 复用现有 AI 设置（provider/model/baseUrl/key），**不新增一套密钥**；建议单独指定便宜模型或本地 Ollama 给运维助手。
- 协议：不依赖各家 function calling，统一用"**JSON 计划**"协议（提示词里给出工具 Schema，要求只输出 JSON），兼容所有 provider。
- 每次交互最多 2 次调用：生成计划 1 次 + 解释结果 1 次（可合并或跳过解释）。
- 上下文只带**工具摘要**（≤2KB），不带全量日志、不带历史全量。
- 配额：复用容器健康守护里的配额思路——每小时/每日调用上限、每日 token 预算、超预算停止、相同请求指纹缓存。
- 只读工具（R0）也计入次数，但允许更高上限；写操作一律人工确认。

### 4.6 审计与回滚

- 新增 `ops_agent_audits`：`id, ts, session, intent, tool, risk, args_json, diff, result, duration_ms, status, rollback_hint`。
- 回滚：compose 有文件备份 + `up -d` 旧版本；容器操作保留操作前 `inspect` 快照；删除类操作**先导出 config 再删**。
- 前端"运维助手"面板提供"最近操作"列表与一键回滚（仅限有备份的）。

### 4.7 前端形态

- **全局悬浮入口**：右下角圆钮（工作台与各页面都在），点击展开右侧/底部抽屉对话面板；工作台的输入框也唤起同一面板。
- **确认卡片**：面板内嵌卡片，展示 diff（代码块）、影响面（"将重建 1 个容器"）、风险标签（只读/写/破坏性）、[执行]/[取消]；破坏性操作要求输入容器名确认。
- **Docker 页**：容器行增加"更多"菜单 → 查看日志 / 重启 / 生成 compose 片段 / 交给助手。
- **设置页**：新增「运维助手」分区（总开关、权限档位、确认策略、模型选择、配额与预算、审计入口）。

### 4.8 安全边界（硬约束）

- 路径 jail：只能读写 `<compose root>` 下的一级子目录，禁止 `..`、符号链接逃逸。
- 禁止：`docker exec`、任意宿主命令、`--privileged` 新建容器（默认拒绝，需显式开启）、挂载宿主根目录或 socket 到新容器、修改自身容器（`nas-traffic-lens` 自我保护，见问题 8）。
- 镜像来源：默认允许 Docker Hub 官方镜像与已存在镜像；其他 registry 需显式开启。
- 并发：同一时刻只允许一个执行任务；执行中禁止新的写提案。
- 校验前置：所有写操作先做"干跑"（dry-run）校验，失败直接拒绝，不落盘。
- 敏感信息：AI 输入输出都不含密码/Token/密钥；compose 文件里的 env 支持 `${VAR}` 引用 `.env`，避免明文进提示词。

## 5. 数据模型与 API

| 类别 | 内容 |
| --- | --- |
| 新表 | `ops_agent_audits`（审计）、`ops_agent_calls`（用量，可与 ai_messages 合并） |
| 新 settings 键 | `ops_agent`（开关/档位/确认策略/配额）、`ui`（sidebarPinned、hash 路由开关） |
| 新 API | `POST /api/agent/chat`（SSE 流式，返回计划或回答）、`POST /api/agent/plan`、`POST /api/agent/execute`（proposalId）、`GET /api/agent/audits`、`POST /api/agent/rollback/{auditId}` |
| Compose API | `GET /api/compose/apps`、`GET /api/compose/app/{name}`、`POST /api/compose/app`（返回 diff 提案）、`POST /api/compose/app/{name}/up|down`（仍走提案确认） |
| 复用 | 设置类仍走现有 `/api/settings/*` 与 `collector.mutate_settings`；Docker 动作复用 `docker_container_action` |

## 6. 实施拆分与验收

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| P1 工作台与按需菜单 | 概览改工作台、菜单按需显示、hash 同步 | 首页无侧边栏；进入其他页面出现；刷新保持页面；移动端/明暗主题回归 |
| P2 只读 Agent | Agent 面板、JSON 计划协议、R0 工具、审计表、用量统计 | 能回答"今天哪个进程上传最多""哪个容器占用磁盘最多"；零写操作；单测覆盖工具参数校验与脱敏 |
| P3 设置与 Docker 生命周期 | settings.propose/apply 复用、容器 start/stop/restart 确认执行 | 变更前有 diff、确认后才生效；破坏性动作用例全部被拦截；审计可查 |
| P4 Compose 创建与更新 | 镜像加 docker CLI + compose 插件、挂载 compose 根、模板生成、校验/备份/原子替换/启动/回滚 | 真机创建一个新容器（如 `redis`）并出现在极空间容器列表；改端口后重建成功；失败自动回滚；删除功能默认关闭 |

## 7. 待确认问题（请先拍板）

1. **菜单策略**：只工作台隐藏（推荐 A），还是全站抽屉（B）？
2. **是否接受镜像增加 docker CLI + compose 插件**（约 +40MB），并新增挂载 `compose root`（读写）与重建本容器？不加就没法"写 compose 文件后启动"。
3. **compose 根目录**：默认用极空间应用根 `/tmp/zfsv3/nvme16/18181998187/data/docker`，新建应用放 `<root>/<应用名>/`，可以吗？还是希望放到单独的 `.../data/docker/nas-traffic-lens/apps/` 之类目录？
4. **权限档位默认到哪一级**：只读 / +设置 / +容器启停 / +compose 创建更新 / +删除？建议默认"只读 + 设置提案"，Docker 写操作需你在设置里显式打开。
5. **确认方式**：所有写操作都要人工点确认（推荐），还是允许低风险（如 restart）自动执行？
6. **自保护**：是否禁止 Agent 操作 `nas-traffic-lens` 自身容器（避免把自己改坏）？建议禁止，并在 UI 说明。
7. **极空间"应用列表"**：由我们创建的 compose 只保证出现在容器列表，不保证出现在极空间 Docker 的"应用"页（那是它自己的元数据，写入有风险）。可以接受吗？
8. **镜像来源**：是否限制只能用 Docker Hub 官方镜像 + 本地已有镜像？其他 registry 默认拒绝。
9. **Agent 是否允许 `docker exec`**：默认禁止（能拿到容器内 shell 就等于拿到其数据），确认一下。
10. **审计保留与回滚**：审计默认保留 90 天；回滚只支持有备份的操作，可以吗？
