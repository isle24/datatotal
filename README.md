# NAS Traffic Lens / datatotal

NAS Traffic Lens 是一个面向极空间、家庭 NAS 和 x86/ARM Linux 主机的轻量网络监控面板。它用于补齐 NAS 自带系统缺少的实时公网流量、累计公网流量、进程和端口归因、Docker 容器识别、告警通知等能力。

当前项目已经拆分为前后端：

- `front-end/`：Vue 3 + Vite 前端。
- `server/`：FastAPI 后端、采集器、SQLite 存储、通知模块。
- `doc/`：更细的功能设计和运行说明。
- `docker-compose.yml`：本地构建测试用。
- `docker-compose.nas.yml`：NAS 部署推荐模板。

## 主要功能

- 实时公网/内网上下行速率。
- 物理网卡优先展示，可切换查看全部网卡、bridge、veth、docker0 等接口。
- 公网累计流量统计，避免系统网卡累计混入内网复制、Docker bridge、组播广播。
- 公网连接数统计，尽量按路由器的“活跃会话数”口径展示。
- 进程级上行/下行排行，按需加载，降低后台压力。
- 连接与端口弹窗，支持筛选、分页、公网/内网、方向、协议、网卡、进程和关键词过滤。
- Docker 容器列表、端口识别、手动端口、端口备注、服务类型、快捷访问、图标上传。
- Docker stats 按需加载，页面离开后不继续刷新，减少 Docker socket 压力。
- 监控中心，可配置上传速率、连接数、每日流量等规则。
- 通知渠道模块，支持 Webhook、IYUU、MeoW，并支持消息模板变量。
- 历史统计折线图，支持今日、本周、本月等时间范围。
- 系统状态页面，展示 CPU、内存、磁盘、温度、GPU/NPU 可见性。
- 支持访问密码、登录失败限制、SQLite 持久化、日志目录映射。

## 适用环境

推荐运行方式是 Docker。

| 环境 | 说明 |
| --- | --- |
| 极空间 Z425 | Intel Ultra 5 125H，x64 架构，推荐 `linux/amd64` 镜像 |
| 普通 x86 NAS / Linux 主机 | 使用 `linux/amd64` |
| ARM NAS / ARM Linux 主机 | 使用 `linux/arm64` |
| macOS / Windows Docker Desktop | 可用于开发和构建，但采集宿主网络信息会受 Docker 虚拟化限制 |

要完整读取宿主网络、进程和 Docker 信息，Linux/NAS 部署时建议使用：

- `network_mode: host`
- `pid: host`
- `privileged: true`
- 可选映射 `/var/run/docker.sock`

## 快速部署

如果镜像已经推送到 Docker Hub，可以直接使用 `docker-compose.nas.yml`：

```bash
docker compose -f docker-compose.nas.yml up -d
```

然后访问：

```text
http://NAS-IP:8088
```

默认端口是 `8088`，可通过环境变量修改：

```yaml
environment:
  APP_PORT: "8088"
```

默认 compose 已设置访问密码：

```yaml
DASHBOARD_PASSWORD: "123456"
```

如果只在内网访问，也仍建议保留密码。要关闭密码，删除或置空 `DASHBOARD_PASSWORD`。

## NAS 推荐 Compose

极空间 Z425 推荐使用 `linux/amd64`：

```yaml
services:
  nas-traffic-lens:
    image: isle204/nas-traffic-lens:latest
    container_name: nas-traffic-lens
    restart: unless-stopped
    network_mode: host
    pid: host
    platform: linux/amd64
    privileged: true
    environment:
      APP_PORT: "8088"
      SAMPLE_SECONDS: "1"
      RETENTION_SECONDS: "3600"
      DB_PATH: "/data/traffic.db"
      LOG_DIR: "/logs"
      ENABLE_DOCKER_DISCOVERY: "false"
      DOCKER_LIST_CACHE_SECONDS: "20"
      DOCKER_STATS_CACHE_SECONDS: "5"
      DOCKER_WEB_PROBE_TTL_SECONDS: "86400"
      DOCKER_WEB_PROBE_TIMEOUT: "1"
      DOCKER_API_MAX_BYTES: "2097152"
      COLLECTOR_MODE: "auto"
      COLLECTOR_PROFILE: "balanced"
      GO_COLLECTOR_ENABLED: "true"
      ENABLE_PACKET_CAPTURE: "true"
      CAPTURE_MAX_EVENTS_PER_SECOND: "2000"
      CAPTURE_SAMPLE_RATE: "1"
      CAPTURE_DYNAMIC_SAMPLE: "true"
      CAPTURE_MAX_SAMPLE_RATE: "50"
      ENABLE_SYSTEM_TRAFFIC_CALIBRATION: "true"
      SYSTEM_TRAFFIC_CALIBRATION_THRESHOLD: "1.25"
      SYSTEM_TRAFFIC_CALIBRATION_MIN_BYTES: "262144"
      SYSTEM_TRAFFIC_CALIBRATION_MAX_FACTOR: "20"
      SYSTEM_TRAFFIC_CALIBRATION_ASSUME_WAN: "false"
      MAX_RATE_HISTORY_POINTS: "180"
      PROCESS_RECENT_SECONDS: "180"
      MAX_CONNECTION_TRACKED: "10000"
      MAX_PROCESS_TRACKED: "2048"
      MAX_PORT_TRACKED: "4096"
      MAX_DOCKER_CACHE_ENTRIES: "512"
      MAX_DOCKER_ICON_DATA_CHARS: "2097152"
      UVICORN_ACCESS_LOG: "false"
      FILE_LOG: "true"
      CONSOLE_LOG: "true"
      DASHBOARD_PASSWORD: "123456"
      ALERT_WAN_TX_BPS: "10485760"
      ALERT_WAN_TX_SECONDS: "300"
      ALERT_STAGE_TX_BYTES: "10737418240"
      ALERT_DAILY_TX_BYTES: "53687091200"
      ALERT_NOTIFY_CHANNEL: "webhook"
      ALERT_WEBHOOK_URL: ""
      ALERT_WEBHOOK_TIMEOUT: "5"
      CONNECTION_ACTIVE_SECONDS: "120"
      CONNECTION_RETENTION_SECONDS: "900"
      AUTO_START_STAGE: "true"
      CONNECTION_COUNT_SOURCE: "conntrack"
      CONNTRACK_REFRESH_SECONDS: "30"
      CONNTRACK_COUNT_MODE: "active"
      CONNTRACK_TCP_STATES: "ESTABLISHED"
      CONNTRACK_UDP_REQUIRE_ASSURED: "true"
      CONNTRACK_INCLUDE_UNREPLIED: "false"
      CONNTRACK_MIN_TIMEOUT_SECONDS: "3"
      CONNTRACK_MAX_LINES: "30000"
      CONNTRACK_SCAN_SECONDS: "1"
      CONNTRACK_CONNECTION_MAX_LINES: "30000"
      CONNTRACK_CONNECTION_SCAN_SECONDS: "1.5"
      SOCKET_REFRESH_SECONDS: "60"
      PROC_SCAN_TIMEOUT_SECONDS: "1"
      MAX_PROC_FD_LINKS: "60000"
      MAX_PROC_NET_LINES: "60000"
      # CAPTURE_INTERFACES: "eth0"
    volumes:
      - ./data:/data
      - ./logs:/logs
      # 需要 Docker 容器名、端口映射、容器列表时再打开。
      # Docker socket 权限很高，确认需要后再启用。
      # 同时需要设置 ENABLE_DOCKER_DISCOVERY: "true"
      # - /var/run/docker.sock:/var/run/docker.sock:ro
    # 可选：暴露 Intel 核显 / NPU 设备，极空间 UI 支持 devices 时再打开。
    # devices:
    #   - /dev/dri:/dev/dri
    #   - /dev/accel:/dev/accel
```

注意：极空间 UI 如果提示 `invalid volume path: /proc`，不要映射 `/proc`。本项目通过 `pid: host` 读取宿主进程信息，不需要把 `/proc` 作为 volume 映射。

## 本地 Docker 构建

项目使用多阶段 Dockerfile：

1. `node:20-slim` 构建前端静态资源。
2. `python:3.12-slim` 安装后端依赖和运行 FastAPI。
3. 镜像内读取 `/app/VERSION` 作为页面和 API 版本号。

本机直接构建并运行：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker logs -f nas-traffic-lens
```

停止：

```bash
docker compose down
```

## 构建 amd64 镜像

极空间 Z425 是 x64 架构，应构建 `linux/amd64`。

```bash
VERSION=$(cat VERSION)

docker buildx build \
  --platform linux/amd64 \
  -t isle204/nas-traffic-lens:${VERSION} \
  -t isle204/nas-traffic-lens:latest \
  --load .
```

导出离线包：

```bash
docker save \
  isle204/nas-traffic-lens:${VERSION} \
  isle204/nas-traffic-lens:latest \
  -o nas-traffic-lens-amd64.tar
```

在 NAS 上导入：

```bash
docker load -i nas-traffic-lens-amd64.tar
```

然后 compose 使用：

```yaml
image: isle204/nas-traffic-lens:latest
platform: linux/amd64
```

## 构建 arm64 镜像

给 ARM NAS 或 ARM Linux 主机使用：

```bash
VERSION=$(cat VERSION)

docker buildx build \
  --platform linux/arm64 \
  -t isle204/nas-traffic-lens:${VERSION}-arm64 \
  -t isle204/nas-traffic-lens:arm64 \
  --load .
```

导出离线包：

```bash
docker save \
  isle204/nas-traffic-lens:${VERSION}-arm64 \
  isle204/nas-traffic-lens:arm64 \
  -o nas-traffic-lens-arm64.tar
```

ARM 设备 compose 示例：

```yaml
image: isle204/nas-traffic-lens:arm64
platform: linux/arm64
```

## 构建并发布多架构镜像

如果要发布到 Docker Hub，让同一个 tag 同时支持 `amd64` 和 `arm64`，使用 `--push`：

```bash
VERSION=$(cat VERSION)

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t isle204/nas-traffic-lens:${VERSION} \
  -t isle204/nas-traffic-lens:latest \
  --push .
```

如果不想自动推送，只想本地打包，请使用前面单架构的 `--load` + `docker save`。`docker buildx build --load` 一次只能可靠加载一个平台，所以本项目建议 amd64 和 arm64 分开构建、分开保存 tar。

## 推送 Docker Hub

登录：

```bash
docker login
```

推送 amd64 固定版本和 latest：

```bash
VERSION=$(cat VERSION)

docker push isle204/nas-traffic-lens:${VERSION}
docker push isle204/nas-traffic-lens:latest
```

推送 arm64：

```bash
VERSION=$(cat VERSION)

docker push isle204/nas-traffic-lens:${VERSION}-arm64
docker push isle204/nas-traffic-lens:arm64
```

日常部署推荐使用 `latest`，这样文档和 compose 不需要每次跟着版本号修改。遇到缓存、回滚或需要确认版本时，再改用固定版本 tag，例如当前 `VERSION` 文件中的版本。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8088` | Web 服务端口 |
| `DASHBOARD_PASSWORD` | 空 | 设置后启用访问密码 |
| `APP_SECRET` | 空 | 会话签名密钥；不填时根据密码派生，生产环境建议设置 |
| `SESSION_TTL_SECONDS` | `604800` | 登录会话有效期，默认 7 天 |
| `DB_PATH` | `/data/traffic.db` | SQLite 数据库路径 |
| `LOG_DIR` | `/logs` | 日志目录 |
| `UVICORN_ACCESS_LOG` | `false` | 是否开启 HTTP access log，默认关闭以降低写盘 |
| `FILE_LOG` | `true` | 是否写入 `LOG_DIR` 文件；设为 `false` 时直接输出到容器 stdout/stderr |
| `CONSOLE_LOG` | `true` | 是否把日志同步输出到容器控制台 |
| `SAMPLE_SECONDS` | `1` | 采样间隔 |
| `RETENTION_SECONDS` | `3600` | 内存中短期历史保留秒数 |
| `PERSIST_INTERVAL_SECONDS` | `60` | 写入 SQLite 的间隔 |
| `HISTORY_RETENTION_DAYS` | `400` | 历史数据保留天数 |
| `COLLECTOR_PROFILE` | `balanced` | 采集档位：`low` 低负载近似公网总量、`balanced` Go/libpcap 优先、`diagnostic` 诊断模式 |
| `COLLECTOR_MODE` | `auto` | 采集后端：`auto`/`golibpcap`/`python`/`off`；`ebpf` 目前仅实验提示并回退 Go |
| `GO_COLLECTOR_ENABLED` | `true` | 是否允许启动 Go libpcap 外部采集器 |
| `ENABLE_PACKET_CAPTURE` | `true` | 是否启用抓包归因；关闭后公网累计和进程流量会不可用或变少 |
| `CAPTURE_INTERFACES` | 自动 | 指定抓包接口，逗号分隔；`all` 表示抓所有启用接口 |
| `CAPTURE_MAX_EVENTS_PER_SECOND` | `2000` | 抓包每秒精确记录阈值，超过后动态抽样并按倍率折算 |
| `CAPTURE_SAMPLE_RATE` | `1` | 固定抓包采样率，`1` 表示不固定抽样 |
| `CAPTURE_DYNAMIC_SAMPLE` | `true` | 高包量时是否自动抽样并按倍率折算流量 |
| `CAPTURE_MAX_SAMPLE_RATE` | `50` | 动态抽样最大倍率 |
| `ENABLE_SYSTEM_TRAFFIC_CALIBRATION` | `true` | 抓包统计明显低于系统网卡计数时，用系统计数补齐总量 |
| `SYSTEM_TRAFFIC_CALIBRATION_THRESHOLD` | `1.25` | 系统网卡增量超过抓包增量多少倍时触发校准 |
| `SYSTEM_TRAFFIC_CALIBRATION_MIN_BYTES` | `262144` | 单次校准最小系统增量，避免小流量抖动 |
| `SYSTEM_TRAFFIC_CALIBRATION_MAX_FACTOR` | `20` | 单次校准最大补齐倍率 |
| `SYSTEM_TRAFFIC_CALIBRATION_ASSUME_WAN` | `false` | 抓包没有公网/内网比例时是否默认补到公网 |
| `MAX_RATE_HISTORY_POINTS` | `180` | 内存中的实时速率诊断点数，历史图表使用 SQLite |
| `ENABLE_DOCKER_DISCOVERY` | `false` | 是否读取 Docker socket 自动发现容器和端口 |
| `DOCKER_SOCKET` | `/var/run/docker.sock` | Docker socket 路径 |
| `DOCKER_LIST_CACHE_SECONDS` | `20` | Docker 容器列表缓存秒数 |
| `DOCKER_STATS_CACHE_SECONDS` | `5` | 单容器 stats 缓存秒数 |
| `DOCKER_WEB_PROBE_TTL_SECONDS` | `86400` | Web 端口探测缓存秒数 |
| `DOCKER_WEB_PROBE_TIMEOUT` | `1` | 单次 Web 探测超时秒数 |
| `DOCKER_API_MAX_BYTES` | `2097152` | 单次 Docker socket 响应最大读取字节 |
| `PROCESS_RECENT_SECONDS` | `180` | 30 秒进程排行的内存缓存窗口，默认只保留最近几分钟 |
| `MAX_CONNECTION_TRACKED` | `10000` | 抓包连接缓存硬上限，超过后淘汰最久未活跃连接 |
| `MAX_PROCESS_TRACKED` | `2048` | 进程累计缓存硬上限 |
| `MAX_PORT_TRACKED` | `4096` | 端口累计缓存硬上限 |
| `MAX_DOCKER_CACHE_ENTRIES` | `512` | Docker stats 和 Web 探测缓存条目上限 |
| `MAX_DOCKER_ICON_DATA_CHARS` | `2097152` | 单个 Docker 图标 data URL 最大字符数 |
| `LOGIN_MAX_ATTEMPTS` | `10` | 单客户端登录失败次数上限 |
| `LOGIN_LOCK_SECONDS` | `300` | 登录锁定秒数 |
| `ALERT_WAN_TX_BPS` | `0` | 默认持续公网上传速率阈值，单位 B/s |
| `ALERT_WAN_TX_SECONDS` | `0` | 默认持续公网上传触发秒数 |
| `ALERT_STAGE_TX_BYTES` | `0` | 兼容旧阶段上传规则，首页不再展示阶段公网 |
| `ALERT_DAILY_TX_BYTES` | `0` | 默认每日公网上传阈值，单位 B |
| `ALERT_NOTIFY_CHANNEL` | `webhook` | 默认通知渠道类型：`webhook`、`iyuu`、`meow` |
| `ALERT_WEBHOOK_URL` | 空 | 默认 Webhook 地址 |
| `ALERT_WEBHOOK_TIMEOUT` | `5` | 通知请求超时秒数 |
| `CONNECTION_ACTIVE_SECONDS` | `120` | 活跃连接统计窗口 |
| `CONNECTION_RETENTION_SECONDS` | `900` | 连接明细缓存保留秒数 |
| `CONNECTION_COUNT_SOURCE` | `conntrack` | 连接数来源：`conntrack`、`socket`、`capture` |
| `CONNTRACK_REFRESH_SECONDS` | `30` | conntrack 连接数刷新间隔 |
| `CONNTRACK_COUNT_MODE` | `active` | `active` 统计活跃会话，`raw` 统计原始表条目 |
| `CONNTRACK_TCP_STATES` | `ESTABLISHED` | active 模式下计入的 TCP 状态 |
| `CONNTRACK_UDP_REQUIRE_ASSURED` | `true` | UDP 是否只统计已确认双向会话 |
| `CONNTRACK_INCLUDE_UNREPLIED` | `false` | 是否统计未回应连接 |
| `CONNTRACK_MIN_TIMEOUT_SECONDS` | `3` | active 模式最小剩余超时时间 |
| `CONNTRACK_MAX_LINES` | `30000` | 首页连接数每次最多扫描 conntrack 行数 |
| `CONNTRACK_SCAN_SECONDS` | `1` | 首页连接数每次最多扫描秒数 |
| `CONNTRACK_CONNECTION_MAX_LINES` | `30000` | 连接弹窗 conntrack 明细每次最多扫描行数 |
| `CONNTRACK_CONNECTION_SCAN_SECONDS` | `1.5` | 连接弹窗 conntrack 明细每次最多扫描秒数 |
| `SOCKET_TCP_STATES` | `ESTABLISHED` | socket 模式下计入的 TCP 状态 |
| `SOCKET_REFRESH_SECONDS` | `60` | socket 连接数刷新间隔 |
| `PROC_SCAN_TIMEOUT_SECONDS` | `1` | 扫描 `/proc` socket 到进程归属的单次时间预算 |
| `MAX_PROC_FD_LINKS` | `60000` | 单次最多读取的进程 fd 链接数 |
| `MAX_PROC_NET_LINES` | `60000` | 单个 `/proc/net/*` 文件最多读取行数 |
| `INTERFACE_REFRESH_SECONDS` | `30` | 网卡元信息刷新间隔 |

页面“监控中心”可以修改监控规则、通知渠道、消息模板和部分运行参数。页面保存后的配置会写入 SQLite，优先级高于环境变量。端口、日志目录、Docker 发现、Docker socket、抓包接口属于启动期配置，修改后需要重启容器。

## 数据和日志

推荐映射：

```yaml
volumes:
  - ./data:/data
  - ./logs:/logs
```

文件说明：

- SQLite：`./data/traffic.db`
- 普通日志：`./logs/uvicorn.log`
- 错误日志：`./logs/uvicorn-error.log`

清理历史统计：

```bash
docker compose down
rm -f ./data/traffic.db
docker compose up -d
```

清理日志：

```bash
rm -f ./logs/*.log
docker restart nas-traffic-lens
```

## Docker 容器发现

默认关闭 Docker 自动发现：

```yaml
ENABLE_DOCKER_DISCOVERY: "false"
```

如果需要在页面显示容器列表、容器端口、端口备注和快捷访问，打开：

```yaml
environment:
  ENABLE_DOCKER_DISCOVERY: "true"
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
```

Docker socket 权限很高，即使只读映射也能暴露大量宿主 Docker 信息。只在内网可信环境使用。

性能策略：

- `/api/docker/containers` 只返回轻量容器列表。
- `/api/docker/containers/{id}` 单独返回某个容器的端口、图标、备注等详情。
- `/api/docker/containers/{id}/stats` 只在点击“显示占用”时读取。
- 页面关闭或离开 Docker 页后，不继续刷新容器 stats。

host 网络模式容器通常没有 published ports，页面支持手动添加端口。

## GPU / NPU / 温度

Intel 核显通常通过 `/dev/dri` 暴露：

```yaml
devices:
  - /dev/dri:/dev/dri
```

NPU/AI Boost 是否可见取决于宿主驱动和设备节点。如果宿主存在 `/dev/accel`，可尝试：

```yaml
devices:
  - /dev/accel:/dev/accel
```

容器能看到设备，不代表一定能读取利用率。Intel 核显/NPU 的利用率通常依赖宿主内核、驱动和 sysfs/debugfs 指标。读不到时，页面会显示设备可用但利用率未暴露。

温度会把 `coretemp`、`acpitz`、`nvme`、`drivetemp` 等传感器名整理为 CPU、主板/机箱、NVMe、硬盘等更容易看的名称。

## 常见问题

### 极空间提示 invalid volume path: /proc

不要映射 `/proc`。使用：

```yaml
pid: host
```

### 页面提示采集器连接失败或接口 500

优先查看日志：

```bash
docker logs -f nas-traffic-lens
```

如果日志写入文件：

```bash
tail -f ./logs/uvicorn-error.log
```

常见处理：

- 只抓必要网卡，设置 `CAPTURE_INTERFACES: "eth0"` 或实际物理网卡名。
- 保持默认只展示物理网卡，需要排查时再切换“全部接口”。
- 保持 Docker stats 按需查看，不要让页面长期打开大量容器详情。
- `ENABLE_DOCKER_DISCOVERY` 出问题时先设为 `false`，再确认 Docker socket 是否可映射。
- 查看 `/api/diagnostics` 可以看到当前 RSS 内存、线程数、连接缓存、进程缓存、Docker 缓存规模。

### 运行几天后 CPU 或内存变高

优先打开：

```text
http://NAS-IP:8088/api/diagnostics
```

重点看：

- `memory.rssBytes`：后端进程实际内存。
- `caches.connectionTotals`：抓包连接缓存数量。
- `caches.processTotals`：进程累计缓存数量。
- `caches.processRecentKeys`：短期进程排行缓存数量。
- `caches.dockerStats` / `caches.dockerWebProbes`：Docker 按需缓存数量。
- `capture.droppedEvents`：动态抽样跳过的包数。
- `capture.sampledEvents` / `capture.weightedBytes`：抽样折算是否正在发生。
- `calibration.interfaces`：系统网卡计数校准是否已参与补齐。
- `conntrack.truncated`：conntrack 是否因行数或时间预算被截断。

默认已经加了硬上限，BT、DHT、UDP 或大量短连接不会无限撑大内存。如果 NAS 负载仍高，可以进一步调低：

```yaml
PROCESS_RECENT_SECONDS: "90"
CONNECTION_RETENTION_SECONDS: "300"
MAX_CONNECTION_TRACKED: "8000"
MAX_PROCESS_TRACKED: "2048"
MAX_PORT_TRACKED: "4096"
CAPTURE_MAX_EVENTS_PER_SECOND: "1000"
CONNTRACK_MAX_LINES: "15000"
CONNTRACK_CONNECTION_MAX_LINES: "15000"
```

如果不常看连接明细，也可以只抓指定物理网卡：

```yaml
CAPTURE_INTERFACES: "eth0"
```

如果 Docker 引擎或宿主负载异常，先用保守模式验证：

```yaml
ENABLE_DOCKER_DISCOVERY: "false"
CONNECTION_COUNT_SOURCE: "socket"
ENABLE_PACKET_CAPTURE: "false"
FILE_LOG: "false"
```

这个模式会牺牲公网阶段统计、进程流量归因和 Docker 自动发现，但可以快速判断压力是否来自 conntrack/抓包/Docker socket。

### 迅雷或 BT 下载统计偏低

迅雷、BT、DHT 这类场景包量很高。旧版本为了保护 Docker 引擎，超过 `CAPTURE_MAX_EVENTS_PER_SECOND` 后会直接跳过包，因此可能出现极空间系统监控显示 10MB/s 以上，而本页面公网流量只显示 1MB/s 左右。

新版本改为两层保护：

- 超过精确记录阈值后动态抽样，并按抽样倍率折算字节数。
- 如果抓包统计仍明显低于系统网卡计数，会按已识别到的公网/内网比例补齐接口总量和历史统计。

排查时打开：

```text
http://NAS-IP:8088/api/diagnostics
```

重点看 `capture.sampledEvents`、`capture.weightedBytes` 和 `calibration.interfaces`。如果它们在下载时增长，说明高速下载已经触发抽样/校准。

如果你希望更精确、NAS CPU 也扛得住，可以提高：

```yaml
CAPTURE_MAX_EVENTS_PER_SECOND: "5000"
CAPTURE_MAX_SAMPLE_RATE: "100"
```

### 公网连接数特别大

默认使用 conntrack 的 active 模式，尽量贴近路由器活跃会话数。如果仍然偏大，可以调小：

```yaml
CONNECTION_ACTIVE_SECONDS: "60"
CONNTRACK_MIN_TIMEOUT_SECONDS: "10"
CONNTRACK_UDP_REQUIRE_ASSURED: "true"
CONNTRACK_INCLUDE_UNREPLIED: "false"
```

如果宿主没有 conntrack，可改：

```yaml
CONNECTION_COUNT_SOURCE: "socket"
```

### Docker 页很慢

保持：

```yaml
DOCKER_LIST_CACHE_SECONDS: "20"
DOCKER_STATS_CACHE_SECONDS: "5"
```

列表页只加载容器摘要，单容器端口和 stats 都是按需接口。如果仍然慢，先关闭 Docker 自动发现，使用手动端口配置。

### Redis、MySQL 这类端口不能直接打开

页面会尽量识别常见非 Web 服务。非 Web 端口默认复制地址，不直接 `http://` 打开。可手动设置端口类型，或点击探测按钮让服务缓存一次 HTTP/HTTPS 探测结果。

## 开发

前端：

```bash
cd front-end
npm install
npm run build
```

后端：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r server/requirements.txt
APP_PORT=8088 FRONTEND_DIR=front-end/dist python -m uvicorn server.main:app --host 0.0.0.0 --port 8088
```

代码检查：

```bash
python3 -m py_compile server/main.py server/services/*.py
cd front-end && npm run build
```

## 版本发布建议

1. 修改代码。
2. 更新 `VERSION`，例如 `2026.06.26-3`。
3. 运行后端和前端检查。
4. 提交 Git。
5. 分别构建 amd64 和 arm64。
6. 生成 tar 或推送 Docker Hub。
7. NAS compose 使用固定版本 tag 部署。

版本号由镜像内 `/app/VERSION` 提供，页面和 `/api/health` 会显示这个版本。不要只改 Docker tag 而不改 `VERSION`。

## 更多文档

更细的功能说明、设计取舍和模块说明见：

- [doc/README.md](doc/README.md)

## 采集后端与低负载模式

启动时默认优先使用 **Go + libpcap**，不可用时回退 **Python Scapy**。eBPF 代码保留为实验方向，但当前生产镜像不启用 eBPF。

| 档位 | 适合场景 | 行为 |
|---|---|---|
| `low` | 长期常驻，接近宝塔这类面板的低负载统计 | 不抓包，按物理/默认网卡系统计数近似公网总量，不提供进程/端口归因 |
| `balanced` | 默认推荐 | Go libpcap 抓包，保留公网/内网、进程、连接、端口归因 |
| `diagnostic` | 排查偷跑或异常连接 | 保留详细采集能力，适合短时间打开 |

可通过 `COLLECTOR_PROFILE=low|balanced|diagnostic` 和 `COLLECTOR_MODE=auto|golibpcap|python|off` 调整。细节见 [doc/README.md § 采集后端架构](doc/README.md#采集后端架构与低负载模式)。

## 开发

Go collector（独立编译）：

```bash
cd server/go-collector
go build -o go-collector .
```

前端：
