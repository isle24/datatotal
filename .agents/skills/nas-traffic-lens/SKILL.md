---
name: nas-traffic-lens
description: Use when querying NAS Traffic Lens traffic, containers, system status or alerts, or when explicitly asked to modify monitoring rules or restart a specific container.
---

# NAS Traffic Lens 查询与操作

用随技能提供的 `scripts/ntl.py` 访问用户指定的 NAS Traffic Lens 实例。它使用固定接口，不依赖面板内的 AI 模型。登录可能更新服务端登录计数，查询可能刷新发现缓存。只有用户明确要求修改规则、删除规则或重启指定容器时才执行对应操作；查询或笼统的排查请求不表示授权修改或重启。

## 连接与调用

先从用户给出的地址或已有配置确定服务地址；不要猜测地址或向其他主机发送凭据。设置 `NTL_URL` 或在命令中使用 `--url`，地址仅为服务的 `http(s)://主机:端口`。有登录密码时，交互式终端使用隐藏输入；自动化可通过可信的凭据提供程序经标准输入传入，勿将密码写入命令行、文件、日志或回复。会话 Cookie 只保存在当前进程内。优先使用 HTTPS；HTTP 会在网络上传送明文密码与 Cookie，只在用户认可的可信网络使用。

```bash
python3 /path/to/nas-traffic-lens/scripts/ntl.py --url http://NAS-IP:8088 overview
python3 /path/to/nas-traffic-lens/scripts/ntl.py --url http://NAS-IP:8088 history --period day
python3 /path/to/nas-traffic-lens/scripts/ntl.py --url http://NAS-IP:8088 containers
```

将 `/path/to/nas-traffic-lens` 替换为这个 `SKILL.md` 的目录；若用户已安装 `ntl` 命令，也可直接执行 `ntl --help`。从 `--help` 查看所有参数和命令。结果是 JSON；非零退出码表示调用失败，检查标准错误并如实报告，不能将失败或缺失数据解释为零。

若本机存在 `~/.config/nas-traffic-lens/default.json`，可用 `python3 /path/to/nas-traffic-lens/scripts/ntl_sshbind.py --config "$HOME/.config/nas-traffic-lens/default.json" history --period day` 查询。该可选配置只包含 sshbind 别名、容器名和服务地址，不含凭据；助手确认目标可用且服务主机与 sshbind 目标一致，从容器配置在内存中读取密码，通过标准输入传给查询程序。该方式需要本机 `sshbind` 和远程 Docker 查看权限；分别查询容器时把末尾替换成 `containers`。无配置时按 `ntl_sshbind.py --help` 显式传参，不得获取其他服务器的凭据。

## 查询口径

- 实时上行看 `overview` 的 `summary.wan.txBps`，单位为字节/秒；`summary.wan.txBytes` 是累计值，不是今日值。
- 今日、本周、本月或本年流量用 `history --period day|week|month|year`；今日公网上传为 `totals.wan.txBytes`，单位字节，按服务端所在时区统计。历史记录周期性落库，可能滞后或不完整；结合采集与存储状态，无法确认完整性时说明这一点，不能把空桶或零值直接当作无流量。
- 容器列表用 `containers`，逐项查看 `containers[].state` 和发现状态；单容器资源用 `container-stats`，参数取列表返回的容器 ID。CPU、网络和磁盘 I/O 是采样值或速率，不等同磁盘占用容量。历史、进程与连接数据的可用性取决于采集器状态和保留期限。
- `processes`、`connections` 和告警证据可能包含命令行、地址等私有数据；只读取与问题相关的内容，引用或分享前遵守用户授权。
- `tools` 展示服务端内置只读运维助手的工具目录；该目录不等于公开的独立工具调用接口。此 CLI 不调用模型或写入运维助手审计。

遇到未认证、服务不可达或版本不兼容时，说明实际错误和缺失条件；不要猜测结果、绕过认证或反复尝试密码。

## 修改规则与重启容器

服务端需要支持 Agent 操作接口并开启面板密码。`ntl` 和 `ntl_sshbind.py` 都支持以下子命令，参数放在子命令之后：

- `rules --kind monitor` 或 `rules --kind protection`：读取对应规则和 `revision`。先根据 ID 确定目标，修改已有规则时保留其全部字段，仅改变用户要求的值；阈值的单位以该指标为准，例如每日上传使用字节。
- `rule-put --kind monitor --revision <revision> --rule-json '<完整规则 JSON>' --apply`：新增或替换一条规则；容器保护规则的 kind 为 `protection`。只接受无凭据的规则 JSON。
- `rule-delete --kind monitor --revision <revision> --id <规则ID> --apply`：删除明确指定的规则。`--apply` 表示执行本次已获用户授权的操作；未带该参数不会写入。
- `container-restart <容器ID> --apply`：先用 `containers` 取得用户指定容器的 ID，再使用其 12–64 位小写十六进制 ID。不要以猜测的名称、ID 或模糊匹配代替用户指定目标。

写入后使用返回的 revision 或重新读取规则核对。版本冲突时先重新读取并告知用户已有变更，依据用户意图重新合并；结果未知、连接中断或超时时先核查实际状态，不自动重试。CLI 不执行批量重启或任意命令。
