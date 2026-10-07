# 容器健康巡检与 AI 研判设计（待确认）

> 状态：设计稿，未开发。目标是先确认开关、阈值和 AI 频率，再进入实现。
> 关联现状：`server/main.py` 的 `protection_loop`（每 5 秒评估容器保护规则）、`server/services/protection_state.py`（计数/冷却/锁定）、`server/services/container_targets.py`（容器选择器）、监控中心与通知渠道。

## 1. 背景

现有的“容器保护”只在 CPU / 内存 / 磁盘 I/O 超过阈值并持续一段时间后重启或停止容器。实际遇到的两类问题它覆盖不到：

- **持续报错直到崩溃**：Redis 之前磁盘报错（AOF/RDB 写入失败）时容器不断异常，但 CPU、内存都不高，磁盘写入速度也未必长期超过阈值；真正有价值的是日志里的 `MISCONF`、`No space left on device`、`I/O error` 这类持续错误，以及随之而来的退出码非 0、无限重启。
- **异常但未达阈值**：容器反复重启、OOMKilled、健康检查长期 unhealthy、上下行流量突然跑到平时的几十倍，这些都不是“资源占用超阈值”，而是“行为异常”。

同时用户希望**可选**地让 AI 参与判断，但必须能控制调用频率，避免 token 消耗失控。

## 2. 目标与非目标

目标：

1. 覆盖崩溃类异常：重启风暴、非 0 退出反复、OOMKilled、健康检查连续失败。
2. 覆盖资源类异常：磁盘持续大量读写（读写/总 I/O 均可）、容器级上下行流量异常（绝对值或相对基线）。
3. 覆盖日志类异常：窗口内错误行数量超阈值，支持自定义关键字/正则。
4. 把“某一刻超阈值”升级为有生命周期的**事件（incident）**：检测 → 观察 → 确认 → 动作 → 恢复，全过程留证据。
5. AI 研判作为**可选层**，带明确的四层开关和频率/预算限制，默认关闭。
6. 复用现有通知渠道、保护动作、SQLite 与监控中心，不改动“重启次数不限”的既有语义。

非目标：

- 不替代 Docker 自身的 `restart: unless-stopped` 策略，也不与它抢动作。
- 不做容器内进程级/系统调用级追踪（eBPF、perf 等），本期只到容器与日志粒度。
- 不做跨宿主的集中告警平台。

## 3. 现状与差距

| 能力 | 现状 | 差距 |
| --- | --- | --- |
| 规则与选择器 | 容器保护规则支持单选/多选/全部容器 | 可直接复用 |
| 资源阈值 | CPU、内存、`blkReadBps`、`blkWriteBps`、`blkIoBps` + 持续时间 | 已有，规则里补“持续读写”预设即可 |
| 动作与冷却 | restart / stop、计数、冷却、锁定 | 复用，新增“仅告警”动作 |
| 通知 | Webhook / IYUU / MeoW + 模板 | 复用 |
| 证据 | `alerts`、`alert_evidence` | 需新增事件级证据与时间线 |
| 崩溃识别 | 无 | 需 Docker events + inspect |
| 容器日志 | 未读取 | 需受控的 `logs?tail=` 读取 |
| 容器级网络异常 | 无（只有宿主机 WAN/LAN） | 需 `/stats` 的 network 字段 |
| AI 参与 | AI 中心可手动分析/对话 | 需自动研判 + 频率与预算闸门 |

## 4. 数据来源与采集开销

全部走现有的只读 `/var/run/docker.sock`，不需要新增权限或挂载。

| 来源 | 内容 | 频率 | 说明 |
| --- | --- | --- | --- |
| `GET /events` | `die` / `restart` / `oom` / `health_status` / `kill` / `destroy` | 常驻长连接 | 实时且几乎零成本，是崩溃类检测的首选 |
| `GET /containers/{id}/json` | `State.Status/ExitCode/OOMKilled/Health`、`RestartCount`、`StartedAt/FinishedAt`、重启策略 | 15 秒（仅启用巡检的容器） | 把 events 事件与当前状态对齐 |
| `GET /containers/{id}/stats?stream=false` | CPU、内存、blkio、network | 10 秒（仅启用巡检的容器，可调 5–60） | 磁盘/网络异常的采样来源，与现有 5 秒保护循环解耦 |
| `GET /containers/{id}/logs?tail=N&since=` | 日志尾部 | 仅在事件确认后按需，单容器 30 分钟内最多 1 次 | 先本地正则过滤，只保留命中行作为证据与 AI 上下文 |
| 宿主机指标（已有） | 磁盘、网卡速率 | 复用 | 用于判断“是容器异常”还是“整机异常” |

要点：**没有启用任何巡检规则的容器不会被轮询**，默认只订阅 events。因此在当前这台 39 个容器（27 个运行中）的 NAS 上，新增开销约等于 0；只对选中的容器做 stats/inspect。

### 4.1 实测确认（2026-10-07，极空间 NAS / 容器内只读 socket）

| 检查项 | 结果 |
| --- | --- |
| `GET /containers/json?all=1` | HTTP 200，39 个容器（含已停止） |
| inspect：`RestartCount` / `State.ExitCode` / `OOMKilled` | 可读（示例容器 restarts=0 / exit=0 / oom=false） |
| inspect：`State.Health.Status` | 有 healthcheck 的容器返回 `healthy`；未配置的返回 null |
| inspect：`HostConfig.LogConfig.Type` | 全部为 `json-file`，日志接口可用 |
| `GET /events`（container 过滤） | 4 秒收到 13 条事件，长连接可用 |
| `GET /containers/{id}/logs?tail=3` | HTTP 200，可读 |

也就是说：**本期需要的所有数据，用现有的只读 `/var/run/docker.sock` 挂载即可拿到，不需要新增权限或 Compose 改动**。

## 5. 规则模型

建议新增设置键 `health_rules`，结构与容器保护保持一致，便于前端复用同一套编辑器：

```json
{
  "id": "health-redis-disk",
  "name": "Redis 磁盘与崩溃巡检",
  "enabled": true,
  "severity": "critical",
  "targetMode": "selected",
  "containers": [{ "containerId": "…", "containerName": "redis" }],
  "confirmSeconds": 120,
  "cooldownMinutes": 30,
  "action": "notify",
  "checks": [
    { "kind": "restart_loop", "count": 3, "windowMinutes": 10 },
    { "kind": "crash_exit", "count": 2, "windowMinutes": 30 },
    { "kind": "oom", "count": 1, "windowMinutes": 60 },
    { "kind": "unhealthy", "consecutive": 3 },
    { "kind": "disk_sustained", "metric": "blkWriteBps", "threshold": 52428800, "seconds": 300 },
    { "kind": "log_errors", "patterns": ["MISCONF", "No space left", "I/O error", "panic", "FATAL"], "count": 20, "windowMinutes": 10 },
    { "kind": "net_anomaly", "direction": "tx", "thresholdBps": 52428800, "seconds": 300 }
  ],
  "ai": { "enabled": false, "minSeverity": "critical" },
  "notify": { "channelMode": "all", "channelIds": [] }
}
```

建议默认值（可在 UI 改）：

| 检查 | 默认 | 理由 |
| --- | --- | --- |
| `restart_loop` | 10 分钟内 3 次 | 正常升级重启不会这么密 |
| `crash_exit` | 30 分钟内 2 次非 0 退出 | 过滤一次性失败 |
| `oom` | 60 分钟内 1 次 | OOM 一次就值得报 |
| `unhealthy` | 连续 3 次 | 与 Docker healthcheck 周期解耦 |
| `disk_sustained` | 50 MB/s 持续 5 分钟 | 覆盖 Redis AOF/RDB 风暴，又不会误伤普通日志写入 |
| `log_errors` | 10 分钟内 20 行命中 | 关键字可自定义，默认给一组常见致命模式 |
| `net_anomaly` | 50 MB/s 持续 5 分钟，或相对 7 天基线 > 3σ | 兼容“新服务首次跑满带宽”的绝对值口径 |

## 6. 事件状态机

```
detected ──(持续 confirmSeconds)──▶ confirmed ──(执行动作)──▶ acting ──▶ resolved
    │                                   │                                  ▲
    └──(窗口内自行恢复)──▶ suppressed ────┴──(冷却期内重复)──▶ merged ───────┘
```

- **去抖**：同一规则同一容器在确认窗口内反复穿越阈值，只产生一个事件，证据累加。
- **合并**：冷却期内再次命中追加到同一事件的 `occurrences`，不新建、不重复通知。
- **恢复**：连续 3 次检查正常或容器恢复 running 且退出码为 0 → `resolved`，记录持续时长。
- **证据**：首次与最近一次指标快照、命中的日志样本（最多 50 行）、事件时间线、动作与每个通知渠道的投递结果。
- **动作前校验**：与现有保护一致——同一容器同一时刻只允许一个动作；`locked` 状态下只记录不动作。

## 7. AI 研判设计（重点：开关与频率）

### 7.1 四层开关（全部默认关闭）

| 层级 | 位置 | 默认 | 作用 |
| --- | --- | --- | --- |
| L1 全局 | 设置 → 健康巡检 → AI 研判 | 关 | 一键停用所有自动 AI 调用 |
| L2 规则级 | 每条规则内的 `ai.enabled` + `ai.minSeverity` | 关 / critical | 只让重要规则触发 AI |
| L3 预算闸门 | `aiMaxCallsPerHour`、`aiMaxCallsPerDay`、`aiMaxTokensPerDay` | 4 / 24 / 200000 | 触顶即停，写一条“已达预算”告警 |
| L4 手动 | 事件详情里的“立即研判” | 可用 | 不计入自动预算（可选：也计入，待确认） |

### 7.2 频率参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `aiIntervalMinutes` | 30 | 巡检汇总周期：事件确认后先入队，按这个周期批量处理，而不是一触发就调用 |
| `aiMinGapMinutes` | 60 | 同一容器两次 AI 调用的最小间隔 |
| `aiCooldownMinutes` | 30 | 事件恢复后再次调用的冷却 |
| `aiBatchWindowMinutes` | 5 | 多容器同时异常时合并成一次调用 |
| `aiMaxCallsPerHour` / `aiMaxCallsPerDay` | 4 / 24 | 硬上限 |
| `aiMaxTokensPerDay` | 200000 | 估算值，触顶停止自动调用 |
| `aiQuietHours` | 关闭（示例 02:00–07:00） | 静默期只累积证据 |
| `aiLogLines` | 20（最大 100） | 上下文大小控制 |

### 7.3 调用决策流程

```
事件 confirmed
  → 命中规则的 ai.enabled 且 severity ≥ minSeverity      （L2）
  → 全局开关开                                            （L1）
  → 距离该容器上次调用 ≥ aiMinGapMinutes，且不在恢复冷却期
  → 本小时/本日调用次数与估算 token 未触顶                 （L3）
  → 不在静默时段
  → 入待研判队列；每 aiIntervalMinutes 汇总一次
      · 单容器 → 一次调用
      · 多容器（aiBatchWindowMinutes 内）→ 合并为一次批量研判
  → 记录 ai_call_log（模型、耗时、估算 token、结果或错误）
```

### 7.4 上下文与安全边界

- 只发送结构化事实：容器名/镜像、状态与退出码、重启次数、OOM 标志、健康状态、CPU/内存/磁盘/网络速率、命中规则与阈值、**经正则过滤后的日志尾部**。
- 不发送：环境变量、任何密钥/Token、完整 inspect、宿主机路径、其他容器数据（批量时只发摘要）。
- 输出要求为 JSON：`{原因排序, 置信度, 建议动作, 需要补充的信息}`；解析失败时降级保存纯文本，不阻塞事件流。
- 复用 AI 设置助手已有的安全边界（不读取/修改密码、API Key、Webhook Token、Docker socket、DB/日志路径，不执行 SQL/宿主命令）。

### 7.5 用量可视化与熔断

- 设置页显示：本小时/今日调用次数、估算 token、预算剩余、最近 20 次调用（时间、容器、模型、耗时、成功/失败原因）。
- 触顶后：停止自动调用，事件继续正常检测与通知，并在监控中心提示“AI 研判已达预算，次日 00:00 重置”。
- 建议巡检单独配置模型/供应商（便宜模型或本地 Ollama），不复用聊天模型。

### 7.6 成本估算

| 场景 | 单次 token（输入+输出） | 每天调用 | 每天 token |
| --- | --- | --- | --- |
| 单容器单事件 | ≈ 1.2k–3k | 按默认配额最多 24 次 | ≈ 40k–90k |
| 批量研判（3 容器） | ≈ 3k–6k | 常见 2–4 次 | ≈ 10k–25k |
| 实际稳态（多数日子无事件） | — | 0–2 次 | ≈ 0–6k |

默认配额下即使天天打满，也在 10 万 token/天量级；把 `aiIntervalMinutes` 调到 60、`aiMinGapMinutes` 调到 180，可再降一半以上。

## 8. 存储与接口

- 新增表：
  - `container_incidents`：`id, ruleId, containerId, containerName, kind, severity, status, firstSeenAt, lastSeenAt, resolvedAt, confirmSeconds, occurrences, evidenceJson, actionTaken, actionAt, aiStatus, aiCalledAt, aiVerdictJson`
  - `ai_call_log`：`id, ts, incidentId, containerName, provider, model, promptTokens, completionTokens, durationMs, status, error`
- 复用 `settings` 保存 `health_rules` 与 `ai_triage`。
- 保留策略：事件 90 天 / 最多 5000 条，调用日志 30 天，超限按时间清理（沿用现有清理任务）。
- 接口：
  - `GET/POST /api/settings/health`（规则与 AI 配置）
  - `GET /api/health/incidents`（支持状态、容器、时间筛选）
  - `POST /api/health/incidents/{id}/ack`、`POST /api/health/incidents/{id}/analyze`
  - `GET /api/health/ai-usage`

## 9. UI 设计

- **设置 → 新增「健康巡检」分区**（与“容器保护”并列）：规则列表、每规则的检查项、动作、AI 开关与最低级别；顶部单独的“AI 研判”卡片放全局开关与频率/预算。
- **监控中心 → 事件列表**：状态标签、持续时间、命中规则、动作结果、AI 结论摘要，点开看时间线与证据（含日志样本）。
- **Docker 卡片**：右上角加事件角标（异常 / 观察中 / 已恢复），不改变现有手风琴结构。
- **概览页**：只加一个“异常容器 N”指标，不新增图表。

## 10. 分批实施计划

| 批次 | 内容 | 主要文件 | 验收 |
| --- | --- | --- | --- |
| P1 | 事件模型 + events 订阅 + inspect 轮询 + 重启/退出/OOM/健康规则 + 通知 + 监控中心列表 | `server/services/health_incidents.py`（新）、`server/main.py`、`front-end/src/App.vue` | 单测：状态机、去抖、合并、恢复；真机：`docker restart` 人为制造重启风暴并观察事件与通知 |
| P2 | 磁盘持续读写、日志错误风暴、网络异常规则 + 日志采集与正则过滤 | `server/services/health_incidents.py`、`server/services/container_logs.py`（新） | 单测：窗口统计、正则、限流；真机：用 `dd`/`fallocate` 或临时容器制造写入 |
| P3 | AI 研判：四层开关、频率、预算、去重、用量面板、调用日志 | `server/services/ai_triage.py`（新）、`server/main.py`、`front-end/src/App.vue` | 单测：预算熔断、最小间隔、批量合并；真机：用 mock provider 验证零调用与超预算行为 |
| P4 | 静默时段、本地模型、事件保留清理、桌面端同步 | 同上 | 桌面端与手机端视觉回归 |

每批都遵守现有约定：不改现有保护语义、不动历史数据、验证使用隔离数据、不手动触发线上容器的真实动作作为测试。

## 11. 风险与限制

- **误报**：确认窗口 + 冷却 + 合并可抑制抖动；仍建议先跑一周“只告警不动作”再考虑自动重启。
- **日志读取开销**：只在事件确认后按需拉取，限制 `tail` 与频次，先本地过滤再入库。
- **Docker socket 压力**：events 常驻 + 仅对启用规则的容器做 stats/inspect；间隔可调到 60 秒。
- **AI 成本**：默认关闭 + 四层闸门 + 批量合并；预算触顶自动停。
- **权限**：只读 socket 即可；容器日志依赖 Docker 保留的 json-file 日志（若宿主用 journald 驱动，日志项自动降级为“不可用”并提示）。
- **容器数很多时**：默认不启用任何规则，新增开销接近 0。

## 12. 待确认问题

1. 默认阈值是否接受？特别是磁盘持续读写 **50 MB/s / 5 分钟**、日志错误 **20 行 / 10 分钟**、重启 **3 次 / 10 分钟**。
2. AI 默认频率与预算：**30 分钟汇总、同容器最小 60 分钟、每小时 4 次、每天 24 次、每天 20 万 token** 是否合适？
3. AI 研判结果是否允许自动执行重启/停止？建议先只告警 + 给建议，确认稳定后再开自动动作。
4. 是否接受新增 `container_incidents`、`ai_call_log` 两张表与 `health_rules`、`ai_triage` 两个设置键（按仓库惯例，新表需先确认）。
5. 巡检默认范围：只覆盖“规则里选中的容器”，还是一键给所有容器套一组默认规则（默认只订阅 events、不轮询统计）？
6. 巡检用哪个模型？建议单独配置一个便宜模型或本地 Ollama，避免占用聊天模型的额度。
7. 是否需要“事件只看不回”的静默模式（只记录不通知）用于前两周观察期？
