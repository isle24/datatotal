# Compose 与运行配置精简设计

## 目标

降低 NAS 用户部署 NAS Traffic Lens 的配置门槛。推荐 compose 只展示部署时必须决定的参数；用户日常会调整的监控与运行参数使用代码默认值，并在保存后持久化到 SQLite。

## 配置边界

### Compose 保留

- `APP_PORT`：Web 服务监听端口，只能在进程启动前确定，默认 `8088`。
- `DASHBOARD_PASSWORD`：登录密码属于启动期安全配置，示例值使用 `123456`。
- `./data:/data`：SQLite、上传图标和其他持久化数据目录。
- `./logs:/logs`：文件日志目录，方便查看和清理。
- `/var/run/docker.sock:/var/run/docker.sock:ro`：默认映射 Docker socket，用于容器发现、端口读取和容器保护动作。
- `network_mode: host`、`pid: host`、`privileged: true`：宿主网络流量、进程归属和抓包所需权限。
- `platform: linux/amd64`：NAS 推荐模板面向极空间 Z425；本地构建模板同样保持 amd64。

`DB_PATH` 和 `LOG_DIR` 不再写入 compose，因为程序默认值已经分别是 `/data/traffic.db` 和 `/logs`，与目录映射一致。

### SQLite 管理

- 采样间隔、内存保留时间、SQLite 写入间隔和历史保留天数。
- 活跃连接窗口、连接缓存时间、Conntrack 刷新间隔和阶段统计自动启动。
- 监控规则、容器保护规则、通知渠道、通知模板、Docker 端口备注和图标。

首次启动没有 SQLite 配置时使用代码默认值；页面保存后 SQLite 配置优先于对应环境变量默认值。

### 仅保留代码默认值和高级环境变量覆盖

抓包抽样上限、Conntrack 扫描保护、进程扫描预算、内存缓存硬上限、Docker API 响应上限等低层诊断参数不放入推荐 compose，也不做普通用户 UI。它们继续使用代码中的保守默认值，高级用户仍可参考环境变量表按需覆盖。

## Docker 默认行为

- 后端 `ENABLE_DOCKER_DISCOVERY` 默认值从关闭改为开启。
- 两个 compose 默认映射 Docker socket，不再要求用户取消注释或额外设置环境变量。
- Docker socket 不存在、不可访问或 Docker API 请求失败时，应用继续运行，Docker 页面显示无可用数据，不影响流量采集和历史统计。
- 文档明确 Docker socket 等同于较高宿主控制权限；不需要 Docker 功能的用户可以删除该挂载，并显式设置 `ENABLE_DOCKER_DISCOVERY=false`。

## 推荐 Compose 形态

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
      DASHBOARD_PASSWORD: "123456"
    volumes:
      - ./data:/data
      - ./logs:/logs
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

## 文档调整

- README 的快速部署和 NAS compose 示例改为精简版本。
- 环境变量章节拆成“推荐配置”和“高级覆盖”，避免让普通用户误以为所有变量都必须填写。
- Docker 章节改为默认开启，并说明关闭方法和 socket 安全风险。
- `doc/README.md` 与根 README 保持一致。

## 验证

- 自动测试检查两个 compose 只包含允许的环境变量、默认映射 `/data`、`/logs` 和 Docker socket。
- 自动测试检查 Docker 发现未设置环境变量时默认启用，显式 `false` 时仍可关闭。
- 解析两个 compose，确保 YAML 合法。
- 运行后端测试、前端构建和 Docker amd64/arm64 构建。
- 发布前把版本号从 `2026.06.29-2` 升到当天版本 `2026.07.17-1`，并同时生成版本 tag、`latest` 和架构 tag。
