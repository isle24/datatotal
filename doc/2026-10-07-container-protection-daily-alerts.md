# Docker 容器保护和每日上传报警交付记录

## 最终行为

容器保护支持单容器、多选和所有运行中容器。按每个目标独立判断 CPU、内存或磁盘 I/O 阈值、持续时间和冷却；达到条件后重启该容器，重启次数不限，累计次数仅记录历史，不会按次数改成停止或锁定。旧版已知次数上限锁定自动解除，历史次数保留。明确选择停止的规则和结果不确定的待确认状态仍保留原语义。

修正 cgroup v2 CPU 核心数、并发采样、失败隔离、慢动作后的过期样本刷新、容器重建及 Compose 副本匹配。多容器和监控范围切换均保留各自历史。前端显示可读单位与逐容器采样结果；移除最大重启次数输入。

上传总量新规则默认按自然日判断 WAN 上传，每条规则每天独立报警，跨天重算，通知标记跨服务重启保留。NAS 设置 TZ=Asia/Shanghai。原 10 GB 阶段累计规则已转换成每日规则，原 50 GB 每日规则、阈值、ID、持续时间和渠道保留。

## 验证

- Python 133 项、前端 24 项通过；NAS 和桌面嵌入页面构建成功。
- amd64/arm64 最终镜像各 43 项相关测试通过；独立代码审查通过。
- CPU 公式参考 [Docker Engine API 官方定义](https://raw.githubusercontent.com/moby/moby/master/api/swagger.yaml)。Go 采集器与已发布基线一致。
- 已有 FastAPI lifespan 弃用和 Vite 大分块提示仍存在。

## Docker Hub

版本：2026.10.07-2。已发布版本、latest 和架构标签，支持 linux/amd64、linux/arm64。

仓库：[isle204/nas-traffic-lens](https://hub.docker.com/r/isle204/nas-traffic-lens/tags)。版本及 latest 的多架构 digest 均为 `sha256:563bac92e097d3b88ae6d5f7041b3be5c9a840dddc432131be665af8adf318d7`。

候选 2026.10.07-1 被新版本取代，未发布或部署。

## NAS 部署

sshbind zspace，192.168.3.56。用户开通 docker 组权限后，已在原 Compose 项目部署。

- Compose：`/tmp/zfsv3/nvme16/18181998187/data/docker/nas-traffic-lens/docker-compose.yml`
- 原 data、logs、Docker socket 挂载保持实际原路径；保留 host 网络、host PID 与原部署参数。
- 镜像：`isle204/nas-traffic-lens:2026.10.07-2`
- 实际 config ID：`sha256:f970883a6663eff86a15f7ad1a98901e3e3504e748d87ee9eb413ba7e370b5f6`
- 原 Compose、SQLite 全量备份：`/tmp/zfsv3/nvme16/18181998187/data/docker/nas-traffic-lens/upgrade-backups/20261007-165150`
- 回退镜像：`isle204/nas-traffic-lens:rollback-20261007-165150`

验收确认版本正确、容器 running/restartCount=0、认证后 health/settings/overview/Docker API 正常，Go captureReady=true。27 个 Docker 容器可见，flaresolverr 正在运行，保护规则已解除旧锁定且采样正常，原 3 次计数保留。未手动触发真实重启、停止或通知作为测试。

镜像通过离线包加载到 NAS，与 Docker Hub 发布的 amd64 payload 相同。发布及部署资料、摘要证据、备份/回退脚本存于 `artifacts/releases/2026.10.07-2/`（忽略目录）。没有把密码、令牌或私钥写入脚本或发布上下文。

数据保留核对：通知渠道、AI 设置、Docker 自定义配置原值一致；升级前 301484 条网卡历史及 3265239 条进程历史的行数和收发字节汇总一致。
