# 多 NAS 兼容性说明（Multi-NAS compatibility）

本文记录 NAS Traffic Lens 在不同 NAS 系统上的实测结果、能力差异和部署方式。所有结论都来自实机验证，未实测的部分会明确标注。

## 1. 支持矩阵（2026-10-07 实测）

| 项目 | 极空间 Z425 | 绿联 DXP4300 Plus | 飞牛 OS / 通用 Linux |
| --- | --- | --- | --- |
| 状态 | ✅ 已部署验证 | ✅ 已部署验证 | ⚠️ 未实测（按通用 Debian 适配） |
| 架构 | x86_64（Intel Ultra 5 125H） | aarch64（8 核 ARM，RK3588 级） | 视机型 |
| 系统 | ZOS（ZFS 数据集 `/tmp/zfsv3/...`） | Debian 12 + UGOS，内核 6.1.84 | Debian 系 |
| 容器运行时 | Docker 29.x + Compose v2.29.7 | Docker 29.6.2 + Compose **v5.1.3**（UGOS 自带） | 视安装 |
| GPU 利用率 | i915 PMU（6 个引擎：渲染/计算/编解码/拷贝） | **devfreq** `fb000000.gpu/load`（Mali GPU） | 自动探测：i915 PMU → amdgpu → devfreq |
| NPU 利用率 | `/sys/class/accel/accel0/device/npu_busy_time_us` | **devfreq** `fdab0000.npu/load`（RKNPU，governor `rknpu_ondemand`） | 多数机型没有，显示"未暴露" |
| VPU 利用率 | 不适用（Intel 走 i915 的 vcs 引擎） | **`/proc/mpp_service/load`**，13 个编解码核心，带真实百分比 | 视机型（Rockchip 系同绿联） |
| 温度 | coretemp / acpitz / nvme / eth1（4 组） | 7 路 hwmon：SoC、CPU 大核 0/1、CPU 小核、SoC 中心、GPU、NPU | hwmon 通用 |
| 风扇 | 3 路（`acpi_ec_z425`） | 未在 hwmon 暴露 → 显示"未暴露风扇转速传感器" | 视机型 |
| 应用目录 | `<zfs>/data/docker/<应用>/` | 创建项目时**自选存放路径**；Docker 数据根 `/volume2/@docker` | 视安装 |

## 2. 部署

### 2.1 极空间（ZOS）

```bash
mkdir -p /tmp/zfsv3/nvme16/<用户ID>/data/docker/nas-traffic-lens
cd /tmp/zfsv3/nvme16/<用户ID>/data/docker/nas-traffic-lens
# 写入 docker-compose.yml（见 2.4），然后：
docker compose -p nas-traffic-lens up -d
```

注意：

- 绑定路径必须在 ZFS 数据集下；**禁止挂载 `/proc`**（会被拒绝：`invalid volume path: /proc`）。
- 极空间的 Docker 界面能看到容器，但"应用"列表是它自己的元数据，外部 compose 创建的应用不保证收录。

### 2.2 绿联云（UGOS Pro）

实测要点：

- 允许 `privileged: true` + `network_mode: host` + `pid: host`（已实测启动成功）。
- `docker` 组存在（gid 121），普通管理员账号默认不在组内，需要 `sudo usermod -aG docker <用户>` 后重新登录。
- `scp`/SFTP 被限制在用户 home 之下，传文件用 `ssh <host> 'cat > /path/file' < local-file`。
- 创建项目时由用户自选存放路径；推荐 `/volume2/docker/nas-traffic-lens/`（`/volume2/docker` 默认可写）。
- 容器内可读：`/dev/dri`（card0/card1/renderD128/renderD129）、`/sys/class/devfreq/*`、`/proc/mpp_service/load`；**docker.sock 需要显式挂载**（`/var/run` 不共享）。

```bash
mkdir -p /volume2/docker/nas-traffic-lens/{data,logs}
cd /volume2/docker/nas-traffic-lens
# 写入 docker-compose.yml（见 2.4，路径用 /volume2/docker/nas-traffic-lens）
docker compose up -d
```

### 2.3 飞牛 OS / 通用 Linux

未实测。通用模板 `docker-compose.generic.yml` 使用相对路径 `./data`、`./logs`，在任何装好 Docker 的 Linux 上都能跑；GPU/NPU/VPU 利用率会自动探测，探测不到时显示具体原因，不影响其它功能。

### 2.4 Compose 模板要点

三个平台共用同一份服务定义，只有路径与 `platform` 不同：

```yaml
services:
  nas-traffic-lens:
    image: isle204/nas-traffic-lens:2026.10.07-7   # 多架构：amd64 + arm64
    container_name: nas-traffic-lens
    restart: unless-stopped
    network_mode: host      # 抓包与连接归因需要宿主机网络
    pid: host               # 进程归因需要宿主机 PID 命名空间
    privileged: true        # /dev/dri、PMU、温度与 MPP 需要
    environment:
      APP_PORT: '8088'
      DASHBOARD_PASSWORD: <改成你自己的密码>
      TZ: Asia/Shanghai
    volumes:
      - <数据目录>/data:/data
      - <数据目录>/logs:/logs
      - /var/run/docker.sock:/var/run/docker.sock:ro   # 容器清单与保护动作
```

## 3. 加速器读数的来源与语义

| 平台 | 来源 | 语义 |
| --- | --- | --- |
| Intel | i915 PMU（perf_event_open） | 每个引擎的忙碌时间占比 |
| Intel NPU | `npu_busy_time_us` 增量 | 累计忙碌时间换算成占比 |
| ARM/Rockchip GPU/NPU | `/sys/class/devfreq/*/load`（`load@freq`） | governor 上报的负载（千分比），**扣除观测到的最小基线** |
| ARM/Rockchip VPU | `/proc/mpp_service/load` | 驱动直接给出的 `load` 与 `utilization` 百分比，按核心与职责（解码/编码/图像处理）聚合 |

关于 devfreq 基线：绿联的 RKNPU 在完全空闲时仍上报 `load=100`（即 10%），因此实现里对每个 devfreq 设备记录观测到的最小 load 作为基线，展示的是 `load - 基线` 换算后的百分比；卡片详情里同时给出原始 `load`、基线与 governor，便于核对。GPU 的基线通常为 0。

无法读取时不会静默：卡片会给出具体原因（未映射 `/dev/dri`、内核缺少 PMU、缺乏 CAP_PERFMON、缺少 `/proc/mpp_service` 等）。

## 4. 已知差异与限制

- 绿联的风扇转速未通过 hwmon 暴露，系统页显示"当前环境未暴露风扇转速传感器"。
- 绿联 VPU 只有在播放/转码时才会出现非零利用率；空闲为 0 属于正常。
- 极空间不适用 VPU 卡片（Intel 平台的编解码负载体现在 i915 的 vcs 引擎上）。
- 部分 cgroup v2 / rootless 场景容器磁盘 IO 统计恒为 0，与 NAS 品牌无关。
- 除极空间与绿联外，其余 NAS 系统未做实测；遇到问题请附 `/api/system` 输出。
