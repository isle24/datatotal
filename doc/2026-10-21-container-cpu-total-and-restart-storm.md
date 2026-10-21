# 容器保护 CPU 阈值改整机口径 & flaresolverr 重启风暴复盘（2026-10-21）

## 结论（TL;DR）

- 容器 `flaresolverr` 的"一直重启"不是它自己崩溃，而是本应用的**容器保护规则**在自动重启它。
- 直接原因：容器保护的 CPU 阈值沿用了 Docker 的**单核口径**（`100%` = 一个 CPU 核心），而用户设置的阈值 `5` 是**整机口径**的 5%。极空间 Z425 有 18 个逻辑核心，单核口径的 `68.44%` 其实只有整机 `3.8%`，却被拿来和 `5` 比较，于是反复触发 `restart`。
- 为什么最近更频繁：10 月中旬起 flaresolverr 出现每 3 小时一次的高 CPU 时段（10-20 起稳定为 00/03/06/09/12/15/18/21 点成串出现），每次持续几分钟；规则冷却只有 60 秒，同一时段会连续重启 2~3 次，单日重启从约 1 次涨到 14~18 次。应用升级本身没有改变 CPU 计算公式（各发布版本一致）。
- 修复：`cpuPercent` 改为**整机口径**（全部核心合计，`100%` = 整机跑满）；旧的单核口径值保留为 `cpuPercentSingleCore`，并新增 `cpuCount`。容器保护阈值、告警值、页面展示、运维助手统一按整机口径。
- 现场处置：先临时停用规则止血（保留配置）；按用户要求已恢复启用（`enabled=true`，阈值 5 / 通知渠道 / 历史计数不变）。修复版 `2026.10.21-1` 已构建并部署到极空间 Z425，规则现按"整机 5%"判断。

## 现场与证据（极空间 Z425，192.168.3.56:8088，版本 2026.10.07-13）

| 项目 | 观察值 |
| --- | --- |
| 规则 | `protection-1782714000910`「新容器保护」，目标仅 `flaresolverr`，`action=restart`，`logic=and`，`cooldownSeconds=60` |
| 条件 | `cpuPercent gte 5`，持续 `30` 秒 |
| 保护状态 | `count=64`，最后动作为 `restart`，原因 `restart completed: cpuPercent=18.57 threshold=5 duration=30s`（2026-10-21 15:09:47） |
| 容器状态 | `flaresolverr` 当时 `Up 2 minutes`；其余 35 个容器大多 `Up 7–8 天`（少数为近期新建或重启），没有任何其他容器被保护规则选中 |
| 宿主机 | 18 个逻辑 CPU（`/api/system`）；主机 uptime 约 27.8 天，期间无整机重启 |
| 告警历史 | `container_protection` 告警 94 条 / 72 个连续告警时段（gap ≤ 15 分钟），2026-07-12 起；按月 Jul 2、Aug 17、Sep 14、Oct 61 |
| 10 月每日 | 10-07~11 每天 1 条；10-12 起 2~3 条；10-16 6 条；10-20 14 条；10-21 18 条 |
| 触发值 | 最小 5、中位 21、最大 113；换算整机口径后中位仅 1.4%、均值 2.1%、最大 6.3% |
| 误触发比例 | **76/94（80.9%）的触发值换算后低于整机 5%**；只有 18 条真正超过整机 5% |
| 最后一次触发 | `18.57`（单核口径）≈ 整机 `1.03%`，仍被重启 |

对比第二台绿联 DXP4300 Plus（192.168.3.57，版本相同）：`containerProtection.rules=[]`、无保护告警，`nas-traffic-lens` / `v2raya` / `firefox-app` 均连续运行 13 天~3 周，无此问题。

## 根因

### 1. CPU 百分比单位错配（代码缺陷）

```python
# 旧实现（Docker 单核口径）：
cpu_percent = (cpu_delta / system_delta) * cpu_count * 100
# 18 核机器上，容器吃满 1 个核 = 100，吃满 18 个核 = 1800
```

容器保护规则直接把该值和用户阈值比较。用户阈值 `5` 的语义是"整机 CPU 的 5%"，但在旧实现里 `5` 只相当于**单核的 5%**（18 核整机约 `0.28%`），几乎任何一次 FlareSolverr 解验证的 CPU 波动都会超过它。

以本次现场为例：`3422 / 90000 × 18 × 100 = 68.44`（单核口径）；`3422 / 90000 × 100 = 3.80`（整机口径）。整机 3.8% < 阈值 5，本不应触发。

### 2. 动作是"重启"且冷却只有 60 秒

规则动作是 `restart` 而不是"仅告警"，`cooldownSeconds=60`。一次高 CPU 时段持续数分钟时，容器重启后的启动/解题 CPU 又会持续超过 30 秒条件，60 秒冷却一过就再次重启，单个时段连续 2~3 次。`maxActions` 字段虽然保存，但评估路径并未使用，重启次数不限。

### 3. 最近高 CPU 时段变密

告警时间分布显示：7~9 月只有每天 18:00 前后 1 次；10 月中旬开始出现每 3 小时一次的高 CPU 时段，10-20 起稳定为 00/03/06/09/12/15/18/21 点。说明有某个定时任务（PT/站点/搜索类容器）开始周期性调用 FlareSolverr 解 Cloudflare 验证。每次调用本身是正常业务，被误判成"异常占用"后触发重启，才形成重启风暴。

## 修复内容

### 后端 `server/main.py`

- `docker_container_stats()`：
  - `cpuPercent` = `cpu_delta / system_delta × 100`（**整机口径**，全部核心合计，范围 0~100）；
  - 新增 `cpuPercentSingleCore` = 旧 Docker 口径（`100` = 一个核心，可超过 100）；
  - 新增 `cpuCount`（逻辑核心数）。
- `DOCKER_STATS_FIELDS` 加入上述兼容字段，避免混入容器摘要/详情。
- `normalize_container_stats()` 透传两个兼容字段；内存、磁盘、网络口径不变。
- `container_protection_metric_value()` 的 `cpuPercent` 现在返回整机百分比，容器保护阈值/告警/证据随之统一。
- `server/services/ops_agent.py`：容器 CPU 输出标注"（整机）"，单容器查询额外提供"CPU单核"参照。

### 前端

- 指标标签改为「CPU 占用（整机）」；保护条件编辑器增加单位说明（100% = 全部核心之和，阈值 5 = 整机 5%，不是单核 5%）。
- Docker 卡片占用行显示 `整机 3.8%（单核 68.4%）`（`formatDockerCpu`）；无单核字段时只显示整机值。
- 其它文案、数据结构不变。

### 兼容与升级注意

- `GET /api/docker/containers/{id}/stats` 中 `cpuPercent` 的语义从"单核口径"变为"整机口径"；需要旧值的客户端改读 `cpuPercentSingleCore`。
- 已保存的容器保护规则中的 CPU 阈值也按整机口径重新解释。旧规则若按单核口径设置，请按 `旧阈值 ÷ 逻辑核心数` 换算后重新保存；例如 18 核机器上的旧阈值 `90` 约等于整机 `5%`。
- 内存百分比（分母为容器内存限制/主机内存）和磁盘 I/O 口径不变。

## 现场处置与恢复

- 15:10 左右最初将 `protection-1782714000910` 临时 `enabled=false` 止血：规则、目标、阈值 5、通知渠道全部保留，仅停止自动动作；停用期间 `flaresolverr` 不再被重启，也没有新增保护告警。
- 15:20 按用户要求把规则恢复 `enabled=true`（未改阈值/渠道/计数）。旧版本在恢复后仍按单核口径判断，15:20~15:23 又发生 3 次重启，`count` 64 → 67；随后完成修复版部署。
- 如果只想"预警"不想自动重启：当前版本的容器保护动作只有"重启/停止"，没有"仅告警"。若确需限制 runaway 容器，建议把阈值调到更合理的整机值（例如 50% 或按核心数换算），避免把正常解题 CPU 波动当成异常。

## 发布与部署

| 项目 | 结果 |
| --- | --- |
| 源码提交 | `fix(protection): 容器保护 CPU 阈值改整机口径` + 本版本发布提交（见 GitHub `main`） |
| 镜像 | `isle204/nas-traffic-lens:2026.10.21-1`（amd64 + arm64 多架构，索引 `sha256:b1d34caed453f9cf25a298c75b61771f9ba2bd2d9981017375ebeac8d5e389d2`）；`latest` 已同步到同一索引；amd64 manifest `sha256:8ca795d7…`，arm64 manifest `sha256:131ab9d8…` |
| 构建 | Dockerfile 全量构建（Go 采集器 / 前端 / Python 运行时），amd64 与 arm64 分别构建后合并多架构索引 |
| 部署方式 | `docker save \| gzip \| ssh zspace 'gunzip \| docker load'` 导入镜像；修改 compose `image:` 后 `docker compose up -d` 重建容器（不改网络/卷/权限配置） |
| 部署前备份 | `/data_n008/data/udata/real/18181998187/docker/nas-traffic-lens/upgrade-backups/20261021-153900/`：`docker-compose.yml`、`traffic.db`（2.36 GB）、`settings.json`、`alerts-baseline.json` |
| 停机窗口 | 停旧容器 → 备份 → 切换镜像 → 启动新容器，约 20 秒 |

部署后实机验证：

- 容器 `running`、`restarts=0`、镜像 `isle204/nas-traffic-lens:2026.10.21-1`；`/api/health` 返回 `version=2026.10.21-1`，日志无报错。
- 规则与历史完整保留：`protection-1782714000910` 仍 `enabled=true`、`action=restart`、阈值 5/30 秒；保护计数仍为 67；告警历史 110 条、`settings` 8 条与部署前一致。
- 新口径生效：单容器 stats 返回 `cpuPercent=0.0`（整机）、`cpuPercentSingleCore=0.01`（单核）、`cpuCount=18`；保护状态 `metricDetails` 使用整机值（`value=0.0, threshold=5`），超过整机 5%（约 0.9 个核）持续 30 秒才会动作。
- 部署后 `flaresolverr` 连续运行、无新增重启请求；后续高 CPU 时段是否重启，取决于整机占用是否真的超过 5%。

## 验证

- 新增 `server/tests/test_cpu_total_semantics.py`（10 项）：
  - 公式：4 核 `100/400` → 整机 25.0 / 单核 100.0 / `cpuCount=4`；
  - 现场形状：18 核 `3422/90000` → 单核 68.44 / 整机 3.80；
  - 保护集成（走真实 `docker_container_stats` 管线）：整机 3.8% + 阈值 5 → **不重启**；整机 6.0% + 阈值 5 → 重启并写告警；跨采样缓存 TTL 仍不误触发。
- 更新 `test_container_targets.py::test_cgroup_v2_cpu_uses_nested_online_cpus` 断言新口径。
- 回归：`.venv/bin/python -m pytest server/tests -q` → `205 passed, 1 failed`，唯一失败为改动前已存在的 `test_ops_agent.py::AgentApiTests::test_audit_rows_are_persisted_and_listed`（与本次改动无关）；前端 `node --test tests/*.test.mjs` → 78 passed；`npm run build` 成功。
- 独立复核：把新增回归测试放到改动前的 HEAD 代码上运行会失败（10 项中 9 项失败，包括"68.44 被当成与 5 比较并重启"和"整机 3.8% 不应动作"两项），说明该测试能真实拦住旧缺陷。
- 历史告警不迁移：升级前的 `container_protection` 告警仍保存单核口径数值，升级后的新告警保存整机口径数值；排查历史记录时需按时间区分口径。

## 后续建议

1. 观察下一次高 CPU 时段（每 3 小时一次）：修复版下只有整机占用真正 ≥5%（约 0.9 个核）并持续 30 秒才会重启，大部分正常解题波动不应再触发。
2. 排查 10 月中旬起每 3 小时调用 FlareSolverr 的定时任务（PT/搜索类容器），确认调用量增长是否符合预期。
3. 若产品上需要"只预警不动作"，可考虑给容器保护新增 `notify` 动作（只写告警、不执行 Docker 动作），本次未实现。
4. 顺带发现：容器列表的 `uptimeSeconds` 实际是 `now - Created`（重建前不会变化），排障时应以 Docker 的 `status` 字符串为准；该字段当前未在页面展示，本次未改动。
