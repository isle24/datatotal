# NAS Traffic Lens

极空间 NAS 自带界面如果没有实时流量和阶段流量统计，可以先考虑这些现成镜像：

| 方案 | 适合做什么 | 不足 |
| --- | --- | --- |
| [Netdata](https://learn.netdata.cloud/docs/netdata-agent/installation/docker) | 系统、网卡、容器、磁盘的实时监控很强，部署简单 | 进程级网络归因和“公网/内网阶段总量”不是核心能力 |
| [ntopng](https://www.ntop.org/guides/ntopng/installation.html) | 专业网络流量分析，按主机、协议、会话看流量 | 较重，进程名/PID 归因通常拿不到 |
| [vnStat + Web UI](https://github.com/vergoh/vnstat-docker) | 按网卡做日/月流量统计 | 没有进程、端口、实时连接归因 |

如果你要同时看公网、内网、每个网卡、进程、端口、使用时长和阶段时间内的公网总量，普通现成镜像通常不能完整覆盖，所以这里提供一个自研轻量服务。

## 功能

- 实时展示公网/内网的上下行速率。
- 展示每个网卡的公网、内网实时上下行和系统累计上下行。
- 展示公网累计上下行和“阶段公网”上下行；两者都来自抓包后的公网分类，阶段公网默认启动即统计，除非手动暂停或关闭。
- 展示进程级累计流量、PID、命令行和使用时长。
- 展示连接与端口维度的协议、源、目标、进程、上下行总量和时长。
- 阶段公网默认使用抓包分类后的公网流量，不读取系统网卡累计，因此不会混入内网、组播和 Docker bridge 的系统总流量。
- 支持访问密码、监控规则、SQLite 历史统计、日志目录映射。
- 支持监控中心和通知渠道模块，可按规则触发 Webhook、IYUU、MeoW 等渠道。
- 支持在页面可视化保存监控规则、通知渠道、消息模板和可热更新运行参数，配置写入 SQLite，重启后保留。
- 支持网卡/进程/连接筛选，连接表可按公网/内网、网卡、协议、方向、关键词、流量和时长过滤。
- 历史统计按今日、本周、本月、今年自然时间段聚合，用平滑曲线区分公网/内网、上行/下行。
- 系统页展示 CPU、内存、磁盘、温度和可用 GPU 信息；无法读取的硬件项会显示不可用。
- Intel 核显通常不会被 `nvidia-smi` 识别；容器能看到 `/dev/dri` 时会显示 DRI/核显可用，并尽量读取 i915 engine busy 指标，读取不到时会明确显示“已映射但未暴露利用率”。
- NPU 检测会读取 `/sys/class/accel`、`/dev/accel` 和 PCI 信息；Intel NPU 如果没有映射到容器内，会显示未检测到或仅 PCI 可见。
- 温度会把 `coretemp`、`acpitz`、`nvme`、`drivetemp` 等原始传感器名整理成 CPU、主板/机箱、NVMe、硬盘等友好名称。
- 前端使用 Vue/Vite 构建为静态文件，后端只提供 API 和静态托管。
- 默认只返回并展示物理/主接口数据，切换到“全部接口”时才加载 Docker/veth/bridge 等虚拟接口。
- 默认页接口已拆分：概览轻量刷新，进程排行和连接明细按需独立加载，降低 500 和高负载风险。
- 可读取 Docker 容器端口映射并显示容器名，也可给容器端口添加自定义备注、手动端口、图标和访问方式。
- Docker 页支持容器搜索、端口搜索、图标上传和按需 CPU/内存/网络占用查看。
- Docker 页列表接口只返回容器摘要，端口/图标按容器单独加载，CPU/内存/网络统计只在点击“显示占用”后请求单个容器，页面离开后不继续刷新，减少 Docker socket 压力。
- Docker 端口会自动识别 Redis、MySQL、PostgreSQL、MongoDB、SSH、Web 等常见服务；非 Web 端口默认只复制地址，不直接 HTTP 打开。

## 部署

在本目录执行：

```bash
docker compose up -d --build
```

然后访问：

```text
http://NAS-IP:8088
```

如果 8088 端口被占用，设置环境变量 `APP_PORT`，默认是 `8088`。

## amd64 打包

极空间 Z425 是 x64 架构，compose 已经固定：

```yaml
platform: linux/amd64
```

如果你在 Z425 本机上构建，直接执行部署命令即可。如果你在 Apple Silicon Mac 或其他非 amd64 机器上打包给 Z425 使用，建议同时打固定版本和 `latest` 两个 tag：

```bash
VERSION=$(cat VERSION)

docker buildx build --platform linux/amd64 \
  -t isle204/nas-traffic-lens:${VERSION} \
  -t isle204/nas-traffic-lens:latest \
  --load .
docker save isle204/nas-traffic-lens:${VERSION} isle204/nas-traffic-lens:latest -o nas-traffic-lens-amd64.tar
```

把 `nas-traffic-lens-amd64.tar` 导入极空间 Docker 后，镜像架构就是 `linux/amd64`。

日常 NAS 部署推荐使用 `latest`，文档和 compose 不需要每次跟着版本号修改。遇到缓存、回滚或需要确认版本时，再改用固定版本 tag。你手动推送时可以两个 tag 都推：

```bash
VERSION=$(cat VERSION)

docker push isle204/nas-traffic-lens:${VERSION}
docker push isle204/nas-traffic-lens:latest
```

页面和 API 显示的版本号来自镜像内 `/app/VERSION`，源码对应根目录 `VERSION` 文件。发新版时先更新 `VERSION`，再按同一个版本号打 Docker tag。

推送到 Docker Hub 后，NAS 端可以直接使用项目里的 `docker-compose.nas.yml`：

```bash
docker compose -f docker-compose.nas.yml up -d
```

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8088` | Web 服务端口 |
| `DASHBOARD_PASSWORD` | 空 | 设置后启用登录密码 |
| `DB_PATH` | `/data/traffic.db` | SQLite 历史数据路径 |
| `LOG_DIR` | `/logs` | uvicorn 访问日志和错误日志目录 |
| `UVICORN_ACCESS_LOG` | `false` | 是否记录每次 HTTP 访问日志，默认关闭以减少写盘 |
| `FILE_LOG` | `true` | 是否写入日志文件；设为 `false` 时直接输出到容器控制台 |
| `CONSOLE_LOG` | `true` | 是否把文件日志同步输出到容器控制台 |
| `ENABLE_PACKET_CAPTURE` | `true` | 是否启用抓包归因；关闭后公网阶段和进程流量会不可用或变少 |
| `CAPTURE_INTERFACES` | 自动 | 指定抓包网卡，逗号分隔；设置为 `all` 才抓所有启用接口 |
| `CAPTURE_MAX_EVENTS_PER_SECOND` | `2000` | 抓包每秒精确记录阈值，超过后动态抽样并按倍率折算 |
| `CAPTURE_SAMPLE_RATE` | `1` | 固定抓包采样率，`1` 表示不固定抽样 |
| `CAPTURE_DYNAMIC_SAMPLE` | `true` | 高包量时是否自动抽样并按倍率折算流量 |
| `CAPTURE_MAX_SAMPLE_RATE` | `50` | 动态抽样最大倍率 |
| `ENABLE_SYSTEM_TRAFFIC_CALIBRATION` | `true` | 抓包统计明显低于系统网卡计数时，用系统计数补齐总量 |
| `SYSTEM_TRAFFIC_CALIBRATION_THRESHOLD` | `1.25` | 系统网卡增量超过抓包增量多少倍时触发校准 |
| `SYSTEM_TRAFFIC_CALIBRATION_MIN_BYTES` | `262144` | 单次校准最小系统增量，避免小流量抖动 |
| `SYSTEM_TRAFFIC_CALIBRATION_MAX_FACTOR` | `20` | 单次校准最大补齐倍率 |
| `SYSTEM_TRAFFIC_CALIBRATION_ASSUME_WAN` | `false` | 抓包没有公网/内网比例时是否默认补到公网 |
| `MAX_RATE_HISTORY_POINTS` | `180` | 内存实时速率诊断点数，历史图表使用 SQLite |
| `HISTORY_RETENTION_DAYS` | `400` | SQLite 历史数据保留天数 |
| `ENABLE_DOCKER_DISCOVERY` | `false` | 是否读取 Docker socket 自动识别容器名 |
| `DOCKER_LIST_CACHE_SECONDS` | `20` | Docker 容器列表缓存秒数，避免频繁扫 socket |
| `DOCKER_STATS_CACHE_SECONDS` | `5` | 单容器 stats 缓存秒数，只对已点开“显示占用”的容器生效 |
| `DOCKER_WEB_PROBE_TTL_SECONDS` | `86400` | 端口是否 Web 的探测缓存秒数 |
| `DOCKER_WEB_PROBE_TIMEOUT` | `1` | 单次 Web 端口探测超时秒数 |
| `DOCKER_API_MAX_BYTES` | `2097152` | 单次 Docker socket 响应最大读取字节 |
| `PROCESS_RECENT_SECONDS` | `180` | 30 秒进程排行的内存缓存窗口 |
| `MAX_CONNECTION_TRACKED` | `10000` | 抓包连接缓存硬上限，超过后淘汰最久未活跃连接 |
| `MAX_PROCESS_TRACKED` | `2048` | 进程累计缓存硬上限 |
| `MAX_PORT_TRACKED` | `4096` | 端口累计缓存硬上限 |
| `MAX_DOCKER_CACHE_ENTRIES` | `512` | Docker stats 和 Web 探测缓存条目上限 |
| `MAX_DOCKER_ICON_DATA_CHARS` | `2097152` | 单个 Docker 图标 data URL 最大字符数 |
| `LOGIN_MAX_ATTEMPTS` | `10` | 单个客户端登录失败次数上限 |
| `LOGIN_LOCK_SECONDS` | `300` | 登录失败达到上限后的限制时间 |
| `ALERT_WAN_TX_BPS` | `0` | 默认监控规则：公网上传速率阈值，单位 B/s |
| `ALERT_WAN_TX_SECONDS` | `0` | 默认监控规则：高上传持续秒数 |
| `ALERT_STAGE_TX_BYTES` | `0` | 默认监控规则：阶段公网上传上限，单位 B |
| `ALERT_DAILY_TX_BYTES` | `0` | 默认监控规则：每日公网上传上限，单位 B |
| `ALERT_NOTIFY_CHANNEL` | `webhook` | 默认通知渠道类型，支持 `webhook`、`iyuu`、`meow` |
| `ALERT_WEBHOOK_URL` | 空 | 默认 Webhook 地址，设置后启用默认通知渠道 |
| `ALERT_WEBHOOK_TIMEOUT` | `5` | 默认通知渠道超时，单位秒 |
| `CONNECTION_ACTIVE_SECONDS` | `120` | 连接数统计窗口，越小越接近路由器“当前会话数” |
| `CONNECTION_RETENTION_SECONDS` | `900` | 连接明细缓存保留时长 |
| `AUTO_START_STAGE` | `true` | 启动后自动开始阶段公网统计，设为 `false` 后需手动开始 |
| `CONNECTION_COUNT_SOURCE` | `conntrack` | 首页连接数来源，支持 `conntrack`、`socket`、`capture` |
| `CONNTRACK_REFRESH_SECONDS` | `30` | conntrack 连接数刷新间隔，单位秒 |
| `CONNTRACK_COUNT_MODE` | `active` | conntrack 计数模式，`active` 只算活跃会话，`raw` 算原始表条目 |
| `CONNTRACK_TCP_STATES` | `ESTABLISHED` | active 模式下计入的 TCP 状态，逗号分隔 |
| `CONNTRACK_UDP_REQUIRE_ASSURED` | `true` | UDP 默认只统计双向确认会话，减少组播/残留条目 |
| `CONNTRACK_INCLUDE_UNREPLIED` | `false` | 是否把未回应连接纳入 active 统计 |
| `CONNTRACK_MIN_TIMEOUT_SECONDS` | `3` | active 模式下最小剩余超时时间 |
| `CONNTRACK_MAX_LINES` | `30000` | 首页连接数每次最多扫描 conntrack 行数 |
| `CONNTRACK_SCAN_SECONDS` | `1` | 首页连接数每次最多扫描秒数 |
| `CONNTRACK_CONNECTION_MAX_LINES` | `30000` | 连接弹窗明细每次最多扫描 conntrack 行数 |
| `CONNTRACK_CONNECTION_SCAN_SECONDS` | `1.5` | 连接弹窗明细每次最多扫描秒数 |
| `SOCKET_REFRESH_SECONDS` | `60` | socket/进程归属刷新间隔 |
| `PROC_SCAN_TIMEOUT_SECONDS` | `1` | 扫描 `/proc` socket 到进程归属的单次时间预算 |
| `MAX_PROC_FD_LINKS` | `60000` | 单次最多读取的进程 fd 链接数 |
| `MAX_PROC_NET_LINES` | `60000` | 单个 `/proc/net/*` 文件最多读取行数 |

监控规则、通知渠道和部分运行参数都可以在页面“监控中心”里修改。页面保存后的值会写入 SQLite，并优先于环境变量。端口、日志目录、Docker 发现、抓包接口这类启动期配置会在页面只读展示，修改仍建议通过 compose 环境变量并重启容器。

## 通知渠道和模板

通知渠道支持：

- `webhook`：向自定义 URL `POST application/json`，包含 `title`、`text`、`url`、`alert` 和渠道信息。
- `iyuu`：按 IYUU 文档请求 `https://iyuu.cn/{token}.send`，发送 `text` 和 `desp`。
- `meow`：按 MeoW 文档请求 `https://api.chuckfang.com/{昵称}`，POST JSON：`title`、`msg`、`url`，并通过 query 传 `msgType`、`htmlHeight`。

标题、正文和跳转 URL 都支持模板变量：

```text
{app} {version} {channel_id} {channel_name} {channel_type}
{alert_id} {rule_id} {rule_name} {message} {severity}
{value} {threshold} {timestamp} {iso_time}
```

例如：

```text
标题：{app} {rule_name}
正文：告警：{message}
当前值：{value}
阈值：{threshold}
时间：{timestamp}
```

## 阶段公网统计

首页“公网累计”和“阶段公网”都统计抓包分类后的公网下行/上行，不是系统网卡累计值。系统累计会包含内网复制、Docker bridge、组播/广播等流量，不能代表真实公网消耗；阶段公网默认从容器启动后开始累计，更适合判断偷跑上传。

- `重置`：清空阶段公网累计，并立即重新开始统计。
- `暂停`：停止继续累计，已有阶段数据保留。
- `继续`：从已有阶段数据继续累计。
- 如果你确实不想默认统计，设置 `AUTO_START_STAGE=false`。

## 数据和日志映射

compose 默认映射：

```yaml
volumes:
  - ./data:/data
  - ./logs:/logs
```

- SQLite 数据在 `./data/traffic.db`。
- 日志在 `./logs/uvicorn.log` 和 `./logs/uvicorn-error.log`。
- 默认也会把这两个日志同步到容器控制台，方便在极空间 Docker 页面直接排查重启和 500 错误。若只想写文件，可设置 `CONSOLE_LOG=false`。
- 清历史统计可以停容器后删除 `./data/traffic.db`。
- 清运行日志可以直接删除 `./logs/*.log`，重启容器后会重新生成。

## Docker 权限说明

这个服务需要看到宿主机网络和宿主机进程 socket，因此 compose 使用：

- `network_mode: host`：让容器抓宿主机网卡流量。
- `pid: host`：让容器读取宿主机进程 `/proc`，用于把端口关联到进程。
- `privileged: true`：允许原始 socket 抓包。

如果你的 NAS Docker 管理器不允许 `privileged`、host 网络或 host PID，服务仍可能启动，但只能看到容器自己的网络，进程归因也会明显不完整。

## 网卡选择

默认只抓推荐的物理/主网卡，虚拟网卡仍显示系统计数，但不默认抓包。这样能避免 `veth*`、`br-*`、`docker0`、`ifb0` 等虚拟接口重复统计同一份流量，也能降低 CPU 占用。

页面默认只请求物理/主接口视图。需要排查 Docker 网桥、veth、IFB 或其他虚拟接口时，在“网卡实时情况”里把接口类型切到“全部接口”，此时 `/api/snapshot` 才会返回全量接口数据。

如果只想抓某些网卡，在 `docker-compose.yml` 中设置：

```yaml
environment:
  CAPTURE_INTERFACES: "eth0,br0"
```

如果确实要抓所有启用网卡：

```yaml
environment:
  CAPTURE_INTERFACES: "all"
```

极空间设备实际网卡名可能是 `eth0`、`br0`、`bond0`、`docker0` 等，可以进 NAS 终端执行：

```bash
ip link
```

## Docker 容器识别和备注

连接表会优先显示 Docker 容器名、镜像名和端口映射。为了让容器内能读取 Docker 容器列表，需要可选映射 Docker socket：

```yaml
environment:
  ENABLE_DOCKER_DISCOVERY: "true"
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
```

Docker socket 权限很高，所以默认关闭自动发现。只有你确认需要容器名自动识别时，再开启 `ENABLE_DOCKER_DISCOVERY` 并映射 socket。

如果极空间 UI 不允许映射 Docker socket，服务仍然可用，只是容器名自动识别会缺失。新版会把 Docker 发现失败降级为空，不应该导致容器重启。可以通过 `/api/health` 或 `/api/snapshot` 里的 `containerStatus` 查看是否启用、socket 路径和识别到的端口数量。

Docker 页现在支持：

- 搜索容器名、镜像名、端口、服务类型和备注。
- 容器列表优先轻量返回；端口、图标会按容器详情接口补齐，避免 `/api/docker/containers` 一次性返回所有重数据。
- 查看容器基础占用：CPU、内存、Docker API 统计的网络收发总量。这个统计只在点击某个容器的“显示占用”后读取，并只在 Docker 页面打开时刷新。
- 给容器上传 PNG/JPG/WebP 图标，图标会以 data URL 形式保存在 SQLite；为了安全不接受 SVG。
- 给每个端口设置备注、服务类型、访问方式、Web 协议和路径。
- host 网络模式容器一般不会在 Docker API 里出现发布端口，可以在 Docker 页手动添加端口。
- Redis、MySQL、PostgreSQL、MongoDB、SSH、MQTT 等非 Web 端口默认显示“复制地址”；TCP 端口可手动点“探测”做一次 HTTP/HTTPS 请求，探测结果会缓存，识别为 Web 后才显示“打开”按钮。

Docker 相关接口拆分为：

- `GET /api/docker/containers`：轻量容器列表，不读取 stats。
- `GET /api/docker/containers/{id}`：单容器端口、图标和详情。
- `GET /api/docker/containers/{id}/stats`：单容器 CPU/内存/网络统计，按需调用。
- `POST /api/docker/ports/probe`：单端口 Web 探测，带缓存。

## GPU / NPU 和温度

Intel Ultra 5 125H 的核显通常通过 `/dev/dri` 暴露。要让容器看到核显设备，可以在 compose 中增加：

```yaml
devices:
  - /dev/dri:/dev/dri
```

如果宿主内核同时暴露 `/sys/class/drm/card*/engine/*/busy`，系统页会显示 Intel 核显利用率；如果只映射了 `/dev/dri` 但没有 busy 指标，会显示设备可用但利用率未暴露。

NPU/AI Boost 取决于宿主机驱动和设备节点。若宿主存在 `/dev/accel`，可尝试增加：

```yaml
devices:
  - /dev/accel:/dev/accel
```

部分系统即使能在 PCI 中看到 NPU，也不会向容器暴露利用率统计，这时页面会显示“PCI 可见但设备节点未映射”或“已识别但利用率取决于宿主驱动”。

温度显示优先使用宿主暴露给容器的 `psutil.sensors_temperatures()`。页面会把常见原始名转换为更容易看的名称：

- `coretemp` / `k10temp`：CPU。
- `acpitz` / `thermal_zone`：主板/机箱。
- `nvme`：NVMe 盘。
- `drivetemp` / `hddtemp`：硬盘。

页面里仍可给已识别的容器端口添加备注，备注保存在 SQLite 的 `labels` 表中。

## 性能优化

- 默认不抓虚拟接口，减少重复包和 CPU 占用。
- 进程 socket 映射改为后台定时刷新，不再在每个包路径里扫描 `/proc`。
- SQLite 只保存分钟级聚合，不保存原始包。
- 连接/端口缓存会定期清理长时间不活跃项。
- 进程、连接、端口排行只在页面请求快照时排序，不在每秒采样循环里排序。
- 默认关闭 uvicorn 访问日志，避免 2 秒轮询持续写盘。
- conntrack 和 `/proc` 扫描都有行数上限和时间预算，超过后返回截断状态，优先保护 Docker 引擎和宿主稳定。
- 抓包有每秒精确记录阈值，超过后动态抽样并按倍率折算，避免迅雷、BT 等高包量下载被硬丢包漏统。
- 抓包统计明显低于系统网卡计数时，会按已识别到的公网/内网比例补齐总量；补齐状态可在 `/api/diagnostics` 的 `calibration` 中查看。

高速下载仍偏低时，优先看 `/api/diagnostics`：

- `capture.sampledEvents` / `capture.weightedBytes`：是否触发抽样折算。
- `calibration.interfaces`：是否触发系统网卡计数补齐。

如果 NAS CPU 余量足，可以把 `CAPTURE_MAX_EVENTS_PER_SECOND` 提到 `5000`，或把 `CAPTURE_MAX_SAMPLE_RATE` 提到 `100`。

如果宿主或 Docker 引擎负载异常，可以先用保守模式定位压力来源：

```yaml
ENABLE_DOCKER_DISCOVERY: "false"
CONNECTION_COUNT_SOURCE: "socket"
ENABLE_PACKET_CAPTURE: "false"
FILE_LOG: "false"
```

这个模式会牺牲公网阶段统计、进程流量归因和 Docker 自动发现，但能快速判断问题是否来自 conntrack、抓包或 Docker socket。

## 连接数口径

首页的“公网/总连接数”默认读取宿主机 `conntrack` 的活跃会话：

- 能读到 `/proc/net/nf_conntrack` 或 `/proc/net/ip_conntrack` 时，默认只统计 TCP `ESTABLISHED` 和已确认 UDP，会更接近路由器“当前连接数”。
- 页面会同时显示原始 conntrack 条目数，方便判断内核表里是否有大量 `TIME_WAIT`、`UNREPLIED`、UDP 残留或 P2P 条目。
- 读不到 conntrack 时，优先回退到宿主机 socket，再回退到抓包活跃连接。
- 如果你想看内核原始表总量，把 `CONNTRACK_COUNT_MODE` 改成 `raw`。

点击首页“公网/总连接数”默认打开 `conntrack` 活跃会话列表；点击网卡速率或进程卡片时，默认打开抓包归因明细，以便看到进程、PID、容器和备注。

## 公网/内网判断

服务按 IP 地址分类：

- 双方都是局域网、本机、链路本地、组播、广播或保留地址时，记为内网。
- 只要有一端不是私有地址，记为公网。

私有地址包括：

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`
- `127.0.0.0/8`
- `169.254.0.0/16`
- `224.0.0.0/4`、`239.255.255.250` 等组播/SSDP 发现流量
- `255.255.255.255/32`
- `fc00::/7`
- `fe80::/10`
- `ff00::/8`

例如 `192.168.3.11:1900 -> 239.255.255.250:1900` 是 SSDP 组播发现流量，新版本会归为内网，不会计入公网。已写入 SQLite 的旧历史聚合无法反推源/目标 IP，因此旧误分类数据不会自动重算；需要完全干净的历史时，停容器后删除 `./data/traffic.db` 重新统计。

## 局限

- 进程归因依赖 `/proc/net/tcp*`、`/proc/net/udp*` 和 `/proc/<pid>/fd` 的 socket inode。短连接结束太快时，可能只显示为 `unknown`。
- 加密流量不影响计量，但不会解析应用层域名。
- 如果流量经过 Docker bridge、虚拟网卡或硬件卸载，系统网卡累计值和抓包累计值可能不完全一致。
- UDP 无连接场景的进程归因比 TCP 更容易缺失。
- 极空间系统如果限制容器权限，需要改用宿主机直接运行或安装 eBPF/pcap 权限更高的版本。

## 采集后端架构（三层降级）

从 v2026.06.25 起，采集引擎支持三层自动降级：

```
启动 → eBPF (内核态) → 不可用 → Go + libpcap → 不可用 → Python Scapy (原方案)
```

### 第一层：eBPF TC 采集（负载最低）

- 通过 TC (Traffic Control) hook 在内核层直接捕获包事件
- 零用户态拷贝：包数据通过 BPF ring buffer 从内核推到用户态
- 每包不经过 Python 解释器，CPU 开销极低
- **要求**：Linux >= 5.4、`CONFIG_DEBUG_INFO_BTF=y`、BTF vmlinux 存在
- **源码**：[`ebpf/traffic_kern.c`](../server/go-collector/ebpf/traffic_kern.c)（BPF C 程序）+ [`ebpf/collector.go`](../server/go-collector/ebpf/collector.go)（Go 用户态加载器）
- 容器需要 `privileged: true` 和 host 网络
- 检测方式：启动时检查 `/sys/kernel/btf/vmlinux` 是否存在

### 第二层：Go + libpcap 采集（负载较低）

- Go 编译为原生二进制，无 GC 停顿，goroutine channel 替代 Python RLock
- gopacket (libpcap CGO 绑定) 抓包，直接读取 `/proc/net/dev` 做系统计数器
- 与 Python 方案逻辑对等（动态抽样、进程归因、conntrack），但消除了 Python GIL 和解释器开销
- **要求**：Linux，libpcap 可用
- **源码**：[`go-collector/`](../server/go-collector/)（Go module，独立编译为二进制）
- 启动为独立 HTTP 服务（默认端口 18088），Python 后端通过 HTTP 调用其 API

### 第三层：Python Scapy（自动回退）

- 原方案完整保留，Go/eBPF 不可用时自动激活
- 所有流量统计、连接归因逻辑不变

### 容器内自动选择

入口脚本 [`entrypoint.sh`](../server/entrypoint.sh) 按优先级探测：

```bash
# 强制指定模式
COLLECTOR_MODE=ebpf       # 仅 eBPF
COLLECTOR_MODE=golibpcap  # 仅 Go
COLLECTOR_MODE=auto       # 自动（默认）

# Go collector HTTP 端口
GO_COLLECTOR_PORT=18088

# 二进制路径（Docker 镜像内默认）
GO_COLLECTOR_BIN=/app/bin/go-collector
GO_COLLECTOR_EBPF_BIN=/app/bin/go-collector-ebpf
```

Python 后端探测方式：`GO_COLLECTOR_URL` 环境变量或 `server/services/go_collector_client.py` 中的默认 URL。

### Python 集成点

现有 `TrafficCollector` 在以下 API 自动使用外部 collector 数据：

| API endpoint | Go 数据源 | 回退行为 |
|---|---|---|
| `/api/overview` | `/api/snapshot`（Go） | 使用 Python 本地数据 |
| `/api/snapshot` | `/api/snapshot`（Go） | 使用 Python 本地数据 |
| `/api/processes` (30s) | `/api/processes`（Go 内存） | Python `process_recent` |
| `/api/connections` (capture) | `/api/connections`（Go） | Python `conn_totals` |
| `/api/diagnostics` | `/api/diagnostics`（Go） | Python 自诊断 |

Go 不可用时所有 API 透明回退到 Python 原逻辑，前端无需任何修改。

## 性能对比（预估）

| 指标 | Python Scapy | Go + libpcap | eBPF TC |
|---|---|---|---|
| CPU（空载 1000 pps） | ~3-5% | ~0.5-1% | ~0.1-0.3% |
| CPU（高峰 5000 pps） | ~15-25% | ~3-5% | ~0.5-1% |
| 内存（稳定态） | ~80-120 MB | ~20-40 MB | ~15-30 MB |
| 每包延迟 | ~50-100μs | ~5-10μs | ~1-2μs |
| 丢包率（peak 10K pps） | 有动态抽样 | 有动态抽样 | 接近零 |

实际表现取决于 NAS CPU 型号、内核版本和网络负载。

## 开发结构

```text
doc/                    文档
front-end/              前端静态页面
server/                 FastAPI 后端和采集器
  go-collector/         Go 采集引擎（独立二进制）
    collector/          共享类型、聚合器、抓包、系统信息
    ebpf/               eBPF BPF C 程序 + Go 加载器
  services/             服务模块（通知、系统状态、Go collector 客户端）
```

## API

- `GET /api/overview`：轻量概览快照，包含卡片汇总、连接计数、告警和运行状态。
- `GET /api/snapshot`：当前快照，包含网卡、阶段和告警，不返回连接明细。
- `GET /api/snapshot?interfaces=physical|captured|virtual|all`：按接口视图返回当前快照，默认 `physical`。
- `GET /api/processes?period=30s|today|1d|3d|7d|30d|custom&limit=30`：进程上下行排行；自定义时间可带 `start` 和 `end` Unix 秒。
- `GET /api/connections?interfaces=physical&scope=wan&direction=tx`：按需连接明细，支持网卡、范围、协议、方向、进程、源/目标、最小流量、最小时长、分页。
- `GET /api/history?period=day|week|month|year`：历史聚合统计。
- `GET /api/settings`：当前配置。
- `POST /api/settings/monitor`：保存监控规则。
- `POST /api/settings/channels`：保存通知渠道。
- `POST /api/settings/alerts`：兼容旧接口，保存默认监控规则。
- `POST /api/settings/notify`：兼容旧接口，保存默认通知渠道。
- `POST /api/labels`：保存容器端口备注。
- `GET /api/logs`：查看日志目录和日志文件大小。
