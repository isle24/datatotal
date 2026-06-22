<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><Activity :size="22" /></div>
        <div>
          <h1>NAS Traffic Lens</h1>
          <p>v{{ overview?.version || settings?.version || "-" }}</p>
        </div>
      </div>
      <nav class="menu">
        <button v-for="item in navItems" :key="item.key" :class="{ active: activeView === item.key }" @click="setView(item.key)">
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ subtitle }}</p>
          <h2>{{ currentTitle }}</h2>
        </div>
        <div class="top-actions">
          <span v-if="toast" class="toast">{{ toast }}</span>
          <button class="icon-button" type="button" :title="theme === 'dark' ? '切换浅色模式' : '切换暗黑模式'" @click="toggleTheme">
            <Sun v-if="theme === 'dark'" :size="18" />
            <Moon v-else :size="18" />
          </button>
          <button class="icon-button" type="button" title="刷新" @click="refreshActive">
            <RefreshCw :size="18" />
          </button>
          <button v-if="overview?.authEnabled" type="button" @click="logout">退出</button>
        </div>
      </header>

      <section v-if="activeView === 'overview'" class="view">
        <div class="metric-grid">
          <MetricCard title="公网实时下行" accent="blue" :value="formatRate(summary.wan?.rxBps)" @click="openConnections({ scope: 'wan', direction: 'rx' })">
            <ArrowDown :size="18" />
          </MetricCard>
          <MetricCard title="公网实时上行" accent="orange" :value="formatRate(summary.wan?.txBps)" @click="openConnections({ scope: 'wan', direction: 'tx' })">
            <ArrowUp :size="18" />
          </MetricCard>
          <MetricCard title="内网实时下行" accent="cyan" :value="formatRate(summary.lan?.rxBps)">
            <ArrowDown :size="18" />
          </MetricCard>
          <MetricCard title="内网实时上行" accent="green" :value="formatRate(summary.lan?.txBps)">
            <ArrowUp :size="18" />
          </MetricCard>
          <MetricCard title="公网 / 总连接数" accent="red" :value="`${connectionSummary.wan || 0} / ${connectionSummary.total || 0}`" @click="openWanConnections">
            <Network :size="18" />
          </MetricCard>
          <MetricCard title="阶段公网" accent="teal" :value="`↓ ${formatBytes(stageWan.rxBytes)} / ↑ ${formatBytes(stageWan.txBytes)}`" wide>
            <Gauge :size="18" />
            <template #footer>
              <span>{{ stageSummary.active ? `运行 ${formatDuration(stageSummary.durationSeconds)}` : "已暂停" }}</span>
              <button type="button" @click.stop="updateStage('reset')">重置</button>
              <button type="button" @click.stop="updateStage(stageSummary.active ? 'stop' : 'resume')">{{ stageSummary.active ? "暂停" : "继续" }}</button>
            </template>
          </MetricCard>
        </div>

        <div class="grid two">
          <section class="card">
            <CardHead title="运行状态" :meta="lastUpdated" />
            <div class="info-grid">
              <InfoItem label="公网累计" :value="`↓ ${formatBytes(summary.wan?.rxBytes)} / ↑ ${formatBytes(summary.wan?.txBytes)}`" />
              <InfoItem label="连接数口径" :value="connectionSourceLabel" />
              <InfoItem label="原始条目" :value="connectionSummary.rawTotal != null ? `${connectionSummary.rawTotal} 条` : '-'" />
              <InfoItem label="活跃网卡" :value="`${summary.interfaces?.up || 0} / ${summary.interfaces?.total || 0}`" />
              <InfoItem label="抓包接口" :value="(overview?.captureInterfaces || []).join('、') || '-'" />
              <button class="info-item clickable" type="button" @click="setView('docker')">
                <span>Docker 发现</span>
                <b>{{ overview?.containerStatus?.enabled ? `启用，${overview?.containerStatus?.containerCount || 0} 个容器 / ${overview?.containerStatus?.count || 0} 个端口` : '关闭' }}</b>
              </button>
            </div>
          </section>
          <section class="card">
            <CardHead title="告警" meta="最近 8 条">
              <button type="button" @click="clearAlerts">清空</button>
            </CardHead>
            <div class="alert-list">
              <div v-for="alert in overview?.alerts || []" :key="alert.id" class="alert-row">
                <Bell :size="16" />
                <div>
                  <strong>{{ alert.message }}</strong>
                  <p>{{ formatDate(alert.timestamp) }} 当前 {{ alert.value }} / 阈值 {{ alert.threshold }}</p>
                </div>
              </div>
              <div v-if="!overview?.alerts?.length" class="empty">暂无告警</div>
            </div>
          </section>
        </div>
      </section>

      <section v-if="activeView === 'interfaces'" class="view">
        <section class="card">
          <CardHead title="网卡实时情况" :meta="captureHint">
            <div class="controls">
              <select v-model="interfaceView" @change="refreshInterfaces">
                <option value="physical">物理/主接口</option>
                <option value="captured">抓包接口</option>
                <option value="all">全部接口</option>
                <option value="virtual">虚拟接口</option>
              </select>
              <select v-model="ifaceFilter">
                <option value="all">全部网卡</option>
                <option v-for="name in interfaceNames" :key="name" :value="name">{{ name }}</option>
              </select>
            </div>
          </CardHead>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>接口</th><th>角色</th><th>状态</th><th>IP / MAC</th><th>实时公网</th><th>公网累计</th><th>实时内网</th><th>系统速率</th><th>系统累计</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="[name, item] in filteredInterfaces" :key="name">
                  <td><strong>{{ name }}</strong><p>{{ item.detail?.note || "-" }}</p></td>
                  <td><span class="pill">{{ item.detail?.role || "未知" }}</span></td>
                  <td><span :class="['status-dot', item.detail?.isUp ? 'up' : 'down']"></span>{{ item.detail?.operstate || "-" }}</td>
                  <td><p>{{ (item.detail?.addresses || []).join(" / ") || "-" }}</p><p>{{ item.detail?.mac || "" }}</p></td>
                  <td>
                    <button class="text-link" type="button" @click="openConnections({ iface: name, scope: 'wan', direction: 'rx' })">↓ {{ formatRate(rateOf(name, 'wan', 'rxBps')) }}</button>
                    <button class="text-link" type="button" @click="openConnections({ iface: name, scope: 'wan', direction: 'tx' })">↑ {{ formatRate(rateOf(name, 'wan', 'txBps')) }}</button>
                  </td>
                  <td>↓ {{ formatBytes(item.scopes?.wan?.rxBytes) }}<br />↑ {{ formatBytes(item.scopes?.wan?.txBytes) }}</td>
                  <td>↓ {{ formatRate(rateOf(name, 'lan', 'rxBps')) }}<br />↑ {{ formatRate(rateOf(name, 'lan', 'txBps')) }}</td>
                  <td>↓ {{ formatRate(snapshot?.rates?.[name]?.systemRxBps) }}<br />↑ {{ formatRate(snapshot?.rates?.[name]?.systemTxBps) }}</td>
                  <td>↓ {{ formatBytes(item.system?.rxBytes) }}<br />↑ {{ formatBytes(item.system?.txBytes) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section v-if="activeView === 'history'" class="view">
        <section class="card">
          <CardHead title="历史统计" meta="公网/内网分色平滑曲线">
            <div class="segmented">
              <button v-for="item in historyPeriods" :key="item.key" type="button" :class="{ active: historyPeriod === item.key }" @click="refreshHistory(item.key)">{{ item.label }}</button>
            </div>
          </CardHead>
          <div class="history-cards">
            <InfoItem label="公网下行" :value="formatBytes(historyTotals.wan?.rxBytes)" />
            <InfoItem label="公网上行" :value="formatBytes(historyTotals.wan?.txBytes)" />
            <InfoItem label="内网下行" :value="formatBytes(historyTotals.lan?.rxBytes)" />
            <InfoItem label="内网上行" :value="formatBytes(historyTotals.lan?.txBytes)" />
          </div>
          <div ref="historyChartEl" class="history-chart"></div>
        </section>
      </section>

      <section v-if="activeView === 'processes'" class="view">
        <section class="card">
          <CardHead title="进程占用" meta="默认显示排行卡片">
            <div class="controls">
              <select v-model="processPeriod" @change="refreshProcesses">
                <option value="30s">30 秒</option><option value="today">当天</option><option value="1d">1 天</option><option value="3d">3 天</option><option value="7d">7 天</option><option value="30d">30 天</option><option value="custom">自定义</option>
              </select>
              <input v-if="processPeriod === 'custom'" v-model="processStart" type="datetime-local" @change="refreshProcesses" />
              <input v-if="processPeriod === 'custom'" v-model="processEnd" type="datetime-local" @change="refreshProcesses" />
              <input v-model="processSearch" type="search" placeholder="筛选进程" />
            </div>
          </CardHead>
          <div class="process-grid">
            <button v-for="item in filteredProcesses" :key="`${item.pid}-${item.name}`" class="process-card" type="button" @click="openConnections({ owner: item.name })">
              <span class="avatar">{{ (item.name || '?').slice(0, 1).toUpperCase() }}</span>
              <strong>{{ item.name || "unknown" }}</strong>
              <p>PID {{ item.pid ?? "-" }} · {{ formatDuration(item.durationSeconds) }}</p>
              <div class="bars">
                <i class="rx" :style="{ width: processBar(item.rxBytes) }"></i>
                <i class="tx" :style="{ width: processBar(item.txBytes) }"></i>
              </div>
              <small>↓ {{ formatBytes(item.rxBytes) }} · ↑ {{ formatBytes(item.txBytes) }}</small>
            </button>
          </div>
        </section>
      </section>

      <section v-if="activeView === 'system'" class="view">
        <div class="metric-grid system-grid">
          <MetricCard title="CPU" accent="blue" :value="`${system?.cpu?.percent ?? 0}%`"><Cpu :size="18" /></MetricCard>
          <MetricCard title="内存" accent="green" :value="`${system?.memory?.percent ?? 0}%`"><Server :size="18" /></MetricCard>
          <MetricCard title="磁盘" accent="orange" :value="`${system?.disk?.percent ?? 0}%`"><HardDrive :size="18" /></MetricCard>
          <MetricCard title="运行时间" accent="teal" :value="formatDuration(system?.uptimeSeconds)"><Monitor :size="18" /></MetricCard>
        </div>
        <div class="grid two">
          <section class="card">
            <CardHead title="硬件详情" :meta="system ? formatDate(system.timestamp) : '-'" />
            <div class="info-grid">
              <InfoItem label="CPU 核心" :value="`${system?.cpu?.countPhysical || '-'} 物理 / ${system?.cpu?.countLogical || '-'} 线程`" />
              <InfoItem label="CPU 频率" :value="system?.cpu?.frequencyMhz ? `${system.cpu.frequencyMhz.toFixed(0)} MHz` : '-'" />
              <InfoItem label="内存" :value="`${formatBytes(system?.memory?.used)} / ${formatBytes(system?.memory?.total)}`" />
              <InfoItem label="Swap" :value="`${formatBytes(system?.swap?.used)} / ${formatBytes(system?.swap?.total)}`" />
              <InfoItem label="磁盘 /" :value="`${formatBytes(system?.disk?.used)} / ${formatBytes(system?.disk?.total)}`" />
              <InfoItem label="GPU" :value="gpuSummary" />
              <InfoItem label="NPU" :value="npuSummary" />
            </div>
          </section>
          <section class="card">
            <CardHead title="温度" meta="psutil / sensors" />
            <div class="temp-grid">
              <div v-for="group in temperatureGroups" :key="group.rawName || group.name" class="temp-card">
                <div class="temp-title">
                  <div>
                    <strong>{{ group.name }}</strong>
                    <span>{{ group.rawName }}</span>
                  </div>
                  <b>{{ formatTemperature(maxTemperature(group)) }}</b>
                </div>
                <div class="temp-readings">
                  <p v-for="item in group.items" :key="`${group.rawName}-${item.rawLabel}`">
                    <span>{{ item.label }}</span>
                    <b :class="['temp-value', item.level]">{{ formatTemperature(item.current) }}</b>
                  </p>
                </div>
              </div>
              <div v-if="!temperatureGroups.length" class="empty">当前环境未暴露温度传感器</div>
            </div>
          </section>
        </div>
      </section>

      <section v-if="activeView === 'docker'" class="view">
        <section class="card">
          <CardHead title="Docker 容器" :meta="dockerStatusText">
            <input v-model="dockerSearch" class="search-input" type="search" placeholder="搜索容器、镜像、端口、备注" />
            <button type="button" @click="refreshDocker"><RefreshCw :size="16" />刷新</button>
          </CardHead>
          <div class="docker-grid">
            <div v-for="container in dockerContainers" :key="container.id || container.name" class="docker-card">
              <div class="docker-title">
                <div class="docker-icon">
                  <img v-if="container.containerIcon" :src="container.containerIcon" alt="" />
                  <Server v-else :size="22" />
                </div>
                <div>
                  <strong>{{ container.name }}</strong>
                  <p>{{ container.image }}</p>
                </div>
                <span :class="['pill', container.state === 'running' ? 'ok' : '']">{{ container.state || "-" }}</span>
              </div>
              <p class="docker-status">{{ container.status || "-" }} · 网络 {{ container.networkMode || "-" }}</p>
              <div v-if="container.showStats" class="docker-stats">
                <span>CPU {{ formatPercent(container.stats?.cpuPercent) }}</span>
                <span>内存 {{ formatBytes(container.stats?.memoryUsedBytes) }}</span>
                <span>↓ {{ formatBytes(container.stats?.netRxBytes) }} / ↑ {{ formatBytes(container.stats?.netTxBytes) }}</span>
              </div>
              <button v-else type="button" class="subtle-button" @click="showDockerStats(container)"><Gauge :size="15" />显示占用</button>
              <div class="port-list">
                <div v-for="port in container.ports" :key="`${port.proto}-${port.hostPort}`" class="port-row">
                  <div>
                    <strong>{{ port.hostPort }} → {{ port.containerPort }}/{{ port.proto }}</strong>
                    <p>{{ serviceLabel(port.service) }} · {{ port.label || "未备注" }}</p>
                  </div>
                  <span :class="['pill', port.accessMode === 'web' ? 'ok' : '']">{{ port.accessMode === "web" ? "Web" : "非 Web" }}</span>
                  <button v-if="port.accessMode === 'web'" type="button" title="打开 Web 端口" @click="openContainerPort(port)"><ExternalLink :size="15" />打开</button>
                  <button v-else-if="port.accessMode !== 'hidden'" type="button" title="复制连接地址" @click="copyContainerPort(port)"><Copy :size="15" />复制</button>
                  <button v-if="port.accessMode !== 'web' && port.accessMode !== 'hidden' && port.proto === 'tcp'" type="button" title="探测是否为 Web 服务" @click="probeContainerPort(container, port)"><ExternalLink :size="15" />探测</button>
                  <span v-if="port.accessMode === 'hidden'" class="muted">已隐藏</span>
                </div>
                <button v-if="!container.portsLoaded" type="button" class="subtle-button" @click="loadDockerDetail(container)"><RefreshCw :size="15" />加载端口</button>
                <div v-else-if="!container.ports?.length" class="empty compact">未发现映射端口；host 模式容器可手动添加</div>
              </div>
              <div class="edit-actions">
                <button type="button" @click="openConnections({ owner: container.name })"><Network :size="16" />连接</button>
                <button type="button" @click="editDockerContainer(container)"><Pencil :size="16" />端口/图标</button>
              </div>
            </div>
            <div v-if="!dockerContainers.length" class="empty">暂无 Docker 容器数据；确认已映射 Docker socket 并启用 ENABLE_DOCKER_DISCOVERY，或先保存手动端口配置</div>
          </div>
        </section>
      </section>

      <section v-if="activeView === 'settings'" class="view">
        <div class="grid two">
          <section class="card">
            <CardHead title="运行参数" meta="可热更新项会写入 SQLite">
              <button type="button" @click="saveRuntime"><Save :size="16" />保存</button>
            </CardHead>
            <div class="form-grid">
              <label>采样间隔秒<input v-model.number="runtimeForm.sampleSeconds" type="number" min="0.5" step="0.5" /></label>
              <label>内存保留秒<input v-model.number="runtimeForm.retentionSeconds" type="number" min="60" /></label>
              <label>持久化间隔秒<input v-model.number="runtimeForm.persistIntervalSeconds" type="number" min="10" /></label>
              <label>历史保留天<input v-model.number="runtimeForm.historyRetentionDays" type="number" min="1" /></label>
              <label>活跃连接窗口秒<input v-model.number="runtimeForm.connectionActiveSeconds" type="number" min="10" /></label>
              <label>连接缓存秒<input v-model.number="runtimeForm.connectionRetentionSeconds" type="number" min="60" /></label>
              <label>Conntrack 刷新秒<input v-model.number="runtimeForm.conntrackRefreshSeconds" type="number" min="2" /></label>
              <label class="check"><input v-model="runtimeForm.autoStartStage" type="checkbox" /> 阶段公网默认统计</label>
            </div>
          </section>

          <section class="card">
            <CardHead title="启动期参数" meta="修改后需重启容器" />
            <div class="info-grid">
              <InfoItem label="端口" :value="settings?.runtime?.appPort" />
              <InfoItem label="数据库" :value="settings?.runtime?.dbPath" />
              <InfoItem label="日志目录" :value="settings?.runtime?.logDir" />
              <InfoItem label="Docker 发现" :value="settings?.runtime?.dockerDiscovery ? '启用' : '关闭'" />
              <InfoItem label="抓包接口" :value="(settings?.runtime?.captureInterfaces || []).join('、') || '-'" />
              <InfoItem label="版本" :value="settings?.version" />
            </div>
          </section>
        </div>

        <section class="card">
          <CardHead title="监控规则" meta="支持多规则多渠道">
            <button type="button" @click="addRule"><Plus :size="16" />新增</button>
            <button type="button" @click="saveRules"><Save :size="16" />保存</button>
          </CardHead>
          <div class="rule-grid">
            <div v-for="rule in monitorRules" :key="rule.id" class="edit-card">
              <div class="edit-title">
                <input v-model="rule.name" />
                <label class="switch"><input v-model="rule.enabled" type="checkbox" />启用</label>
              </div>
              <div class="form-grid mini">
                <label>指标<select v-model="rule.metric"><option v-for="(label, key) in metricLabels" :key="key" :value="key">{{ label }}</option></select></label>
                <label>阈值<input v-model.number="rule.threshold" type="number" min="0" /></label>
                <label>持续秒<input v-model.number="rule.durationSeconds" type="number" min="0" /></label>
                <div class="field-block">
                  <span>渠道</span>
                  <div class="channel-checks">
                    <label v-for="channel in channels" :key="channel.id" class="check-chip">
                      <input :checked="rule.channelIds?.includes(channel.id)" type="checkbox" @change="toggleRuleChannel(rule, channel.id)" />
                      {{ channel.name }}
                    </label>
                  </div>
                </div>
              </div>
              <button class="danger" type="button" @click="removeRule(rule.id)"><Trash2 :size="16" />删除</button>
            </div>
          </div>
        </section>

        <section class="card">
          <CardHead title="通知渠道" meta="Webhook / IYUU / MeoW">
            <button type="button" @click="addChannel"><Plus :size="16" />新增</button>
            <button type="button" @click="saveChannels"><Save :size="16" />保存</button>
          </CardHead>
          <div class="channel-grid">
            <div v-for="channel in channels" :key="channel.id" class="edit-card channel-card">
              <div class="edit-title">
                <input v-model="channel.name" />
                <label class="switch"><input v-model="channel.enabled" type="checkbox" />启用</label>
              </div>
              <div class="form-grid mini">
                <label>类型<select v-model="channel.type"><option value="webhook">Webhook</option><option value="iyuu">IYUU</option><option value="meow">MeoW</option></select></label>
                <label>URL<input v-model="channel.url" type="url" placeholder="Webhook 可填；IYUU/MeoW 可留空" /></label>
                <label>Token / 昵称<input v-model="channel.token" placeholder="IYUU token 或 MeoW 昵称" /></label>
                <label>超时秒<input v-model.number="channel.timeout" type="number" min="1" max="30" /></label>
                <label>消息类型<select v-model="channel.msgType"><option value="text">text</option><option value="html">html</option></select></label>
                <label>HTML 高度<input v-model.number="channel.htmlHeight" type="number" min="100" max="1200" /></label>
                <label>跳转 URL 模板<input v-model="channel.urlTemplate" placeholder="可用 {rule_id} 等变量" /></label>
              </div>
              <div class="template-help">
                可用变量：<code v-for="name in templateVariables" :key="name">{{ templateVar(name) }}</code>
              </div>
              <label class="textarea-label">标题模板<textarea v-model="channel.titleTemplate" rows="2"></textarea></label>
              <label class="textarea-label">正文模板<textarea v-model="channel.bodyTemplate" rows="5"></textarea></label>
              <div class="edit-actions">
                <button type="button" @click="testChannel(channel.id)"><Send :size="16" />测试</button>
                <button class="danger" type="button" @click="removeChannel(channel.id)"><Trash2 :size="16" />删除</button>
              </div>
            </div>
          </div>
        </section>
      </section>
    </main>

    <dialog ref="connectionDialog" class="modal" @close="stopConnectionTimer">
      <div class="modal-box">
        <CardHead title="连接与端口" :meta="`${connPagination.total || 0} 条筛选结果`">
          <button type="button" @click="connectionDialog?.close()"><X :size="16" />关闭</button>
        </CardHead>
        <div class="connection-filters">
          <select v-model="connFilters.mode" @change="refreshConnections(true)"><option value="capture">抓包归因</option><option value="conntrack">路由器口径</option></select>
          <select v-model="connFilters.iface" @change="refreshConnections(true)"><option value="all">全部网卡</option><option v-for="name in interfaceNames" :key="name" :value="name">{{ name }}</option></select>
          <select v-model="connFilters.scope" @change="refreshConnections(true)"><option value="all">全部范围</option><option value="wan">公网</option><option value="lan">内网</option></select>
          <select v-model="connFilters.proto" @change="refreshConnections(true)"><option value="all">全部协议</option><option value="tcp">TCP</option><option value="udp">UDP</option></select>
          <select v-model="connFilters.direction" @change="refreshConnections(true)"><option value="all">全部方向</option><option value="rx">下行</option><option value="tx">上行</option></select>
          <input v-model="connFilters.source" placeholder="源 IP/端口" @input="debounceConnections" />
          <input v-model="connFilters.dest" placeholder="目标 IP/端口" @input="debounceConnections" />
          <input v-model="connFilters.owner" placeholder="进程/容器" @input="debounceConnections" />
          <input v-model.number="connFilters.minBytes" type="number" min="0" placeholder="最小 MB" @input="debounceConnections" />
          <input v-model.number="connFilters.minDuration" type="number" min="0" placeholder="最小秒" @input="debounceConnections" />
          <button type="button" @click="refreshConnections(false)"><RefreshCw :size="16" />刷新</button>
        </div>
        <div class="table-wrap modal-table" :class="{ loading: connLoading }">
          <table>
            <thead><tr><th>网卡</th><th>范围</th><th>协议</th><th>流量</th><th>源</th><th>目标</th><th>归属</th><th>下行</th><th>上行</th><th>时长</th><th>备注</th></tr></thead>
            <tbody>
              <tr v-for="item in connections" :key="`${item.iface}-${item.proto}-${item.source}-${item.dest}-${item.process?.pid}`">
                <td>{{ item.iface || "-" }}</td>
                <td><span class="pill">{{ item.scope === "lan" ? "内网" : "公网" }}</span></td>
                <td>{{ item.proto }}</td>
                <td>↓ {{ formatBytes(item.rxBytes) }}<br />↑ {{ formatBytes(item.txBytes) }}</td>
                <td>{{ item.source }}</td>
                <td>{{ item.dest }}</td>
                <td><strong>{{ item.process?.container?.label || item.process?.container?.name || item.process?.name || "unknown" }}</strong><p>PID {{ item.process?.pid ?? "-" }}</p></td>
                <td>{{ formatBytes(item.rxBytes) }}</td>
                <td>{{ formatBytes(item.txBytes) }}</td>
                <td>{{ formatDuration(item.durationSeconds) }}</td>
                <td><button v-if="item.process?.container?.labelKey" type="button" @click="editLabel(item.process.container.labelKey, item.process.container.label)">备注</button><span v-else>-</span></td>
              </tr>
              <tr v-if="!connections.length"><td colspan="11" class="empty">暂无连接数据</td></tr>
            </tbody>
          </table>
        </div>
        <div class="pager">
          <button type="button" :disabled="connOffset <= 0" @click="pageConnections(-1)">上一页</button>
          <span>{{ connPagination.page || 1 }} / {{ connPagination.pages || 1 }}</span>
          <button type="button" :disabled="(connPagination.page || 1) >= (connPagination.pages || 1)" @click="pageConnections(1)">下一页</button>
        </div>
      </div>
    </dialog>

    <dialog ref="dockerEditDialog" class="modal narrow">
      <div class="modal-box">
        <CardHead title="容器端口与图标" :meta="dockerEditor.name || '-'">
          <button type="button" @click="dockerEditDialog?.close()"><X :size="16" />关闭</button>
        </CardHead>
        <div class="docker-editor">
          <div class="icon-editor">
            <div class="docker-icon large">
              <img v-if="dockerEditor.icon" :src="dockerEditor.icon" alt="" />
              <Server v-else :size="28" />
            </div>
            <label class="file-button">
              <ImagePlus :size="16" />上传图标
              <input type="file" accept="image/png,image/jpeg,image/webp" @change="uploadDockerIcon" />
            </label>
            <button type="button" @click="dockerEditor.icon = ''">清除</button>
          </div>
          <div class="port-editor-list">
            <div v-for="(port, index) in dockerEditor.ports" :key="index" class="port-editor">
              <label>协议<select v-model="port.proto"><option value="tcp">TCP</option><option value="udp">UDP</option></select></label>
              <label>宿主端口<input v-model.number="port.hostPort" type="number" min="1" max="65535" /></label>
              <label>容器端口<input v-model.number="port.containerPort" type="number" min="1" max="65535" /></label>
              <label>服务类型<input v-model="port.service" placeholder="redis / mysql / web" /></label>
              <label>访问方式<select v-model="port.accessMode"><option value="copy">复制地址</option><option value="web">Web 打开</option><option value="hidden">隐藏快捷操作</option></select></label>
              <label>协议<select v-model="port.scheme"><option value="http">http</option><option value="https">https</option></select></label>
              <label>路径<input v-model="port.path" placeholder="/ 或 /admin" /></label>
              <label>备注<input v-model="port.label" placeholder="如 Redis、QB 管理页" /></label>
              <button class="danger" type="button" @click="removeDockerPort(index)"><Trash2 :size="16" />删除</button>
            </div>
          </div>
          <div class="edit-actions">
            <button type="button" @click="addDockerPort"><Plus :size="16" />添加端口</button>
            <button type="button" @click="saveDockerPorts"><Save :size="16" />保存</button>
          </div>
        </div>
      </div>
    </dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  Bell,
  Copy,
  Cpu,
  Database,
  ExternalLink,
  Gauge,
  HardDrive,
  History,
  ImagePlus,
  Moon,
  Monitor,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Send,
  Server,
  Settings,
  Sun,
  Trash2,
  X,
} from "@lucide/vue";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const MetricCard = defineComponent({
  props: { title: String, value: String, accent: String, wide: Boolean },
  emits: ["click"],
  setup(props, { slots, emit }) {
    return () =>
      h("button", { class: ["metric-card", `accent-${props.accent || "blue"}`, props.wide ? "wide" : ""], type: "button", onClick: () => emit("click") }, [
        h("span", { class: "metric-icon" }, slots.default?.()),
        h("span", { class: "metric-title" }, props.title),
        h("strong", props.value || "-"),
        slots.footer ? h("div", { class: "metric-footer" }, slots.footer()) : null,
      ]);
  },
});

const CardHead = defineComponent({
  props: { title: String, meta: String },
  setup(props, { slots }) {
    return () => h("div", { class: "card-head" }, [h("div", [h("h3", props.title), props.meta ? h("p", props.meta) : null]), h("div", { class: "card-actions" }, slots.default?.())]);
  },
});

const InfoItem = defineComponent({
  props: { label: String, value: [String, Number] },
  setup(props) {
    return () => h("div", { class: "info-item" }, [h("span", props.label), h("b", props.value ?? "-")]);
  },
});

const navItems = [
  { key: "overview", label: "概览", icon: Activity },
  { key: "interfaces", label: "网卡", icon: Network },
  { key: "history", label: "历史", icon: History },
  { key: "processes", label: "进程", icon: Database },
  { key: "system", label: "系统", icon: Cpu },
  { key: "docker", label: "Docker", icon: Server },
  { key: "settings", label: "监控中心", icon: Settings },
];
const metricLabels = {
  wan_tx_bps: "公网上传速率",
  wan_rx_bps: "公网下载速率",
  lan_tx_bps: "内网上传速率",
  lan_rx_bps: "内网下载速率",
  wan_connections: "公网连接数",
  total_connections: "总连接数",
  stage_wan_tx_bytes: "阶段公网上传总量",
  daily_wan_tx_bytes: "每日公网上传总量",
};
const templateVariables = ["app", "version", "channel_id", "channel_name", "channel_type", "alert_id", "rule_id", "rule_name", "message", "severity", "value", "threshold", "timestamp", "iso_time"];
const historyPeriods = [
  { key: "day", label: "今日" },
  { key: "week", label: "本周" },
  { key: "month", label: "本月" },
  { key: "year", label: "今年" },
];

const activeView = ref("overview");
const toast = ref("");
const theme = ref(localStorage.getItem("ntl-theme") || (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
const overview = ref(null);
const snapshot = ref(null);
const settings = ref(null);
const system = ref(null);
const dockerData = ref({ enabled: false, status: {}, containers: [] });
const historyData = ref({ buckets: [], totals: {} });
const processes = ref([]);
const connections = ref([]);
const connPagination = ref({ total: 0, page: 1, pages: 1 });
const connOffset = ref(0);
const connLimit = 80;
const connLoading = ref(false);
const interfaceView = ref("physical");
const ifaceFilter = ref("all");
const historyPeriod = ref("day");
const processPeriod = ref("30s");
const processStart = ref("");
const processEnd = ref("");
const processSearch = ref("");
const dockerSearch = ref("");
const monitorRules = ref([]);
const channels = ref([]);
const runtimeForm = reactive({});
const historyChartEl = ref(null);
const connectionDialog = ref(null);
const dockerEditDialog = ref(null);
const dockerEditor = reactive({ id: "", name: "", icon: "", ports: [] });
let historyChart = null;
let overviewTimer = null;
let processTimer = null;
let systemTimer = null;
let connectionTimer = null;
let dockerTimer = null;
let connectionDebounce = null;
let dockerHydrateToken = 0;
let overviewLoading = false;
let interfaceLoading = false;
let processLoading = false;
let systemLoading = false;
let dockerLoading = false;
let connectionLoading = false;
const handleResize = () => historyChart?.resize();

const connFilters = reactive({ mode: "capture", iface: "all", scope: "all", proto: "all", direction: "all", owner: "", source: "", dest: "", minBytes: null, minDuration: null });

const currentTitle = computed(() => navItems.find((item) => item.key === activeView.value)?.label || "概览");
const subtitle = computed(() => (overview.value?.timestamp ? `版本 ${overview.value.version || "-"} · ${formatDate(overview.value.timestamp)}` : "正在连接采集器..."));
const summary = computed(() => overview.value?.summary || {});
const stageSummary = computed(() => overview.value?.stageSummary || {});
const stageWan = computed(() => stageSummary.value.wan || {});
const connectionSummary = computed(() => overview.value?.connectionSummary || {});
const lastUpdated = computed(() => (overview.value?.timestamp ? new Date(overview.value.timestamp * 1000).toLocaleTimeString() : "-"));
const connectionSourceLabel = computed(() => {
  const source = connectionSummary.value.source;
  if (source === "conntrack") return `系统 conntrack (${connectionSummary.value.countMode || "active"})`;
  if (source === "socket") return "宿主机 socket";
  return "抓包活跃连接";
});
const captureHint = computed(() => `抓包接口：${(snapshot.value?.captureInterfaces || overview.value?.captureInterfaces || []).join("、") || "-"}`);
const interfaceNames = computed(() => Object.keys(snapshot.value?.interfaces || {}).sort());
const filteredInterfaces = computed(() => Object.entries(snapshot.value?.interfaces || {}).filter(([name]) => ifaceFilter.value === "all" || name === ifaceFilter.value));
const historyTotals = computed(() => historyData.value?.totals || {});
const dockerContainers = computed(() => {
  const keyword = dockerSearch.value.trim().toLowerCase();
  return (dockerData.value?.containers || []).filter((container) => {
    if (!keyword) return true;
    const portText = (container.ports || []).map((port) => `${port.hostPort} ${port.containerPort} ${port.proto} ${port.label} ${port.service}`).join(" ");
    return `${container.name} ${container.image} ${container.state} ${container.status} ${container.networkMode} ${portText}`.toLowerCase().includes(keyword);
  });
});
const dockerStatusText = computed(() => {
  const status = dockerData.value?.status || {};
  const suffix = dockerSearch.value ? `，筛选 ${dockerContainers.value.length} 个` : "";
  if (!dockerData.value?.enabled) return `Docker 发现未启用${suffix}`;
  return `${status.containerCount || dockerData.value?.containers?.length || 0} 个容器，${status.count || 0} 个端口${suffix}`;
});
const temperatureGroups = computed(() => system.value?.temperatureGroups || []);
const gpuSummary = computed(() => {
  const gpus = system.value?.gpu || [];
  if (!gpus.length) return "未检测到或未映射 /dev/dri";
  return gpus.map((gpu) => {
    if (gpu.type === "dri" && gpu.utilPercent != null) return `${gpu.name} ${gpu.utilPercent}%`;
    if (gpu.type === "dri") return `${gpu.name} 已映射，未暴露利用率`;
    return `${gpu.name} ${gpu.utilPercent ?? "-"}%`;
  }).join(" / ");
});
const npuSummary = computed(() => {
  const npus = system.value?.npu || [];
  if (!npus.length) return "未检测到或未映射 /dev/accel";
  return npus.map((npu) => `${npu.name || "NPU"} ${npu.status || "可用"}`).join(" / ");
});
const filteredProcesses = computed(() => {
  const keyword = processSearch.value.trim().toLowerCase();
  return (processes.value || []).filter((item) => !keyword || `${item.name} ${item.pid} ${item.cmdline}`.toLowerCase().includes(keyword)).slice(0, 30);
});
const processMax = computed(() => Math.max(1, ...filteredProcesses.value.map((item) => Math.max(item.rxBytes || 0, item.txBytes || 0))));

function formatBytes(value) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Math.max(0, Number(value || 0));
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}
const formatRate = (value) => `${formatBytes(value)}/s`;
function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${sec}s`;
  return `${sec}s`;
}
function formatDate(ts) {
  return ts ? new Date(ts * 1000).toLocaleString() : "-";
}
function formatPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(number >= 10 ? 0 : 1)}%` : "-";
}
function formatTemperature(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(1)}°C` : "-";
}
function maxTemperature(group) {
  const values = (group?.items || []).map((item) => Number(item.current)).filter((value) => Number.isFinite(value));
  return values.length ? Math.max(...values) : null;
}
function processBar(value) {
  return `${Math.max(3, ((value || 0) / processMax.value) * 100)}%`;
}
function templateVar(name) {
  return `{${name}}`;
}
function serviceLabel(value) {
  const labels = {
    web: "Web",
    redis: "Redis",
    mysql: "MySQL",
    postgresql: "PostgreSQL",
    mongodb: "MongoDB",
    memcached: "Memcached",
    mqtt: "MQTT",
    ssh: "SSH",
    ftp: "FTP",
    smb: "SMB",
    nfs: "NFS",
    rdp: "RDP",
    vnc: "VNC",
    dns: "DNS",
    unknown: "未知服务",
  };
  return labels[value] || value || "未知服务";
}
function rateOf(name, scope, key) {
  return snapshot.value?.rates?.[name]?.scopes?.[scope]?.[key] || 0;
}
async function readJson(response) {
  if (response.status === 401) {
    location.href = "/login";
    throw new Error("authentication required");
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(data?.detail || response.statusText || "请求失败");
  return data;
}
async function api(url, options) {
  return readJson(await fetch(url, { cache: "no-store", ...options }));
}
async function refreshOverview() {
  if (overviewLoading) return;
  overviewLoading = true;
  try {
  overview.value = await api(`/api/overview?interfaces=${encodeURIComponent(interfaceView.value)}`);
  } finally {
    overviewLoading = false;
  }
}
async function refreshInterfaces() {
  if (interfaceLoading) return;
  interfaceLoading = true;
  try {
  snapshot.value = await api(`/api/snapshot?interfaces=${encodeURIComponent(interfaceView.value)}`);
  } finally {
    interfaceLoading = false;
  }
}
async function refreshHistory(period = historyPeriod.value) {
  historyPeriod.value = period;
  historyData.value = await api(`/api/history?period=${encodeURIComponent(period)}`);
  await nextTick();
  renderHistoryChart();
}
async function refreshProcesses() {
  if (processLoading) return;
  processLoading = true;
  try {
  const params = new URLSearchParams({ period: processPeriod.value, limit: "30" });
  if (processPeriod.value === "custom") {
    if (processStart.value) params.set("start", Math.floor(new Date(processStart.value).getTime() / 1000));
    if (processEnd.value) params.set("end", Math.floor(new Date(processEnd.value).getTime() / 1000));
  }
  processes.value = (await api(`/api/processes?${params.toString()}`)).processes || [];
  } finally {
    processLoading = false;
  }
}
async function refreshSettings() {
  settings.value = await api("/api/settings");
  monitorRules.value = JSON.parse(JSON.stringify(settings.value.monitor?.rules || []));
  channels.value = JSON.parse(JSON.stringify(settings.value.monitor?.channels || []));
  Object.assign(runtimeForm, settings.value.runtime || {});
}
async function refreshSystem() {
  if (systemLoading) return;
  systemLoading = true;
  try {
  system.value = await api("/api/system");
  } finally {
    systemLoading = false;
  }
}
async function refreshDocker() {
  if (dockerLoading) return;
  dockerLoading = true;
  try {
  const data = await api("/api/docker/containers");
  dockerData.value = { ...data, containers: mergeDockerContainers(data.containers || []) };
  hydrateDockerDetails();
  } finally {
    dockerLoading = false;
  }
}
function dockerKey(container) {
  return container?.id || container?.name || "";
}
function normalizeDockerContainer(container = {}, previous = {}) {
  const keepPorts = Array.isArray(previous.ports) ? previous.ports : [];
  return {
    ...previous,
    ...container,
    ports: Array.isArray(container.ports) ? container.ports : keepPorts,
    portsLoaded: Array.isArray(container.ports) ? true : Boolean(previous.portsLoaded),
    containerIcon: container.containerIcon || previous.containerIcon || "",
    showStats: Boolean(previous.showStats),
    stats: previous.stats || null,
    statsLoading: false,
  };
}
function mergeDockerContainers(items) {
  const previous = new Map((dockerData.value?.containers || []).map((container) => [dockerKey(container), container]));
  return items.map((container) => normalizeDockerContainer(container, previous.get(dockerKey(container)) || {}));
}
function replaceDockerContainer(container) {
  const key = dockerKey(container);
  dockerData.value = {
    ...dockerData.value,
    containers: (dockerData.value?.containers || []).map((item) => (dockerKey(item) === key ? normalizeDockerContainer(container, item) : item)),
  };
}
async function loadDockerDetail(container) {
  if (!container?.id && !container?.name) return null;
  const key = encodeURIComponent(container.id || container.name);
  const data = await api(`/api/docker/containers/${key}`);
  if (data?.container) {
    replaceDockerContainer({ ...data.container, portsLoaded: true });
    return data.container;
  }
  return null;
}
async function hydrateDockerDetails() {
  const token = ++dockerHydrateToken;
  const targets = (dockerData.value?.containers || []).filter((container) => !container.portsLoaded);
  for (const container of targets) {
    if (token !== dockerHydrateToken || activeView.value !== "docker") return;
    try {
      await loadDockerDetail(container);
    } catch (error) {
      console.warn("load docker detail failed", error);
    }
  }
}
async function showDockerStats(container) {
  container.showStats = true;
  await refreshDockerStats(container);
}
async function refreshDockerStats(container) {
  if (!container?.id) return;
  const key = encodeURIComponent(container.id);
  const data = await api(`/api/docker/containers/${key}/stats`);
  container.stats = data.stats || {};
}
async function probeContainerPort(container, port) {
  const result = await api("/api/docker/ports/probe", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ port: port.hostPort, path: port.path || "/", refresh: true }),
  });
  if (result.isWeb) {
    port.accessMode = "web";
    port.scheme = result.scheme || port.scheme || "http";
    showToast(`已识别为 Web：${port.scheme}://${location.hostname}:${port.hostPort}`);
  } else {
    port.accessMode = "copy";
    showToast("探测完成：看起来不是 Web 服务");
  }
  await saveDockerPortsFor(container);
}
async function refreshVisibleDockerStats() {
  if (activeView.value !== "docker") return;
  const targets = (dockerData.value?.containers || []).filter((container) => container.showStats && container.id);
  for (const container of targets) {
    try {
      await refreshDockerStats(container);
    } catch (error) {
      console.warn("refresh docker stats failed", error);
    }
  }
}
async function refreshConnections(resetPage = false) {
  if (connectionLoading) return;
  if (resetPage) connOffset.value = 0;
  connLoading.value = true;
  connectionLoading = true;
  try {
    const params = new URLSearchParams({
      mode: connFilters.mode,
      interfaces: interfaceView.value,
      iface: connFilters.iface,
      scope: connFilters.scope,
      proto: connFilters.proto,
      direction: connFilters.direction,
      owner: connFilters.owner || "",
      source: connFilters.source || "",
      dest: connFilters.dest || "",
      min_bytes: String(Math.max(0, Number(connFilters.minBytes || 0)) * 1024 * 1024),
      min_duration: String(Math.max(0, Number(connFilters.minDuration || 0))),
      limit: String(connLimit),
      offset: String(connOffset.value),
    });
    const data = await api(`/api/connections?${params.toString()}`);
    connections.value = data.connections || [];
    connPagination.value = data.pagination || {};
  } finally {
    connLoading.value = false;
    connectionLoading = false;
  }
}
function renderHistoryChart() {
  if (!historyChartEl.value) return;
  if (historyChart && historyChart.getDom() !== historyChartEl.value) {
    historyChart.dispose();
    historyChart = null;
  }
  if (!historyChart) historyChart = echarts.init(historyChartEl.value);
  const buckets = historyData.value?.buckets || [];
  historyChart.setOption({
    color: ["#2f80ed", "#f2994a", "#00a8c8", "#27ae60"],
    tooltip: { trigger: "axis", valueFormatter: (value) => formatBytes(value) },
    legend: { top: 8, textStyle: { color: theme.value === "dark" ? "#cbd5e1" : "#475569" } },
    grid: { left: 52, right: 24, top: 52, bottom: 36 },
    xAxis: { type: "category", boundaryGap: false, data: buckets.map((item) => item.label), axisLine: { lineStyle: { color: "#94a3b8" } } },
    yAxis: { type: "value", axisLabel: { formatter: (value) => formatBytes(value) }, splitLine: { lineStyle: { color: theme.value === "dark" ? "#273244" : "#e2e8f0" } } },
    series: [
      { name: "公网下行", type: "line", smooth: true, areaStyle: { opacity: 0.08 }, data: buckets.map((item) => item.wan?.rxBytes || 0) },
      { name: "公网上行", type: "line", smooth: true, areaStyle: { opacity: 0.08 }, data: buckets.map((item) => item.wan?.txBytes || 0) },
      { name: "内网下行", type: "line", smooth: true, areaStyle: { opacity: 0.05 }, data: buckets.map((item) => item.lan?.rxBytes || 0) },
      { name: "内网上行", type: "line", smooth: true, areaStyle: { opacity: 0.05 }, data: buckets.map((item) => item.lan?.txBytes || 0) },
    ],
  }, true);
  requestAnimationFrame(() => historyChart?.resize());
}
function setView(view) {
  if (activeView.value === "history" && view !== "history" && historyChart) {
    historyChart.dispose();
    historyChart = null;
  }
  if (view !== "docker") stopDockerTimer();
  activeView.value = view;
  refreshActive();
  if (view === "docker") startDockerTimer();
}
function refreshActive() {
  if (activeView.value === "overview") refreshOverview();
  if (activeView.value === "interfaces") refreshInterfaces();
  if (activeView.value === "history") refreshHistory();
  if (activeView.value === "processes") refreshProcesses();
  if (activeView.value === "settings") refreshSettings();
  if (activeView.value === "system") refreshSystem();
  if (activeView.value === "docker") refreshDocker();
}
function startDockerTimer() {
  stopDockerTimer();
  dockerTimer = setInterval(() => {
    if (activeView.value !== "docker") return;
    refreshVisibleDockerStats();
  }, 5000);
}
function stopDockerTimer() {
  dockerHydrateToken += 1;
  if (dockerTimer) clearInterval(dockerTimer);
  dockerTimer = null;
}
function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}
function openConnections(options = {}) {
  Object.assign(connFilters, { mode: "capture", iface: options.iface || "all", scope: options.scope || "all", direction: options.direction || "all", owner: options.owner || "", source: "", dest: "" });
  connOffset.value = 0;
  if (!connectionDialog.value.open) connectionDialog.value.showModal();
  refreshConnections();
  startConnectionTimer();
}
function openWanConnections() {
  Object.assign(connFilters, { mode: "conntrack", iface: "all", scope: "wan", direction: "all", owner: "", source: "", dest: "" });
  connOffset.value = 0;
  if (!connectionDialog.value.open) connectionDialog.value.showModal();
  refreshConnections();
  startConnectionTimer();
}
function startConnectionTimer() {
  stopConnectionTimer();
  connectionTimer = setInterval(() => refreshConnections(false), 5000);
}
function stopConnectionTimer() {
  if (connectionTimer) clearInterval(connectionTimer);
  connectionTimer = null;
}
function debounceConnections() {
  if (connectionDebounce) clearTimeout(connectionDebounce);
  connectionDebounce = setTimeout(() => refreshConnections(true), 300);
}
function pageConnections(direction) {
  connOffset.value = Math.max(0, connOffset.value + direction * connLimit);
  refreshConnections(false);
}
async function updateStage(action) {
  await api(`/api/stage/${action}?interfaces=${encodeURIComponent(interfaceView.value)}`, { method: "POST" });
  refreshOverview();
}
async function clearAlerts() {
  await api("/api/alerts/clear", { method: "POST" });
  refreshOverview();
}
async function saveRuntime() {
  settings.value = await api("/api/settings/runtime", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(runtimeForm) });
  Object.assign(runtimeForm, settings.value.runtime || {});
  showToast("运行参数已保存");
}
async function saveRules() {
  settings.value = await api("/api/settings/monitor", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rules: monitorRules.value }) });
  await refreshSettings();
  showToast("监控规则已保存");
}
async function saveChannels() {
  settings.value = await api("/api/settings/channels", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ channels: channels.value }) });
  await refreshSettings();
  showToast("通知渠道已保存");
}
async function testChannel(channelId) {
  await saveChannels();
  const result = await api("/api/notifications/test", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ channelId }) });
  showToast(result.ok ? "测试通知已发送" : `测试失败：${result.detail || result.body || "未知错误"}`);
}
function addRule() {
  monitorRules.value.push({ id: `rule-${Date.now()}`, name: "新监控规则", metric: "wan_tx_bps", operator: "gte", threshold: 0, durationSeconds: 0, scope: "wan", direction: "tx", window: "realtime", enabled: false, channelIds: [] });
}
function removeRule(id) {
  monitorRules.value = monitorRules.value.filter((item) => item.id !== id);
}
function toggleRuleChannel(rule, channelId) {
  const values = new Set(rule.channelIds || []);
  if (values.has(channelId)) values.delete(channelId);
  else values.add(channelId);
  rule.channelIds = Array.from(values);
}
function addChannel() {
  channels.value.push({ id: `channel-${Date.now()}`, name: "新通知渠道", type: "webhook", enabled: false, url: "", token: "", timeout: 5, titleTemplate: "{app} {rule_name}", bodyTemplate: "告警：{message}\n当前值：{value}\n阈值：{threshold}\n时间：{timestamp}", urlTemplate: "", msgType: "text", htmlHeight: 200 });
}
function removeChannel(id) {
  channels.value = channels.value.filter((item) => item.id !== id);
}
async function editLabel(key, current) {
  const label = window.prompt("给这个容器端口设置备注，留空则清除", current || "");
  if (label === null) return;
  await api("/api/labels", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key, label }) });
  refreshConnections();
}
function openContainerPort(port) {
  const protocol = port.scheme === "https" ? "https:" : "http:";
  const host = location.hostname;
  const path = port.path || "/";
  const url = `${protocol}//${host}:${port.hostPort}${path.startsWith("/") ? path : `/${path}`}`;
  window.open(url, "_blank", "noopener,noreferrer");
}
function containerPortAddress(port) {
  return `${location.hostname}:${port.hostPort}`;
}
async function copyContainerPort(port) {
  const text = containerPortAddress(port);
  try {
    await navigator.clipboard.writeText(text);
    showToast(`已复制 ${text}`);
  } catch {
    window.prompt("复制连接地址", text);
  }
}
function normalizeEditorPort(port = {}) {
  return {
    proto: port.proto || "tcp",
    hostPort: Number(port.hostPort || port.containerPort || 0),
    containerPort: Number(port.containerPort || port.hostPort || 0),
    service: port.service || "",
    accessMode: port.accessMode === "web" ? "web" : port.accessMode === "hidden" ? "hidden" : "copy",
    scheme: port.scheme === "https" ? "https" : "http",
    path: port.path || "",
    label: port.label || "",
    enabled: true,
    manual: true,
  };
}
async function editDockerContainer(container) {
  const detail = container.portsLoaded ? container : (await loadDockerDetail(container)) || container;
  dockerEditor.id = detail.id || "";
  dockerEditor.name = detail.name || "";
  dockerEditor.icon = detail.containerIcon || "";
  dockerEditor.ports = (detail.ports || []).map(normalizeEditorPort);
  dockerEditDialog.value?.showModal();
}
function addDockerPort() {
  dockerEditor.ports.push(normalizeEditorPort({ proto: "tcp", hostPort: 8080, containerPort: 8080, accessMode: "web", service: "web" }));
}
function removeDockerPort(index) {
  dockerEditor.ports.splice(index, 1);
}
async function saveDockerPorts() {
  await saveDockerPortsFor({ id: dockerEditor.id, name: dockerEditor.name, containerIcon: dockerEditor.icon, ports: dockerEditor.ports });
  dockerEditDialog.value?.close();
  showToast("Docker 端口配置已保存");
}
async function saveDockerPortsFor(container) {
  const data = await api("/api/docker/containers/ports", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      containerId: container.id || "",
      containerName: container.name || "",
      icon: container.containerIcon || dockerEditor.icon || "",
      ports: (container.ports || []).map(normalizeEditorPort),
    }),
  });
  dockerData.value = { ...data, containers: mergeDockerContainers(data.containers || []) };
  const key = container.id || container.name;
  const target = (dockerData.value?.containers || []).find((item) => item.id === key || item.name === key);
  if (target) await loadDockerDetail(target);
}
function uploadDockerIcon(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    showToast("图标需为 PNG/JPG/WebP");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    dockerEditor.icon = String(reader.result || "");
  };
  reader.readAsDataURL(file);
}
async function logout() {
  await fetch("/api/auth/logout", { method: "POST" });
  location.href = "/login";
}
function showToast(message) {
  toast.value = message;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.value = "";
  }, 3000);
}

watch(theme, (value) => {
  document.documentElement.dataset.theme = value;
  localStorage.setItem("ntl-theme", value);
  nextTick(renderHistoryChart);
}, { immediate: true });

onMounted(async () => {
  await refreshOverview();
  overviewTimer = setInterval(() => {
    if (activeView.value === "overview") refreshOverview();
    if (activeView.value === "interfaces") refreshInterfaces();
  }, 2000);
  processTimer = setInterval(() => activeView.value === "processes" && refreshProcesses(), 10000);
  systemTimer = setInterval(() => activeView.value === "system" && refreshSystem(), 3000);
  window.addEventListener("resize", handleResize);
});
onUnmounted(() => {
  [overviewTimer, processTimer, systemTimer, connectionTimer, dockerTimer].forEach((timer) => timer && clearInterval(timer));
  if (connectionDebounce) clearTimeout(connectionDebounce);
  window.removeEventListener("resize", handleResize);
  historyChart?.dispose();
});
</script>
