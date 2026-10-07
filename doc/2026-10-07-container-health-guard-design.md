# 容器健康守护（Container Health Guard）设计

> 状态：设计稿，未实现。本文只描述方案与默认值，代码改动需另行确认。
> 关联现状：`server/main.py` 的 `protection_loop`（每 5 秒评估容器保护）、`server/services/protection_state.py`、`server/services/container_targets.py`、`server/services/ai.py`、`server/services/notifications.py`、`doc/2026-10-07-container-protection-daily-alerts.md`、`docker-compose.nas.yml`。

## 1. 目标与非目标

### 1.1 目标

把现有"容器保护"从**单点阈值 → 动作**扩展为覆盖"持续报错导致崩溃"的**健康守护**：

1. 崩溃类：非 0 退出、OOMKilled、RestartCount 快速增长、长时间 restarting、短时间内多次退出。
2. 日志类：错误关键字（`error`/`panic`/`fatal`/`OOM`/`No space left on device` 等）在滑动窗口内的速率超限——Redis 磁盘报错就是这一类。
3. 磁盘类：容器 blkio 读写速率与累计量的**持续性**超限。
4. 网络类：容器 rx/tx 速率相对基线的突增、突降、长时间恒为零。
5. 资源类：CPU / 内存持续占用（复用现有信号，不重复实现）。
6. 健康检查：`health_status` 长时间 unhealthy。
7. 可选 AI 分析：把命中的证据交给 AI 判断成因与建议，**但必须能用开关和配额严格控制调用次数与 token 成本**。

### 1.2 与现有「容器保护」的关系：**扩展同一模块，不新开并行系统**

建议在现有容器保护规则上做**向后兼容的扩展**，理由：

- 目标选择器（`single` / `selected` / `all` + Compose 项目/副本匹配）、冷却与计数（`protection_state`）、通知渠道与模板、告警历史（`alerts` + `alert_evidence`）都已存在且经过验收，重建一套会分叉行为。
- 现有规则的 `conditions[]` 已经是"指标 + 比较 + 阈值 + 持续时间"的通用结构，新增信号只是扩展指标枚举与窗口语义。
- 现有语义必须保留：**重启次数不限**、累计次数只记录、旧锁定自动解除（见交付记录）。

因此：新增独立的 `signal` 类型（崩溃/日志/网络）与事件层，**复用同一份规则列表、同一套动作与通知**；原有 `cpuPercent` 等阈值规则行为不变。

### 1.3 非目标（本期明确不做）

- 不实现"执行自定义命令/脚本"动作（权限边界过大，见 §4.4）。
- 不做容器内进程级、系统调用级追踪（eBPF/perf），只到容器与日志粒度。
- 不做跨主机集中告警、不做多租户。
- 不改变现有保护规则的判定与动作语义，不改历史数据。
- 不自动修改 Docker 的 `restart policy`。

## 2. 信号清单

采集统一走只读 `/var/run/docker.sock`（compose 已 `privileged: true` + `pid: host` + `docker.sock:ro`）。下表"默认阈值"均可按规则覆盖。

| # | 信号 | 采集方式 | 数据来源 | 频率 | 单位 | 默认阈值 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 非 0 退出 | `events` 的 `die`（`Actor.Attributes.exitCode`）+ inspect 复核 | Docker events / inspect `State.ExitCode` | 事件实时 | 次 | 30 分钟内 ≥ 2 次 |
| 2 | OOMKilled | `events` 的 `oom` + inspect 复核 | Docker events / inspect `State.OOMKilled` | 事件实时 | 次 | 60 分钟内 ≥ 1 次 |
| 3 | RestartCount 增速 | 定时 inspect 取 `RestartCount` 求差 | inspect `/containers/{id}/json` | 15 秒 | 次 | 10 分钟内 ≥ 3 次 |
| 4 | restarting 持续 | 定时 inspect 取 `State.Status` | inspect | 15 秒 | 秒 | 持续 ≥ 120 秒 |
| 5 | 短时间多次退出 | events `die` 时间序列 | Docker events | 事件实时 | 次 | 5 分钟内 ≥ 4 次 |
| 6 | 日志错误速率 | `logs?tail=` 拉取后本地正则统计，滑动窗口 | Docker logs（json-file） | 事件触发 + 每 60 秒巡检 | 行/分钟 | 10 分钟内 ≥ 20 行命中 |
| 7 | 日志致命关键字 | 同上，单独关键字段 | Docker logs | 同上 | 次 | 出现 `No space left` / `I/O error` / `panic` / `MISCONF` 各 ≥ 1 次 |
| 8 | blkio 写入速率 | `stats?stream=false` 的 `blkio_stats` 求差 | Docker stats / cgroup blkio | 15 秒 | B/s | ≥ 50 MB/s 持续 300 秒 |
| 9 | blkio 读取速率 | 同上 | 同上 | 15 秒 | B/s | ≥ 80 MB/s 持续 300 秒 |
| 10 | blkio 累计量 | 同上，窗口内累计 | 同上 | 15 秒 | B | 10 分钟内累计写入 ≥ 10 GB |
| 11 | 网络 rx/tx 突增 | `stats` 的 `networks` 求差，与 7 天同小时基线比较 | Docker stats | 15 秒 | B/s | > 基线 3σ 且 ≥ 10 MB/s，持续 300 秒 |
| 12 | 网络长时间恒零 | 同上 | 同上 | 15 秒 | 秒 | running 状态下 ≥ 1800 秒 rx+tx 均为 0 |
| 13 | CPU 持续占用 | 复用现有采样 | Docker stats | 5 秒（现有循环） | % | 沿用现有规则，默认不新增 |
| 14 | 内存持续占用 | 复用现有采样 | Docker stats | 5 秒（现有循环） | % / B | 沿用现有规则，默认不新增 |
| 15 | health_status | `events` 的 `health_status` + inspect `State.Health` | Docker events / inspect | 事件实时 | 秒 | 连续 3 次 unhealthy 或持续 ≥ 300 秒 |

补充说明：

- 信号 11/12 在 `network_mode: host` 的容器上**没有独立 netns 统计**（Docker stats 的 `networks` 为空），此时降级为"不可用"并在事件里标注口径，不再凭空判断（见 §10 已知限制）。
- 信号 6/7 依赖 json-file 日志驱动；若宿主使用 journald，标记为不可用并提示，不静默失败。
- 短命容器（存活 < 采样间隔）只能靠 events（信号 1/2/5）发现，stats 类信号会漏，属于已知限制。

### 2.1 只读 socket 实测确认（2026-10-07，极空间 NAS 容器内）

| 检查项 | 结果 |
| --- | --- |
| `GET /containers/json?all=1` | HTTP 200，39 个容器（含已停止） |
| inspect：`RestartCount` / `State.ExitCode` / `OOMKilled` | 可读（示例容器 restarts=0 / exit=0 / oom=false） |
| inspect：`State.Health.Status` | 有 healthcheck 的容器返回 `healthy`；未配置的返回 null |
| inspect：`HostConfig.LogConfig.Type` | 全部为 `json-file`，日志接口可用 |
| `GET /events`（container 过滤） | 4 秒收到 13 条事件，长连接可用 |
| `GET /containers/{id}/logs?tail=3` | HTTP 200，可读 |

也就是说：**本期需要的所有数据，用现有的只读 `/var/run/docker.sock` 挂载即可拿到，不需要新增权限或 Compose 改动。**

## 3. 规则模型

在现有 `settings.container_protection` 规则列表上做**可选字段扩展**（旧规则 JSON 不变，读取时补默认值）。

```json
{
  "id": "guard-redis-disk",
  "name": "Redis 磁盘与崩溃守护",
  "enabled": true,
  "targetMode": "selected",
  "containers": [{ "containerId": "…", "containerName": "redis" }],
  "logic": "or",
  "confirmSeconds": 120,
  "cooldownSeconds": 1800,
  "dedupeKey": "container+signal",
  "action": "notify",
  "maxActions": 3,
  "actionsPerHour": 2,
  "channelMode": "all",
  "channelIds": [],
  "signals": [
    { "kind": "restart_growth", "count": 3, "windowSeconds": 600 },
    { "kind": "exit_nonzero", "count": 2, "windowSeconds": 1800 },
    { "kind": "oom_killed", "count": 1, "windowSeconds": 3600 },
    { "kind": "restarting_state", "seconds": 120 },
    { "kind": "log_errors", "patterns": ["No space left", "I/O error", "MISCONF", "panic", "fatal"], "count": 20, "windowSeconds": 600 },
    { "kind": "blk_write_rate", "bytesPerSecond": 52428800, "seconds": 300 },
    { "kind": "net_spike", "direction": "tx", "bytesPerSecond": 10485760, "zscore": 3, "seconds": 300 }
  ],
  "ai": { "enabled": false, "minSeverity": "critical" }
}
```

| 字段 | 默认 | 说明与理由 |
| --- | --- | --- |
| `logic` | `or` | 健康信号之间建议"任一命中即事件"；资源类多条件仍可用 `and` |
| `confirmSeconds` | 120 | 信号需持续满足该时长才升级为 confirmed，抑制抖动 |
| `cooldownSeconds` | 1800 | 同一容器同一规则恢复前不重复建事件（沿用现有冷却语义） |
| `dedupeKey` | `container+signal` | 供冷却期去重；可选 `container+rule`、`rule` |
| `maxActions` | 3 | 沿用现有字段：单事件内最多执行动作次数 |
| `actionsPerHour` | 2 | 新增：防止"重启风暴"（容器反复重启又被反复重启） |
| `action` | `notify` | 见 §4 |
| `ai.enabled` | `false` | 见 §5 |
| `ai.minSeverity` | `critical` | 只有确认后的严重事件才触发 AI |

**生效范围**沿用现有三种模式：单容器 / 多选 / 全部运行中容器；多选中支持 Compose 项目 + 服务 + 副本号匹配（`container_targets.py` 已有），并新增按 **Compose 项目**、**镜像名**、**Docker 标签**批量选择的便捷入口（UI 层，存储仍展开为 `containers[]`）。

**组合与窗口语义**：每个 `signal` 独立维护滑动窗口计数（环形时间戳数组，默认保留 1 小时），`logic` 决定信号之间如何合并；`confirmSeconds` 作用于合并后的结果。

## 4. 动作

### 4.1 动作类型

| 动作 | 行为 | 默认 |
| --- | --- | --- |
| `none` | 只写事件与证据，不通知不动作 | — |
| `notify` | 写事件 + 走现有通知渠道 | **默认**（观察期安全） |
| `restart` | 复用现有保护重启路径（计数不限、冷却生效） | 需显式选择 |
| `stop` | 复用现有停止路径 | 需显式选择 |

### 4.2 通知复用

直接复用 `notifications.py`：模板变量（`{message}` / `{value}` / `{threshold}` / `{value_human}` / `{threshold_human}` / `{timestamp}` / `{rule_id}`）与 `safe_notification_detail()` 的脱敏逻辑；新增事件级变量 `{container}`、`{signal}`、`{duration}`、`{ai_summary}`（AI 未启用时为空串）。渠道选择沿用 `channelMode`（all/selected/none）。

### 4.3 冷却与最大次数

- 事件级：`confirmSeconds` 确认后才动作，`cooldownSeconds` 内不重复动作。
- 动作级：`maxActions`（单事件内）+ `actionsPerHour`（跨事件，新增，默认 2）。
- 全局熔断：同一容器 10 分钟内被守护重启 ≥ 3 次时，进入 `locked`（沿用现有锁定状态），只记录与通知，直到人工在设置页"重置并解锁"。
- 与 Docker `restart: always` 叠加时，动作前检查容器是否处于 `restarting`：是则只记录不重复重启。

### 4.4 自定义命令：**本期不实现**

原因：需要在容器或宿主执行任意命令，会突破当前"只读 docker.sock + 固定动作"的信任边界，且与"不执行 SQL/宿主命令"的既有产品约束冲突。若未来要做，需单独设计：白名单命令模板、参数化、独立开关、二次确认、审计表。本文只在"待确认问题"里记录。

## 5. AI 分析的门控设计（重点）

设计目标：**AI 默认关闭；开启后也能把每日调用次数与 token 量锁死在上限内。**

### 5.1 两种触发模式

| 模式 | 行为 | 适用 | 默认 |
| --- | --- | --- | --- |
| 事件触发 | 只有事件 confirmed 且满足严重级别才分析 | 异常少、想省钱 | **默认** |
| 定时巡检 | 按固定间隔扫描"未分析过的活跃事件"并批量分析 | 想主动发现 | 可选 |
| 关闭 | 完全不调用 | — | — |

两种模式都不做"每次阈值抖动就调用"：**先攒事件，再按间隔批量处理**。`intervalMinutes` 是**扫描周期**：每轮只判断有没有待分析的新事件，没有事件就不产生任何 AI 调用。

### 5.2 开关与档位（全部给具体默认值）

| 配置项 | 默认 | 可选档位 | 理由 |
| --- | --- | --- | --- |
| `ai.enabled`（总开关） | **关** | 开/关 | 默认不花钱 |
| `ai.mode` | `event` | `event` / `interval` / `off` | 事件触发最省 |
| `ai.intervalMinutes` | **10**（mode=interval 时生效） | 10 / 15 / 30 / 60 / 180 / 360 | 10 分钟一轮能更快发现"持续报错"；这是**巡检/扫描周期**，每轮只检查是否出现需要分析的新事件，并不是每轮都调用 AI，实际调用仍受冷却、小时/日上限与 token 预算约束（见 §5.6） |
| `ai.maxCallsPerDay` | **24** | 1–200 | 硬上限，触顶即停 |
| `ai.maxCallsPerHour` | **4** | 1–24 | 防止短时间连环调用 |
| `ai.perContainerCooldownMinutes` | **60** | 15–720 | 同一容器一小时最多分析一次 |
| `ai.eventCooldownMinutes` | **30** | 5–720 | 事件恢复后再次分析的冷却 |
| `ai.evidenceLogLines` | **40** | 0–200 | 单次证据包日志行数上限 |
| `ai.evidenceMaxBytes` | **8192** | 1024–65536 | 证据包总字节上限，超出按优先级截断 |
| `ai.tokenBudgetPerDay` | **200000** | 10000–2000000 | 估算 token 预算，触顶停止自动分析 |
| `ai.onBudgetExceeded` | `stop` | `stop` / `notify_only` | 超预算后只记录事件与通知，不再调用 |
| `ai.retry` | 2 次，退避 30s / 120s | 0–3 次 | 网络抖动可重试，429/401 不重试 |
| `ai.model` / `ai.provider` | 复用 AI 设置，建议单独配置便宜模型或本地 Ollama | — | 避免占用聊天额度 |
| `ai.quietHours` | 关闭（示例 02:00–07:00） | — | 静默期只积累证据 |

### 5.3 调用判定流程

```
事件 confirmed 且 severity ≥ rule.ai.minSeverity
  → 全局 ai.enabled = 开
  → mode=event：立即入队；mode=interval：等到下个 interval 汇总
  → 不在 perContainerCooldown / eventCooldown 内
  → 本小时、本日调用次数未达上限，且本日估算 token 未超预算
  → 证据包指纹未命中缓存
  → 调用 → 记录 ai_guard_calls（含估算 token）→ 结果写回事件
```

### 5.4 证据包内容与脱敏

发送内容（JSON）：

- 容器：名称、镜像、Compose 项目/服务、状态、退出码、OOM 标志、重启次数、运行时长。
- 命中信号：规则名、信号类型、阈值、实际值、持续时间、窗口内计数。
- 指标摘要：CPU%、内存%、blkio 读写速率、net rx/tx 速率（各 1 个当前值 + 窗口均值）。
- 日志：**正则过滤后**最多 `evidenceLogLines` 行，只保留命中关键字的行，单行截断 400 字符。

裁剪顺序（超 `evidenceMaxBytes` 时）：日志行数 → 指标历史点 → 非命中信号的上下文，最后只保留命中信号。

脱敏（发送前强制）：

- 替换疑似密钥：`(?i)(password|passwd|token|secret|api[_-]?key|authorization)\s*[:=]\s*\S+` → `[redacted]`。
- 替换 URL 中的凭据段与长随机串（≥ 24 位 base64/hex）。
- **不发送**：环境变量、完整 inspect、宿主机路径、其他容器的日志、AI/通知/Webhook 凭据、Docker socket 路径。
- 复用 `ai.py` 的 baseUrl 校验与 `notifications.py` 的脱敏思路，保持与现有"设置助手不读敏感项"的边界一致。

### 5.5 结果处理

AI 返回结构化 JSON：`{summary, causes:[{name, confidence}], severity, suggestedAction, needsMoreInfo}`；解析失败保留原始文本。

- 结果写入事件（`aiStatus` + `aiVerdict`），在监控中心展示，并可选附加到通知模板 `{ai_summary}`。
- **默认不允许 AI 直接执行动作**（`ai.autoAct=false`）。理由：AI 结论是概率性的，误判会导致误重启/误停止，而容器保护已经能在明确阈值下自动动作；AI 的定位是"解释与建议"，不是"执行器"。人工可在事件详情一键执行建议动作。

### 5.6 成本估算与调用次数对比

单次分析：输入 ≈ 1.2k–2.5k tokens（提示词 ~300 + 指标摘要 ~400 + 日志 40 行 600–1500 + 事件上下文 ~200），输出 ≈ 300–700 tokens，合计 **≈ 1.5k–3.2k tokens/次**。

| 模式 | 每日调用上限 | 每日 token（按 2.5k/次） | 说明 |
| --- | --- | --- | --- |
| 事件触发（默认） | 实际 0–6 次 | 0–15k | 无异常的日子为 0 |
| 定时巡检 10 分钟（默认） | 144 次扫描 → 实际调用被截断为 24 次 | ≈ 60k | 扫描本身零 token；调用次数由 `maxCallsPerDay=24` 与 60 分钟容器冷却决定 |
| 定时巡检 60 分钟 | 24 次扫描 | ≈ 60k（仅在真有事件时） | 与 `maxCallsPerDay=24` 一致 |
| 定时巡检 30 分钟 | 被日上限截断为 24 次 | ≈ 60k | 想真按 48 次跑需手动调高日上限 |
| 定时巡检 15 分钟 | 被日上限截断为 24 次 | ≈ 60k | 不建议；日志与 token 成本都翻倍 |
| 触顶行为 | 停止自动调用 | 0 | 写一条"已达预算"事件，次日 00:00 重置 |

### 5.7 去重与缓存

- **指纹**：`sha256(containerId + ruleId + signalKind + 证据包内容摘要)`。
- 冷却期内同指纹不重复分析；同容器不同信号在 `perContainerCooldownMinutes` 内合并为一次分析。
- 证据包完全相同的调用命中**结果缓存**（默认 TTL 30 分钟，最多 100 条），缓存命中不计入次数与 token。
- 多容器同时异常时（默认开启）合并为一次"批量研判"：每条只发摘要（不含日志），命中容器数上限 5。

## 6. 数据模型与存储

| 表 / 键 | 用途 | 关键字段 | 索引 | 保留 |
| --- | --- | --- | --- | --- |
| `container_guard_events`（新） | 事件生命周期 | `id, rule_id, container_id, container_name, signal_kind, severity, status(detected/confirmed/resolved/suppressed), fingerprint, first_seen_at, last_seen_at, resolved_at, occurrences, evidence_json, action, action_at, ai_status, ai_called_at, ai_verdict_json` | `(status, last_seen_at)`、`(container_id, first_seen_at)`、`(fingerprint, last_seen_at)` | 90 天 / 最多 5000 条 |
| `ai_guard_calls`（新） | AI 调用与用量 | `id, ts, event_id, container_name, provider, model, prompt_tokens_est, completion_tokens_est, duration_ms, status, error` | `(ts)`、`(container_name, ts)` | 30 天 |
| `alerts` + `alert_evidence`（复用） | 通知与历史列表、渠道回执 | 现有结构 | 现有 | 现有 |
| `settings.container_guard_rules`（新键） | 守护规则 | 见 §3 | — | — |
| `settings.container_guard_ai`（新键） | AI 门控配置 | 见 §5.2 | — | — |
| `settings.container_guard_state`（新键） | 滑动窗口与去重状态 | 每个容器/规则的计数、时间戳、最近指纹、每小时动作计数 | — | 只保留最近 1 小时 |

与现有 `settings` 表的关系：继续用 `key/value` 存 JSON，读写走现有 `db.get_setting` / `db.set_setting`，并在保存时做一次 schema 校验；**不迁移、不改写**现有 `container_protection` 键。

## 7. API 设计

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/settings/container-guard` | 返回规则、AI 门控配置、可用信号目录、AI 用量摘要 |
| POST | `/api/settings/container-guard` | 保存规则（沿用现有校验与草稿保护约定） |
| POST | `/api/settings/container-guard/ai` | 保存 AI 门控配置（含总开关、模式、间隔、配额、预算） |
| GET | `/api/guard/events` | 事件列表，支持 `status` / `container` / `signal` / `start` / `end` / `limit` |
| POST | `/api/guard/events/{id}/ack` | 人工确认/关闭事件 |
| POST | `/api/guard/events/{id}/analyze` | 手动立即分析（默认计入当日次数与 token，见待确认问题 3） |
| GET | `/api/guard/ai-usage` | 今日/本小时调用次数、估算 token、预算余量、最近 20 条调用 |

校验与鉴权：与现有 API 一致（登录会话 + `DASHBOARD_PASSWORD`）；入参限制长度与枚举（信号类型白名单、阈值 ≥ 0、间隔只能取档位值、日志行数 ≤ 200、字节 ≤ 65536）；目标容器必须存在于当前容器列表或允许"暂不可见"（沿用现有容器身份匹配规则）；所有写操作走现有配置审计（`configuration_audit`）。

## 8. 前端设计

### 8.1 监控中心

新增「容器健康」卡片，位于现有规则状态卡片之后：

- 顶部统计：未恢复事件数、今日已恢复数、AI 调用次数/预算余量。
- 事件列表：容器名 + 信号标签（崩溃/日志/磁盘/网络）+ 状态徽标（观察中/已确认/已恢复/已抑制）+ 持续时间 + 动作结果 + AI 结论摘要（一行）。
- 展开行：证据时间线、命中的日志样本（等宽字体、最多 20 行、可复制）、每个通知渠道的投递结果、AI 完整结论与"执行建议动作"按钮（需二次确认）。
- 空状态文案区分：未配置规则 / 已配置但无事件 / 日志信号不可用（journald）/ 网络信号不适用于 host 网络容器 / AI 未启用 / AI 已达预算。

### 8.2 设置页

在现有分区（常用设置、流量告警、容器保护、通知渠道、AI 配置、维护与高级）中新增「健康巡检」分区，沿用分区独立保存与草稿保护：

- 规则列表：复用容器保护的编辑器结构（目标选择器、条件行、持续时间、冷却、动作、通知渠道），条件行改为"信号"下拉 + 对应参数（计数/窗口/速率/秒数），支持折叠编辑。
- 顶部「AI 分析」卡片：总开关（开关控件）、模式（三选一 radio）、巡检间隔（下拉档位，仅在 interval 模式可用）、每日最大次数、每小时最大次数、容器冷却、事件冷却、日志行数、预算 token（数字输入 + 当前用量进度条）、超预算行为（下拉）、静默时段（可选，时间范围）。
- 保存反馈沿用现有：分区级"保存"、未保存提示、"当前设置已同步"、失败保留输入。
- 主题与响应式沿用 `front-end/src/styles/console-theme.css`（明暗主题 + 手机端单列）。

### 8.3 Docker 页

容器卡片右上角增加事件角标（异常/观察中/已恢复），不改变现有手风琴结构。

## 9. 性能与安全

**采集开销**

- events：常驻 1 条长连接，开销可忽略（实测 4 秒 13 条事件）。
- stats/inspect：只对"启用守护规则的容器"执行，默认 15 秒一轮；单轮容器数上限默认 50，超出部分只保留 events。
- 与现有 5 秒保护循环的关系：复用同一轮采集，资源类信号不额外采样；崩溃/日志/网络信号走独立慢循环（15 秒）。
- 日志：只在事件 confirmed 后拉取；`tail ≤ 200` 行、单次 ≤ 64 KB、单容器每 5 分钟最多 1 次；先本地正则过滤，入库只留命中行（≤ 50 行）。

**安全边界**

- 部署形态维持 `privileged: true` + `network_mode: host` + `pid: host` + `docker.sock:ro`（见 `docker-compose.nas.yml`）；守护模块**只发 GET**，不 exec、不写 socket、不改容器配置。
- 日志可能含敏感信息：入库前做一次脱敏（同 §5.4 规则），并在事件详情里提示"日志可能包含敏感内容"。
- AI 外发内容边界同 §5.4；AI 关闭时零外发。
- 失败隔离：单容器采集异常不影响整轮；AI 超时/失败不影响检测与通知链路。

## 10. 实施拆分与验收

| 阶段 | 内容 | 验收标准 |
| --- | --- | --- |
| P1 事件骨架与崩溃信号 | 事件表与状态机、events 订阅、inspect 轮询、信号 1–5、通知复用、监控中心事件列表 | 单测覆盖状态机/去重/冷却/恢复；真机上 `docker restart` 制造 3 次重启，产生 1 个事件、1 条通知、无误报；旧保护规则行为不变（回归测试全绿） |
| P2 磁盘、日志、网络信号 | 信号 6–12、日志采集与限流、基线统计、host 网络降级提示 | 单测覆盖滑动窗口、正则、限流、基线 z-score；真机用 `dd`/临时容器制造持续写入并触发一次事件；journald 宿主上日志信号明确显示不可用 |
| P3 AI 门控 | 总开关/模式/间隔/配额/预算/冷却/去重/缓存/用量面板/调用日志 | 单测：关闭时零调用、冷却期内零调用、达日上限零调用、超预算零调用、缓存命中不加计数；真机用 mock provider 验证"事件触发 1 次调用"与"定时巡检按间隔调用" |
| P4 打磨 | 批量研判、静默时段、保留清理、桌面端与手机端回归、文档 | 事件与调用日志按保留策略清理；桌面端嵌入页面与手机端布局回归通过；明暗主题无对比度问题 |

**已知限制与风险**

- host 网络容器没有独立网络统计（信号 11/12 不可用），只能看宿主机口径，需在 UI 明示。
- journald 日志驱动下日志信号不可用；短命容器可能只能靠 events 发现。
- 部分 cgroup v2 / rootless 场景 blkio 恒为 0，需识别并提示，避免误判"无异常"。
- 误报风险：确认窗口 + 冷却 + 每小时动作上限只能降低，不能消除；建议先跑一段"只记录/只通知"观察期。
- AI 结论是概率性的，默认不执行动作；开启自动执行需另立设计。
- 新增 2 张表与 3 个设置键，需要用户确认（见下）。

## 11. 待确认问题

1. ~~**默认阈值是否接受**~~（已确认按本文默认值：重启 3 次/10 分钟、非 0 退出 2 次/30 分钟、OOM 1 次/60 分钟、restarting ≥120 秒、磁盘写入 50 MB/s 持续 5 分钟、日志 20 行/10 分钟、网络突增 3σ 且 ≥10 MB/s 持续 5 分钟、恒零 30 分钟）。
2. ~~**AI 默认档位是否接受**~~（已确认：默认关闭；事件触发；**巡检间隔 10 分钟**；每小时 4 次 / 每天 24 次；容器冷却 60 分钟；每日 20 万 token；超预算停止自动分析。巡检周期只控制扫描频率，不放大 AI 调用量）。
3. **手动"立即分析"是否计入每日配额与预算**（当前设计：计入）。
4. **是否允许 AI 直接执行重启/停止**（当前建议：不允许，只给建议 + 人工一键执行）。
5. **是否接受新增 2 张表**（`container_guard_events`、`ai_guard_calls`）与 3 个设置键。
6. **巡检默认范围**：只覆盖规则选中的容器，还是一键给全部运行中容器套一组默认规则（默认只订阅 events、不轮询 stats）？
7. **host 网络容器的流量异常**：接受"仅宿主机口径 + 标注不可用"，还是要单独做进程/端口归因口径？
8. **自定义命令动作**：确认本期不做（需另立设计），还是必须纳入？
