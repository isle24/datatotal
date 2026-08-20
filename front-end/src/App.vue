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
          <button class="icon-button" type="button" title="设置" @click="setView('settings')">
            <Settings :size="18" />
          </button>
          <button v-if="overview?.authEnabled" type="button" @click="logout">退出</button>
        </div>
      </header>

      <section v-if="activeView === 'overview'" class="view">
        <section class="dashboard-board">
          <div class="dashboard-board-header">
            <div class="dashboard-board-title">
              <span class="dashboard-kicker"><Activity :size="14" /> 实时监控台</span>
              <h3>公网流量总览</h3>
              <p>{{ lastUpdated }} · {{ connectionSourceLabel }}</p>
            </div>
            <div class="dashboard-board-status">
              <span :class="['live-dot', { pending: !overviewIsFresh }]" aria-hidden="true"></span>
              <div>
                <strong>{{ overviewStatusLabel }}</strong>
                <span>{{ overviewIsFresh ? (overview?.containerStatus?.enabled ? "Docker 已接入" : "Docker 未接入") : "数据等待更新" }}</span>
              </div>
            </div>
            <button class="board-ai-button" type="button" :disabled="aiLoading" @click="analyzeWithAi('overview')">
              <Sparkles :size="16" />{{ aiLoading ? "分析中" : "AI 分析" }}
            </button>
          </div>
          <div class="dashboard-board-main">
            <div class="dashboard-total-block dashboard-total-primary">
              <span>当前公网总速率</span>
              <strong>{{ formatRate((summary.wan?.rxBps || 0) + (summary.wan?.txBps || 0)) }}</strong>
              <div class="dashboard-rate-bars">
                <div class="dashboard-rate-row"><span><ArrowDown :size="14" />下行</span><i><b class="rx" :style="{ width: rateBarWidth(summary.wan?.rxBps) }"></b></i><em>{{ formatRate(summary.wan?.rxBps) }}</em></div>
                <div class="dashboard-rate-row"><span><ArrowUp :size="14" />上行</span><i><b class="tx" :style="{ width: rateBarWidth(summary.wan?.txBps) }"></b></i><em>{{ formatRate(summary.wan?.txBps) }}</em></div>
              </div>
            </div>
            <div class="dashboard-total-block">
              <span>公网累计</span>
              <strong class="rx-text">↓ {{ formatBytes(summary.wan?.rxBytes) }}</strong>
              <strong class="tx-text">↑ {{ formatBytes(summary.wan?.txBytes) }}</strong>
              <small>采集累计流量</small>
            </div>
            <div class="dashboard-total-block dashboard-total-connections">
              <span>公网连接</span>
              <strong>{{ connectionSummary.wan || 0 }}</strong>
              <small>总连接 {{ connectionSummary.total || 0 }} · {{ connectionSourceLabel }}</small>
              <button type="button" @click="openWanConnections"><Network :size="15" />查看公网连接</button>
            </div>
          </div>
          <div class="dashboard-board-footer">
            <span><Network :size="14" /> 活跃网卡 {{ summary.interfaces?.up || 0 }} / {{ summary.interfaces?.total || 0 }}</span>
            <span><Server :size="14" /> 抓包接口 {{ (overview?.captureInterfaces || []).join("、") || "-" }}</span>
            <span><ShieldCheck :size="14" /> 数据刷新 {{ overviewIsFresh ? "正常" : "等待" }}</span>
          </div>
        </section>
        <div class="metric-grid dashboard-metric-grid">
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
          <MetricCard title="公网连接数" accent="red" :value="`${connectionSummary.wan || 0}`" @click="openWanConnections">
            <Network :size="18" />
          </MetricCard>
        </div>

        <div class="dashboard-status-grid grid two">
          <section class="card">
            <CardHead title="运行状态" :meta="lastUpdated" />
            <div class="info-grid">
              <InfoItem label="公网累计" :value="`↓ ${formatBytes(summary.wan?.rxBytes)} / ↑ ${formatBytes(summary.wan?.txBytes)}`" />
              <InfoItem label="总连接数" :value="`${connectionSummary.total || 0}`" />
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
            <button type="button" :disabled="aiLoading" @click="analyzeWithAi('history')"><Sparkles :size="16" />AI 分析</button>
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
          <div class="docker-stack">
            <article v-for="container in dockerContainers" :key="container.id || container.name" :class="['docker-card', 'accordion-card', { expanded: isDockerCardExpanded(container) }]">
              <button class="docker-card-trigger" type="button" :aria-expanded="isDockerCardExpanded(container)" @click="toggleDockerCard(container)">
                <div class="docker-icon">
                  <img v-if="container.containerIcon" :src="container.containerIcon" alt="" />
                  <Server v-else :size="22" />
                </div>
                <div>
                  <strong>{{ container.name }}</strong>
                  <p>{{ container.image }}</p>
                </div>
                <div class="docker-card-summary">
                  <span class="docker-port-count"><Network :size="14" />{{ container.portsLoaded ? (container.ports?.length || 0) : (container.portCount || 0) }} 端口</span>
                  <span v-if="container.protection?.enabled" class="pill warn">保护</span>
                  <span :class="['state-badge', `state-${dockerStateMeta(container.state).key}`]" :title="container.state || 'unknown'">
                    <component :is="dockerStateIcon(container.state)" :size="14" />
                    <span>{{ dockerStateMeta(container.state).label }}</span>
                  </span>
                  <component :is="isDockerCardExpanded(container) ? ChevronUp : ChevronDown" class="accordion-chevron" :size="18" />
                </div>
              </button>
              <div v-if="isDockerCardExpanded(container)" class="docker-card-body">
                <div class="docker-summary-strip">
                  <span><component :is="dockerStateIcon(container.state)" :size="15" />{{ dockerStatusLabel(container) }}</span>
                  <span><Network :size="15" />网络 {{ dockerNetworkLabel(container.networkMode) }}</span>
                  <span v-if="container.protection?.enabled"><ShieldCheck :size="15" />{{ container.protection.rules?.length || 0 }} 条保护规则</span>
                </div>
                <div v-if="container.showStats" class="docker-stats">
                  <span>CPU {{ formatPercent(container.stats?.cpuPercent) }}</span>
                  <span>内存 {{ formatBytes(container.stats?.memoryUsedBytes) }}</span>
                  <span>↓ {{ formatBytes(container.stats?.netRxBytes) }} / ↑ {{ formatBytes(container.stats?.netTxBytes) }}</span>
                </div>
                <button v-else type="button" class="subtle-button" @click.stop="showDockerStats(container)"><Gauge :size="15" />显示占用</button>
                <p v-if="container.protection?.state?.lastAction" class="docker-protection-state">
                  上次动作：{{ container.protection.state.lastAction }} · {{ container.protection.state.reason || "-" }}
                </p>
                <div class="port-list">
                <div v-for="port in container.ports" :key="`${port.proto}-${port.hostPort}`" class="port-row">
                  <div>
                    <strong>{{ port.hostPort }} → {{ port.containerPort }}/{{ port.proto }}</strong>
                    <p>{{ serviceLabel(port.service) }} · {{ port.label || "未备注" }}</p>
                  </div>
                  <span :class="['pill', port.accessMode === 'web' ? 'ok' : '']">{{ port.accessMode === "web" ? "Web" : "非 Web" }}</span>
                  <button v-if="port.accessMode === 'web'" type="button" title="打开 Web 端口" @click.stop="openContainerPort(port)"><ExternalLink :size="15" />打开</button>
                  <button v-else-if="port.accessMode !== 'hidden'" type="button" title="复制连接地址" @click.stop="copyContainerPort(port)"><Copy :size="15" />复制</button>
                  <button v-if="port.accessMode !== 'web' && port.accessMode !== 'hidden' && port.proto === 'tcp'" type="button" title="探测是否为 Web 服务" @click.stop="probeContainerPort(container, port)"><ExternalLink :size="15" />探测</button>
                  <span v-if="port.accessMode === 'hidden'" class="muted">已隐藏</span>
                </div>
                <button v-if="!container.portsLoaded" type="button" class="subtle-button" @click.stop="loadDockerDetail(container)"><RefreshCw :size="15" />加载端口</button>
                <div v-else-if="!container.ports?.length" class="empty compact">未发现映射端口；host 模式容器可手动添加</div>
                </div>
                <div class="edit-actions">
                  <button type="button" @click.stop="openConnections({ owner: container.name })"><Network :size="16" />连接</button>
                  <button type="button" @click.stop="editDockerContainer(container)"><Pencil :size="16" />端口/图标</button>
                </div>
              </div>
            </article>
            <div v-if="!dockerContainers.length" class="empty">暂无 Docker 容器数据；确认已映射 Docker socket 并启用 ENABLE_DOCKER_DISCOVERY，或先保存手动端口配置</div>
          </div>
        </section>
      </section>

      <section v-if="activeView === 'monitor'" class="view">
        <section class="monitor-hero">
          <div>
            <span class="dashboard-kicker"><Activity :size="14" /> 运行监控</span>
            <h3>监控中心</h3>
            <p>查看规则、容器保护与通知渠道的当前状态。详细配置统一放在设置中。</p>
          </div>
          <div class="monitor-hero-actions">
            <span class="monitor-health"><span class="live-dot"></span>{{ overviewIsFresh ? "监控运行中" : "等待数据" }}</span>
            <button type="button" :disabled="aiLoading" @click="analyzeWithAi('monitor')"><Sparkles :size="16" />AI 分析</button>
            <button type="button" @click="setView('settings')"><Settings :size="16" />打开设置</button>
          </div>
        </section>
        <div class="monitor-stat-grid">
          <div class="monitor-stat"><span>流量规则</span><strong>{{ monitorRules.filter((item) => item.enabled).length }}<small>/{{ monitorRules.length }}</small></strong><p>启用规则</p></div>
          <div class="monitor-stat"><span>容器保护</span><strong>{{ containerRules.filter((item) => item.enabled).length }}<small>/{{ containerRules.length }}</small></strong><p>监控中</p></div>
          <div class="monitor-stat"><span>通知渠道</span><strong>{{ channels.filter((item) => item.enabled).length }}<small>/{{ channels.length }}</small></strong><p>可用渠道</p></div>
          <div class="monitor-stat"><span>最近告警</span><strong>{{ overview?.alerts?.length || 0 }}</strong><p>当前缓存</p></div>
        </div>
        <section class="card monitor-section">
          <CardHead title="规则状态" meta="点击展开查看条件；编辑请进入设置">
            <button type="button" @click="setView('settings')"><Settings :size="16" />配置</button>
          </CardHead>
          <div class="accordion-stack monitor-stack">
            <article v-for="rule in monitorRules" :key="`status-${rule.id}`" :class="['monitor-status-card', { expanded: isMonitorCardExpanded('status-traffic', rule.id) }]">
              <button class="monitor-card-trigger" type="button" @click="toggleMonitorCard('status-traffic', rule.id)">
                <span class="monitor-card-icon"><Bell :size="17" /></span>
                <span class="monitor-card-copy"><strong>{{ rule.name || "未命名规则" }}</strong><small>{{ monitorRuleSummary(rule) }}</small></span>
                <span :class="['rule-state', rule.enabled ? 'enabled' : 'disabled']"><component :is="rule.enabled ? CheckCircle2 : CircleOff" :size="14" />{{ rule.enabled ? "启用" : "停用" }}</span>
                <component :is="isMonitorCardExpanded('status-traffic', rule.id) ? ChevronUp : ChevronDown" :size="18" />
              </button>
              <div v-if="isMonitorCardExpanded('status-traffic', rule.id)" class="monitor-card-body">
                <span>指标：{{ metricLabels[rule.metric] || rule.metric }}</span><span>阈值：{{ rule.threshold }}</span><span>持续：{{ rule.durationSeconds || 0 }} 秒</span><span>渠道：{{ (rule.channelIds || []).length || "未选择" }}</span>
              </div>
            </article>
            <div v-if="!monitorRules.length" class="empty card-empty">暂无流量监控规则</div>
          </div>
        </section>
        <section class="card monitor-section">
          <CardHead title="容器保护状态" meta="只在设定条件持续达到阈值后执行动作">
            <button type="button" @click="setView('settings')"><Settings :size="16" />配置</button>
          </CardHead>
          <div class="accordion-stack monitor-stack">
            <article v-for="rule in containerRules" :key="`status-container-${rule.id}`" :class="['monitor-status-card', { expanded: isMonitorCardExpanded('status-container', rule.id) }]">
              <button class="monitor-card-trigger" type="button" @click="toggleMonitorCard('status-container', rule.id)">
                <span class="monitor-card-icon protection"><ShieldCheck :size="17" /></span>
                <span class="monitor-card-copy"><strong>{{ rule.name || "未命名容器保护" }}</strong><small>{{ containerProtectionSummary(rule) }}</small></span>
                <span :class="['rule-state', rule.enabled ? 'enabled' : 'disabled']"><component :is="rule.enabled ? ShieldCheck : CircleOff" :size="14" />{{ rule.enabled ? "监控中" : "停用" }}</span>
                <component :is="isMonitorCardExpanded('status-container', rule.id) ? ChevronUp : ChevronDown" :size="18" />
              </button>
              <div v-if="isMonitorCardExpanded('status-container', rule.id)" class="monitor-card-body"><span>条件：{{ rule.conditions?.length || 0 }} 条 / {{ rule.logic === "or" ? "任一条件" : "全部条件" }}</span><span>动作：{{ containerProtectionActions.find((item) => item.value === rule.action)?.label || rule.action }}</span><span>最大次数：{{ rule.maxActions || 1 }}</span><span>通知：{{ (rule.channelIds || []).length || "未选择" }}</span></div>
            </article>
            <div v-if="!containerRules.length" class="empty card-empty">暂无容器保护规则</div>
          </div>
        </section>
        <section class="card monitor-section">
          <CardHead title="通知渠道状态" meta="渠道配置与模板在设置中维护">
            <button type="button" @click="setView('settings')"><Settings :size="16" />配置</button>
          </CardHead>
          <div class="accordion-stack monitor-stack">
            <article v-for="channel in channels" :key="`status-channel-${channel.id}`" :class="['monitor-status-card', { expanded: isMonitorCardExpanded('status-channel', channel.id) }]">
              <button class="monitor-card-trigger" type="button" @click="toggleMonitorCard('status-channel', channel.id)">
                <span class="monitor-card-icon channel"><Send :size="17" /></span>
                <span class="monitor-card-copy"><strong>{{ channel.name || "未命名渠道" }}</strong><small>{{ channelTypeLabel(channel.type) }} · {{ channel.url || "服务商默认地址" }}</small></span>
                <span :class="['rule-state', channel.enabled ? 'enabled' : 'disabled']"><component :is="channel.enabled ? CheckCircle2 : CircleOff" :size="14" />{{ channel.enabled ? "可用" : "停用" }}</span>
                <component :is="isMonitorCardExpanded('status-channel', channel.id) ? ChevronUp : ChevronDown" :size="18" />
              </button>
              <div v-if="isMonitorCardExpanded('status-channel', channel.id)" class="monitor-card-body"><span>类型：{{ channelTypeLabel(channel.type) }}</span><span>超时：{{ channel.timeout || 5 }} 秒</span><span>模板：{{ channel.bodyTemplate ? "已配置" : "默认" }}</span></div>
            </article>
            <div v-if="!channels.length" class="empty card-empty">暂无通知渠道</div>
          </div>
        </section>
      </section>

      <section v-if="activeView === 'ai'" class="view">
        <section class="ai-center-hero">
          <div>
            <span class="dashboard-kicker"><Sparkles :size="14" /> 数据洞察</span>
            <h3>AI 中心</h3>
            <p>按需读取当前流量、历史、进程、Docker、系统和告警摘要，帮助定位异常上传与资源瓶颈。</p>
          </div>
          <div class="ai-center-status">
            <span :class="['live-dot', { pending: !(aiForm.enabled && aiForm.keyConfigured) }]" aria-hidden="true"></span>
            <strong>{{ aiForm.enabled && aiForm.keyConfigured ? `已连接 · ${aiForm.model || "默认模型"}` : "请先配置 AI" }}</strong>
            <button v-if="!(aiForm.enabled && aiForm.keyConfigured)" type="button" @click="setView('settings')"><Settings :size="15" />去设置</button>
          </div>
        </section>
        <section class="ai-chat card">
          <div class="ai-chat-toolbar">
            <div><strong>数据对话</strong><span>上下文为聚合摘要，不发送完整连接原始表</span></div>
            <div class="card-actions">
              <button type="button" :disabled="aiLoading" @click="analyzeWithAi('all')"><Sparkles :size="15" />快速分析全部数据</button>
              <button type="button" class="subtle-button" :disabled="aiLoading || !aiMessages.length" @click="clearAiHistory"><Trash2 :size="15" />清空记录</button>
            </div>
          </div>
          <div class="ai-messages" aria-live="polite">
            <div v-if="!aiMessages.length" class="ai-empty"><Sparkles :size="24" /><strong>从一个问题开始</strong><span>例如：最近公网上传是否异常？哪个进程最值得关注？</span></div>
            <div v-for="(message, index) in aiMessages" :key="`${message.role}-${index}`" :class="['ai-message', message.role === 'user' ? 'user' : 'assistant']">
              <span class="ai-message-avatar"><UserRound v-if="message.role === 'user'" :size="15" /><Sparkles v-else :size="15" /></span>
              <div><small>{{ message.role === 'user' ? "你" : "AI 分析助手" }}</small><p>{{ message.content }}</p><em v-if="message.truncated" class="ai-message-warning">本次回答未完整结束</em></div>
            </div>
            <div v-if="aiLoading" class="ai-message assistant"><span class="ai-message-avatar"><Sparkles :size="15" /></span><div><small>AI 分析助手</small><p class="ai-thinking">正在读取统计摘要<span>·</span><span>·</span><span>·</span></p></div></div>
          </div>
          <p v-if="aiError" class="ai-error"><CircleAlert :size="15" />{{ aiError }}</p>
          <p v-if="aiWarning" class="ai-warning"><CircleAlert :size="15" />{{ aiWarning }}</p>
          <form class="ai-composer" @submit.prevent="sendAiChat">
            <textarea v-model="aiInput" rows="2" maxlength="2000" placeholder="输入你想分析的问题，例如：按公网上传排序，给出前 3 个风险来源"></textarea>
            <button type="submit" :disabled="aiLoading || !aiInput.trim()"><Send :size="16" />发送</button>
          </form>
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
              <label>Conntrack 刷新秒<input v-model.number="runtimeForm.conntrackRefreshSeconds" type="number" :min="settings?.runtime?.minConntrackRefreshSeconds || 15" /></label>
              <div class="field-block">
                <span>Docker 自动发现</span>
                <label class="switch"><input v-model="runtimeForm.dockerDiscovery" type="checkbox" />启用</label>
              </div>
              <div class="field-block">
                <span>阶段统计</span>
                <label class="switch"><input v-model="runtimeForm.autoStartStage" type="checkbox" />自动启动</label>
              </div>
            </div>
          </section>

          <section class="card">
            <CardHead title="启动期参数" meta="修改后需重启容器" />
            <div class="info-grid">
              <InfoItem label="端口" :value="settings?.runtime?.appPort" />
              <InfoItem label="数据库" :value="settings?.runtime?.dbPath" />
              <InfoItem label="日志目录" :value="settings?.runtime?.logDir" />
              <InfoItem label="Docker Socket" :value="settings?.runtime?.dockerSocket || '-'" />
              <InfoItem label="采集档位" :value="`${settings?.runtime?.collectorProfile || '-'} / ${settings?.runtime?.collectorMode || '-'}`" />
              <InfoItem label="Go 采集器" :value="settings?.runtime?.goCollectorAvailable ? '运行中' : (settings?.runtime?.goCollectorEnabled ? '未接入' : '关闭')" />
              <InfoItem label="抓包接口" :value="(settings?.runtime?.captureInterfaces || []).join('、') || '-'" />
              <InfoItem label="抓包限流" :value="settings?.runtime?.packetCapture ? `${settings?.runtime?.captureMaxEventsPerSecond || 0} 包/秒` : '关闭'" />
              <InfoItem label="动态抽样" :value="settings?.runtime?.captureDynamicSample ? `启用，最高 ${settings?.runtime?.captureMaxSampleRate || 1}x` : '关闭'" />
              <InfoItem label="系统校准" :value="settings?.runtime?.systemTrafficCalibration ? `启用，阈值 ${settings?.runtime?.systemTrafficCalibrationThreshold || '-'}` : '关闭'" />
              <InfoItem label="Conntrack 上限" :value="`${settings?.runtime?.conntrackMaxLines || '-'} 行 / ${settings?.runtime?.conntrackRefreshSeconds || '-'} 秒`" />
              <InfoItem label="Conntrack 状态" :value="settings?.runtime?.conntrackTruncated ? `已截断，扫描 ${settings?.runtime?.conntrackScannedLines || 0} 行` : '正常'" />
              <InfoItem label="版本" :value="settings?.version" />
            </div>
          </section>
        </div>

        <section class="card settings-ai-card">
          <CardHead title="AI 分析配置" meta="只在点击分析或发送对话时请求，不参与后台采集">
            <span :class="['rule-state', aiForm.enabled && aiForm.keyConfigured ? 'enabled' : 'disabled']"><component :is="aiForm.enabled && aiForm.keyConfigured ? CheckCircle2 : CircleOff" :size="14" />{{ aiForm.enabled && aiForm.keyConfigured ? "可用" : "未配置" }}</span>
            <button type="button" @click="saveAiSettings"><Save :size="16" />保存</button>
          </CardHead>
          <div class="form-grid ai-form-grid">
            <div class="field-block"><span>启用 AI 分析</span><label class="switch"><input v-model="aiForm.enabled" type="checkbox" />允许按需请求</label></div>
            <label>AI 厂商<select v-model="aiForm.provider" @change="applyAiProviderPreset"><option v-for="provider in providerPresets" :key="provider.value" :value="provider.value">{{ provider.label }}</option></select></label>
            <label>Base URL<input v-model="aiForm.baseUrl" type="url" placeholder="https://api.openai.com/v1" /></label>
            <label>API Key<input v-model="aiForm.apiKey" type="password" autocomplete="off" :placeholder="aiForm.keyConfigured ? aiForm.apiKeyMasked : '填写后保存，前端只显示掩码'" /></label>
            <label>模型
              <div class="inline-field">
                <select v-if="aiModels.length" v-model="aiForm.model" aria-label="从模型列表选择">
                  <option v-for="model in aiModels" :key="model.id" :value="model.id">{{ model.name || model.id }}</option>
                </select>
                <input v-model="aiForm.model" list="ai-model-options" placeholder="gpt-4o-mini / qwen-plus / deepseek-v4-flash" />
                <button type="button" class="subtle-button" :disabled="aiModelsLoading" @click="readAiModels"><RefreshCw :size="15" />{{ aiModelsLoading ? "读取中" : "读取模型" }}</button>
              </div>
              <datalist id="ai-model-options"><option v-for="model in aiModels" :key="`list-${model.id}`" :value="model.id">{{ model.name }}</option></datalist>
            </label>
            <label>请求超时秒<input v-model.number="aiForm.timeoutSeconds" type="number" min="5" max="180" /></label>
            <label>最大输出 Token<input v-model.number="aiForm.maxTokens" type="number" min="128" max="393216" /></label>
            <label class="textarea-label wide">系统提示词<textarea v-model="aiForm.systemPrompt" rows="3" placeholder="定义 AI 分析时的角色和关注点"></textarea></label>
          </div>
          <p v-if="aiModelsError" class="settings-security-note"><CircleAlert :size="15" />{{ aiModelsError }}，仍可手动填写模型。</p>
          <p class="settings-security-note"><ShieldCheck :size="15" /> API Key 只保存在 SQLite，不会回显到页面，也不会写入日志；Base URL 仅允许 HTTP/HTTPS。</p>
        </section>

        <section class="card">
          <CardHead title="监控规则" :meta="`${monitorRules.length} 条 · 支持多规则多渠道`">
            <button type="button" @click="addRule"><Plus :size="16" />新增</button>
            <button type="button" @click="saveRules"><Save :size="16" />保存</button>
          </CardHead>
          <div class="rule-grid accordion-stack">
            <div v-for="rule in monitorRules" :key="rule.id" :class="['edit-card', 'collapsible-card', { expanded: isMonitorCardExpanded('traffic', rule.id) }]">
              <div class="edit-title card-summary-row">
                <button class="collapse-toggle" type="button" :aria-expanded="isMonitorCardExpanded('traffic', rule.id)" @click="toggleMonitorCard('traffic', rule.id)">
                  <component :is="isMonitorCardExpanded('traffic', rule.id) ? ChevronUp : ChevronDown" :size="16" />
                  <span>
                    <strong>{{ rule.name || "未命名规则" }}</strong>
                    <small>{{ monitorRuleSummary(rule) }}</small>
                  </span>
                </button>
                <div class="summary-actions">
                  <span :class="['rule-state', rule.enabled ? 'enabled' : 'disabled']">
                    <component :is="rule.enabled ? CheckCircle2 : CircleOff" :size="14" />{{ rule.enabled ? "启用" : "停用" }}
                  </span>
                </div>
              </div>
              <div v-if="isMonitorCardExpanded('traffic', rule.id)" class="card-editor">
                <div class="form-grid mini">
                  <label>规则名称<input v-model="rule.name" /></label>
                  <div class="field-block"><span>状态</span><label class="switch"><input v-model="rule.enabled" type="checkbox" />启用</label></div>
                  <label>指标<select v-model="rule.metric"><option v-for="(label, key) in metricLabels" :key="key" :value="key">{{ label }}</option></select></label>
                  <label>阈值<input v-model.number="rule.threshold" type="number" min="0" /></label>
                  <label>持续秒<input v-model.number="rule.durationSeconds" type="number" min="0" /></label>
                  <div class="field-block wide">
                    <span>通知渠道</span>
                    <div class="channel-checks">
                      <label v-for="channel in channels" :key="channel.id" class="check-chip">
                        <input :checked="rule.channelIds?.includes(channel.id)" type="checkbox" @change="toggleRuleChannel(rule, channel.id)" />
                        {{ channel.name }}
                      </label>
                      <span v-if="!channels.length" class="field-hint">请先添加通知渠道</span>
                    </div>
                  </div>
                </div>
                <button class="danger" type="button" @click="removeRule(rule.id)"><Trash2 :size="16" />删除规则</button>
              </div>
            </div>
            <div v-if="!monitorRules.length" class="empty card-empty">暂无流量监控规则</div>
          </div>
        </section>

        <section class="card">
          <CardHead title="容器保护" :meta="`${containerRules.length} 条 · 监控触发后可复用现有告警渠道`">
            <button type="button" @click="addContainerRule"><Plus :size="16" />新增</button>
            <button type="button" @click="saveContainerRules"><Save :size="16" />保存</button>
          </CardHead>
          <div class="rule-grid accordion-stack">
            <div v-for="rule in containerRules" :key="rule.id" :class="['edit-card', 'collapsible-card', { expanded: isMonitorCardExpanded('container', rule.id) }]">
              <div class="edit-title card-summary-row">
                <button class="collapse-toggle" type="button" :aria-expanded="isMonitorCardExpanded('container', rule.id)" @click="toggleMonitorCard('container', rule.id)">
                  <component :is="isMonitorCardExpanded('container', rule.id) ? ChevronUp : ChevronDown" :size="16" />
                  <span>
                    <strong>{{ rule.name || "未命名容器保护" }}</strong>
                    <small>{{ containerProtectionSummary(rule) }}</small>
                  </span>
                </button>
                <div class="summary-actions">
                  <span :class="['rule-state', rule.enabled ? 'enabled' : 'disabled']">
                    <component :is="rule.enabled ? ShieldCheck : CircleOff" :size="14" />{{ rule.enabled ? "监控中" : "停用" }}
                  </span>
                </div>
              </div>
              <div v-if="isMonitorCardExpanded('container', rule.id)" class="card-editor">
                <div class="form-grid mini">
                <label>规则名称<input v-model="rule.name" placeholder="规则名称" /></label>
                <div class="field-block"><span>状态</span><label class="switch"><input v-model="rule.enabled" type="checkbox" />启用</label></div>
                <div class="field-block wide">
                  <span>选择容器</span>
                  <input
                    v-model="rule.containerSearch"
                    :list="`container-options-${rule.id}`"
                    placeholder="搜索容器名 / Compose 服务 / 镜像 / ID"
                    @change="selectContainerForRule(rule)"
                  />
                  <datalist :id="`container-options-${rule.id}`">
                    <option v-for="container in dockerContainerOptions" :key="container.optionValue" :value="container.optionValue">
                      {{ container.optionLabel }}
                    </option>
                  </datalist>
                  <p class="field-hint">
                    {{ containerRuleTargetText(rule) }}
                  </p>
                </div>
                <label>容器名<input v-model="rule.containerName" placeholder="容器名称，更新后优先匹配" /></label>
                <label>逻辑<select v-model="rule.logic"><option v-for="item in containerProtectionLogicOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                <label>动作<select v-model="rule.action"><option v-for="item in containerProtectionActions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                <label>最大次数<input v-model.number="rule.maxActions" type="number" min="1" /></label>
                <label>冷却秒<input v-model.number="rule.cooldownSeconds" type="number" min="0" /></label>
                <div class="field-block wide">
                  <span>告警渠道</span>
                  <div class="channel-checks">
                    <label v-for="channel in channels" :key="channel.id" class="check-chip">
                      <input :checked="rule.channelIds?.includes(channel.id)" type="checkbox" @change="toggleContainerRuleChannel(rule, channel.id)" />
                      {{ channel.name }}
                    </label>
                  </div>
                </div>
                <div class="field-block wide">
                  <span>条件</span>
                  <div class="condition-list">
                    <div v-for="(condition, index) in rule.conditions || []" :key="`${rule.id}-${index}`" class="condition-row">
                      <label>指标<select v-model="condition.metric"><option v-for="(label, key) in containerProtectionMetricLabels" :key="key" :value="key">{{ label }}</option></select></label>
                      <label>比较<select v-model="condition.operator"><option v-for="item in containerProtectionOperators" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                      <label>阈值<input v-model.number="condition.threshold" type="number" min="0" /></label>
                      <label>持续秒<input v-model.number="condition.durationSeconds" type="number" min="0" /></label>
                      <button class="danger" type="button" @click="removeContainerCondition(rule, index)"><Trash2 :size="16" />删除</button>
                    </div>
                    <button type="button" class="subtle-button" @click="addContainerCondition(rule)"><Plus :size="16" />添加条件</button>
                  </div>
                </div>
              </div>
                <button class="danger" type="button" @click="removeContainerRule(rule.id)"><Trash2 :size="16" />删除规则</button>
              </div>
            </div>
            <div v-if="!containerRules.length" class="empty card-empty">暂无容器保护规则</div>
          </div>
        </section>

        <section class="card">
          <CardHead title="通知渠道" :meta="`${channels.length} 个 · Webhook / IYUU / MeoW`">
            <button type="button" @click="addChannel"><Plus :size="16" />新增</button>
            <button type="button" @click="saveChannels"><Save :size="16" />保存</button>
          </CardHead>
          <div class="channel-grid accordion-stack">
            <div v-for="channel in channels" :key="channel.id" :class="['edit-card', 'channel-card', 'collapsible-card', { expanded: isMonitorCardExpanded('channel', channel.id) }]">
              <div class="edit-title card-summary-row">
                <button class="collapse-toggle" type="button" :aria-expanded="isMonitorCardExpanded('channel', channel.id)" @click="toggleMonitorCard('channel', channel.id)">
                  <component :is="isMonitorCardExpanded('channel', channel.id) ? ChevronUp : ChevronDown" :size="16" />
                  <span>
                    <strong>{{ channel.name || "未命名渠道" }}</strong>
                    <small>{{ channelTypeLabel(channel.type) }} · {{ channel.enabled ? "启用" : "停用" }}</small>
                  </span>
                </button>
                <div class="summary-actions">
                  <span :class="['rule-state', channel.enabled ? 'enabled' : 'disabled']">
                    <component :is="channel.enabled ? CheckCircle2 : CircleOff" :size="14" />{{ channel.enabled ? "启用" : "停用" }}
                  </span>
                </div>
              </div>
              <div v-if="isMonitorCardExpanded('channel', channel.id)" class="card-editor">
                <div class="form-grid mini">
                  <label>渠道名称<input v-model="channel.name" /></label>
                  <div class="field-block"><span>状态</span><label class="switch"><input v-model="channel.enabled" type="checkbox" />启用</label></div>
                <label>类型<select v-model="channel.type"><option value="webhook">Webhook</option><option value="iyuu">IYUU</option><option value="meow">MeoW</option></select></label>
                <label>URL<input v-model="channel.url" type="url" placeholder="Webhook 可填；IYUU/MeoW 可留空" /></label>
                <label>Token / 昵称<input v-model="channel.token" placeholder="IYUU token 或 MeoW 昵称" /></label>
                <label>超时秒<input v-model.number="channel.timeout" type="number" min="1" max="30" /></label>
                <label>消息类型<select v-model="channel.msgType"><option value="text">text</option><option value="html">html</option></select></label>
                <label>HTML 高度<input v-model.number="channel.htmlHeight" type="number" min="100" max="1200" /></label>
                <label>跳转 URL 模板<input v-model="channel.urlTemplate" placeholder="可用 {rule_id} 等变量" /></label>
              </div>
                <div class="template-help">
                <span>可用变量：</span>
                <code v-for="item in templateVariables" :key="templateKey(item)">{{ templateVar(templateKey(item)) }} · {{ templateLabel(item) }}</code>
                </div>
                <label class="textarea-label">标题模板<textarea v-model="channel.titleTemplate" rows="2"></textarea></label>
                <label class="textarea-label">正文模板<textarea v-model="channel.bodyTemplate" rows="5"></textarea></label>
                <div class="edit-actions">
                  <button type="button" @click="testChannel(channel.id)"><Send :size="16" />测试</button>
                  <button class="danger" type="button" @click="removeChannel(channel.id)"><Trash2 :size="16" />删除</button>
                </div>
              </div>
            </div>
            <div v-if="!channels.length" class="empty card-empty">暂无通知渠道</div>
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
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleOff,
  CircleAlert,
  Copy,
  Cpu,
  Database,
  ExternalLink,
  Gauge,
  HardDrive,
  HelpCircle,
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
  ShieldCheck,
  Settings,
  Sparkles,
  Sun,
  Trash2,
  UserRound,
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
  { key: "monitor", label: "监控中心", icon: Activity },
  { key: "settings", label: "设置", icon: Settings },
  { key: "ai", label: "AI 中心", icon: Sparkles },
];
const metricLabels = {
  wan_tx_bps: "公网上传速率",
  wan_rx_bps: "公网下载速率",
  lan_tx_bps: "内网上传速率",
  lan_rx_bps: "内网下载速率",
  wan_connections: "公网连接数",
  total_connections: "总连接数",
  daily_wan_tx_bytes: "每日公网上传总量",
};
const providerPresets = [
  { value: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini", maxTokens: 1200 },
  { value: "claude", label: "Claude", baseUrl: "https://api.anthropic.com/v1", model: "claude-3-5-haiku-latest", maxTokens: 4096 },
  { value: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com", model: "deepseek-v4-flash", maxTokens: 393216 },
  { value: "kimi", label: "Kimi", baseUrl: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k", maxTokens: 4096 },
  { value: "qwen", label: "Qwen", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus", maxTokens: 4096 },
  { value: "minimax", label: "MiniMax", baseUrl: "https://api.minimaxi.com/v1", model: "MiniMax-Text-01", maxTokens: 4096 },
  { value: "custom", label: "自定义兼容接口", baseUrl: "", model: "", maxTokens: 1200 },
];
const templateVariables = [
  ["app", "应用名"],
  ["version", "版本"],
  ["channel_id", "渠道ID"],
  ["channel_name", "渠道名"],
  ["channel_type", "渠道类型"],
  ["alert_id", "告警ID"],
  ["rule_id", "规则ID"],
  ["rule_name", "规则名"],
  ["message", "消息"],
  ["severity", "级别"],
  ["value", "当前值"],
  ["threshold", "阈值"],
  ["timestamp", "时间"],
  ["iso_time", "ISO 时间"],
  ["container_id", "容器ID"],
  ["container_name", "容器名"],
  ["container_action", "动作"],
  ["container_reason", "原因"],
  ["matched_metrics", "匹配指标"],
  ["container_metrics", "指标详情"],
];
const containerProtectionMetricLabels = {
  cpuPercent: "CPU",
  memoryPercent: "内存%",
  memoryUsedBytes: "内存用量",
  blkReadBps: "块读速率",
  blkWriteBps: "块写速率",
  blkIoBps: "块 I/O",
};
const containerProtectionOperators = [
  { value: "gte", label: "大于等于" },
  { value: "lte", label: "小于等于" },
];
const containerProtectionLogicOptions = [
  { value: "and", label: "AND" },
  { value: "or", label: "OR" },
];
const containerProtectionActions = [
  { value: "restart", label: "重启" },
  { value: "stop", label: "停止" },
];
const dockerStateMetaMap = {
  running: { key: "running", label: "运行中", icon: CheckCircle2 },
  exited: { key: "stopped", label: "已停止", icon: CircleOff },
  stopped: { key: "stopped", label: "已停止", icon: CircleOff },
  restarting: { key: "restarting", label: "重启中", icon: RefreshCw },
  paused: { key: "paused", label: "已暂停", icon: CircleOff },
  created: { key: "created", label: "已创建", icon: HelpCircle },
  dead: { key: "error", label: "异常", icon: CircleOff },
  manual: { key: "manual", label: "手动配置", icon: Pencil },
};
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
const overviewFresh = ref(false);
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
const containerRules = ref([]);
const channels = ref([]);
const expandedMonitorCards = reactive(new Set());
const expandedDockerCards = reactive(new Set());
const runtimeForm = reactive({});
const aiForm = reactive({
  enabled: false,
  provider: "openai",
  baseUrl: "https://api.openai.com/v1",
  apiKey: "",
  apiKeyMasked: "",
  keyConfigured: false,
  model: "gpt-4o-mini",
  timeoutSeconds: 60,
  maxTokens: 1200,
  systemPrompt: "",
});
const aiModels = ref([]);
const aiModelsLoading = ref(false);
const aiModelsError = ref("");
const aiMessages = ref([]);
const aiInput = ref("");
const aiError = ref("");
const aiWarning = ref("");
const aiLoading = ref(false);
const aiHistoryLoaded = ref(false);
let aiHistoryPromise = null;
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
const connectionSummary = computed(() => overview.value?.connectionSummary || {});
const lastUpdated = computed(() => (overview.value?.timestamp ? new Date(overview.value.timestamp * 1000).toLocaleTimeString() : "-"));
const overviewIsFresh = computed(() => {
  if (!overviewFresh.value || !overview.value) return false;
  const timestamp = Number(overview.value.timestamp || 0);
  return !timestamp || (Date.now() / 1000 - timestamp) <= 10;
});
const overviewStatusLabel = computed(() => {
  if (overviewIsFresh.value) return "采集正常";
  return overview.value ? "采集延迟" : "连接中";
});
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
    const protectionText = `${container.protection?.enabled ? "protect" : ""} ${container.protection?.state?.lastAction || ""}`;
    return `${container.name} ${container.image} ${container.state} ${container.status} ${container.networkMode} ${portText} ${protectionText}`.toLowerCase().includes(keyword);
  });
});
const dockerStatusText = computed(() => {
  const status = dockerData.value?.status || {};
  const suffix = dockerSearch.value ? `，筛选 ${dockerContainers.value.length} 个` : "";
  if (!dockerData.value?.enabled) return `Docker 发现未启用${suffix}`;
  return `${status.containerCount || dockerData.value?.containers?.length || 0} 个容器，${status.count || 0} 个端口${suffix}`;
});
const dockerProtectionCount = computed(() => (dockerData.value?.containers || []).filter((item) => item.protection?.enabled).length);
const dockerContainerOptions = computed(() => (dockerData.value?.containers || []).map((container) => {
  const id = (container.id || "").slice(0, 12);
  const compose = [container.composeProject, container.composeService].filter(Boolean).join("/");
  const title = [container.name || id || "unknown", compose || "", container.image || ""].filter(Boolean).join(" · ");
  return {
    ...container,
    optionValue: `${container.name || id} | ${compose || "no-compose"} | ${container.image || ""} | ${id}`,
    optionLabel: title,
  };
}));
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
function rateBarWidth(value) {
  const rx = Number(summary.value.wan?.rxBps || 0);
  const tx = Number(summary.value.wan?.txBps || 0);
  const peak = Math.max(1, rx, tx);
  return `${Math.max(3, Math.min(100, (Number(value || 0) / peak) * 100))}%`;
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
function templateLabel(item) {
  return Array.isArray(item) ? item[1] : item;
}
function templateKey(item) {
  return Array.isArray(item) ? item[0] : item;
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
function dockerStateMeta(state) {
  return dockerStateMetaMap[String(state || "").toLowerCase()] || { key: "unknown", label: "未知", icon: HelpCircle };
}
function dockerStateIcon(state) {
  return dockerStateMeta(state).icon;
}
function dockerStatusLabel(container = {}) {
  if (container.manualOnly || String(container.state || "").toLowerCase() === "manual") return "手动端口配置";
  const state = dockerStateMeta(container.state);
  const status = String(container.status || "").toLowerCase();
  if (status.includes("unhealthy")) return `${state.label} · 健康检查异常`;
  if (status.includes("healthy")) return `${state.label} · 健康`;
  if (state.key === "running") {
    const runningFor = status.match(/^up\s+(.+)$/i)?.[1];
    return runningFor ? `运行中 · 已运行 ${runningFor.replace(/\s+\(healthy\)$/i, "")}` : state.label;
  }
  if (state.key === "stopped") {
    const exitCode = status.match(/^exited\s+\((\d+)\)/i)?.[1];
    return exitCode ? `已停止 · 退出码 ${exitCode}` : state.label;
  }
  return state.label;
}
function dockerNetworkLabel(mode) {
  const value = String(mode || "").trim();
  const labels = { host: "主机", bridge: "桥接", none: "无网络", default: "默认", manual: "手动配置" };
  return labels[value.toLowerCase()] || value || "未知";
}
function monitorCardKey(type, id) {
  return `${type}:${id}`;
}
function dockerCardKey(container) {
  return container?.id || container?.name || "";
}
function isDockerCardExpanded(container) {
  return expandedDockerCards.has(dockerCardKey(container));
}
async function toggleDockerCard(container) {
  const key = dockerCardKey(container);
  if (!key) return;
  if (expandedDockerCards.has(key)) expandedDockerCards.delete(key);
  else {
    expandedDockerCards.add(key);
    if (!container.portsLoaded) {
      try {
        await loadDockerDetail(container);
      } catch (error) {
        console.warn("load expanded docker detail failed", error);
      }
    }
  }
}
function isMonitorCardExpanded(type, id) {
  return expandedMonitorCards.has(monitorCardKey(type, id));
}
function toggleMonitorCard(type, id) {
  const key = monitorCardKey(type, id);
  if (expandedMonitorCards.has(key)) expandedMonitorCards.delete(key);
  else expandedMonitorCards.add(key);
}
function expandMonitorCard(type, id) {
  expandedMonitorCards.add(monitorCardKey(type, id));
}
function monitorRuleSummary(rule = {}) {
  const metric = metricLabels[rule.metric] || "未选择指标";
  const duration = Number(rule.durationSeconds || 0);
  return `${metric} · 阈值 ${Number(rule.threshold || 0)}${duration ? ` · 持续 ${duration} 秒` : ""}`;
}
function containerProtectionSummary(rule = {}) {
  const target = rule.containerName || rule.composeService || "未选择容器";
  const logic = rule.logic === "or" ? "任一条件" : "全部条件";
  const action = containerProtectionActions.find((item) => item.value === rule.action)?.label || "重启";
  return `${target} · ${logic} · ${rule.conditions?.length || 0} 条 · ${action}`;
}
function channelTypeLabel(type) {
  const labels = { webhook: "Webhook", iyuu: "IYUU", meow: "MeoW" };
  return labels[String(type || "").toLowerCase()] || "自定义";
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
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (error) {
    if (!response.ok) throw new Error(text || response.statusText || "请求失败");
    throw error;
  }
  if (!response.ok) {
    const error = new Error(Array.isArray(data?.detail) ? "请求参数无效" : (data?.detail || text || response.statusText || "请求失败"));
    error.detail = data?.detail;
    error.status = response.status;
    throw error;
  }
  return data;
}
async function api(url, options) {
  return readJson(await fetch(url, { cache: "no-store", ...options }));
}
function parseSseBlock(block) {
  const payload = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n")
    .trim();
  if (!payload || payload === "[DONE]") return null;
  try {
    return JSON.parse(payload);
  } catch {
    throw new Error("AI 服务返回了无效的流式数据");
  }
}
async function streamApi(url, options, onEvent) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (response.status === 401) {
    location.href = "/login";
    throw new Error("authentication required");
  }
  if (!response.ok) return readJson(response);
  if (!response.body) throw new Error("当前浏览器不支持流式响应");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = null;
  const consume = (final = false) => {
    buffer = buffer.replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const event = parseSseBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (event) {
        if (event.type === "error" || event.ok === false) throw new Error(event.detail || "AI 请求失败");
        onEvent?.(event);
        if (event.type === "done") completed = event;
      }
      boundary = buffer.indexOf("\n\n");
    }
    if (final && buffer.trim()) {
      const event = parseSseBlock(buffer);
      buffer = "";
      if (event) {
        if (event.type === "error" || event.ok === false) throw new Error(event.detail || "AI 请求失败");
        onEvent?.(event);
        if (event.type === "done") completed = event;
      }
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        consume(true);
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      consume();
    }
  } catch (error) {
    try { await reader.cancel(); } catch {}
    throw error;
  } finally {
    reader.releaseLock();
  }
  if (!completed) throw new Error("AI 流式响应意外结束");
  return completed;
}
async function refreshOverview() {
  if (overviewLoading) return;
  overviewLoading = true;
  try {
    overview.value = await api(`/api/overview?interfaces=${encodeURIComponent(interfaceView.value)}`);
    overviewFresh.value = true;
  } catch (error) {
    overviewFresh.value = false;
    console.warn("load overview failed", error);
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
  containerRules.value = JSON.parse(JSON.stringify(settings.value.monitor?.containerRules || [])).map(normalizeContainerRuleForm);
  channels.value = JSON.parse(JSON.stringify(settings.value.monitor?.channels || []));
  Object.assign(runtimeForm, settings.value.runtime || {});
  Object.assign(aiForm, settings.value.ai || {});
  aiForm.apiKey = "";
  if (activeView.value === "settings") refreshDockerContainerOptions();
}
async function refreshAiSettings() {
  const data = await api("/api/settings/ai");
  Object.assign(aiForm, data || {});
  aiForm.apiKey = "";
  aiModels.value = [];
  aiModelsError.value = "";
  await refreshAiHistory();
}
async function refreshAiHistory(force = false) {
  if (aiHistoryPromise && !force) return aiHistoryPromise;
  if (aiHistoryLoaded.value && !force) return;
  aiHistoryPromise = api("/api/ai/history").then((data) => {
    aiMessages.value = Array.isArray(data?.messages) ? data.messages : [];
    aiHistoryLoaded.value = true;
    return data;
  }).finally(() => {
    aiHistoryPromise = null;
  });
  return aiHistoryPromise;
}
async function clearAiHistory() {
  if (!aiMessages.value.length || aiLoading.value) return;
  await api("/api/ai/history", { method: "DELETE" });
  aiMessages.value = [];
  aiHistoryLoaded.value = true;
  aiWarning.value = "";
  showToast("AI 记录已清空");
}
function applyAiProviderPreset() {
  const preset = providerPresets.find((item) => item.value === aiForm.provider);
  if (!preset) return;
  aiForm.baseUrl = preset.baseUrl;
  aiForm.model = preset.model;
  aiForm.maxTokens = preset.maxTokens;
  aiModels.value = [];
  aiModelsError.value = "";
}
function clampNumber(value, min, max, fallback) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(min, Math.min(max, Math.trunc(numeric)));
}
function formatValidationError(error) {
  const detail = error?.detail;
  if (!Array.isArray(detail)) return String(detail || error?.message || "请求失败");
  return detail.map((item) => {
    const field = Array.isArray(item?.loc) ? item.loc.filter((part) => part !== "body").join(".") : "请求";
    return `${field || "请求"}：${item?.msg || "参数无效"}`;
  }).join("；");
}
async function readAiModels() {
  if (aiModelsLoading.value) return;
  aiModelsLoading.value = true;
  aiModelsError.value = "";
  try {
    const result = await api("/api/ai/models?refresh=true", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        enabled: Boolean(aiForm.enabled),
        provider: aiForm.provider || "openai",
        baseUrl: String(aiForm.baseUrl || "").trim(),
        apiKey: aiForm.apiKey,
        model: String(aiForm.model || "").trim(),
        timeoutSeconds: clampNumber(aiForm.timeoutSeconds, 5, 180, 60),
        maxTokens: clampNumber(aiForm.maxTokens, 128, 393216, 1200),
        systemPrompt: aiForm.systemPrompt,
      }),
    });
    if (!result.ok) {
      aiModels.value = [];
      aiModelsError.value = result.detail || "模型读取失败";
      return;
    }
    aiModels.value = Array.isArray(result.models) ? result.models.slice(0, 200) : [];
    if (aiModels.value.length && !aiModels.value.some((item) => item.id === aiForm.model)) aiForm.model = aiModels.value[0].id;
    showToast(`已读取 ${aiModels.value.length} 个模型`);
  } catch (error) {
    aiModels.value = [];
    aiModelsError.value = formatValidationError(error);
  } finally {
    aiModelsLoading.value = false;
  }
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
  } finally {
    dockerLoading = false;
  }
}
async function refreshDockerContainerOptions() {
  if (dockerLoading || (dockerData.value?.containers || []).length) return;
  try {
    await refreshDocker();
  } catch (error) {
    console.warn("load docker container options failed", error);
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
function containerOptionValue(container = {}) {
  const id = (container.id || "").slice(0, 12);
  const compose = [container.composeProject, container.composeService].filter(Boolean).join("/");
  return `${container.name || id} | ${compose || "no-compose"} | ${container.image || ""} | ${id}`;
}
function normalizeContainerRuleForm(rule = {}) {
  const normalized = {
    composeProject: "",
    composeService: "",
    containerSearch: "",
    ...rule,
  };
  normalized.containerSearch = normalized.containerSearch || containerOptionValue({
    id: normalized.containerId,
    name: normalized.containerName,
    image: normalized.image || "",
    composeProject: normalized.composeProject,
    composeService: normalized.composeService,
  });
  return normalized;
}
function selectContainerForRule(rule) {
  const keyword = String(rule.containerSearch || "").trim().toLowerCase();
  const selected = dockerContainerOptions.value.find((container) => container.optionValue.toLowerCase() === keyword)
    || dockerContainerOptions.value.find((container) => {
      const id = String(container.id || "").slice(0, 12).toLowerCase();
      return keyword && (
        String(container.name || "").toLowerCase() === keyword
        || id === keyword
        || String(container.composeService || "").toLowerCase() === keyword
      );
    });
  if (!selected) return;
  rule.containerId = String(selected.id || "").slice(0, 12);
  rule.containerName = selected.name || rule.containerName || "";
  rule.composeProject = selected.composeProject || "";
  rule.composeService = selected.composeService || "";
  rule.containerSearch = selected.optionValue;
}
function containerRuleTargetText(rule = {}) {
  const id = rule.containerId ? `当前ID ${String(rule.containerId).slice(0, 12)}` : "未绑定当前ID";
  const name = rule.containerName ? `容器名 ${rule.containerName}` : "未设置容器名";
  const compose = rule.composeProject && rule.composeService ? `Compose ${rule.composeProject}/${rule.composeService}` : "无 Compose 标识";
  return `${name} · ${compose} · ${id}`;
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
  if (activeView.value === "monitor" || activeView.value === "settings") refreshSettings();
  if (activeView.value === "ai") refreshAiSettings();
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
  const mode = connectionSummary.value.source === "conntrack" ? "conntrack" : "capture";
  Object.assign(connFilters, { mode, iface: "all", scope: "wan", direction: "all", owner: "", source: "", dest: "" });
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
async function clearAlerts() {
  await api("/api/alerts/clear", { method: "POST" });
  refreshOverview();
}
async function saveRuntime() {
  settings.value = await api("/api/settings/runtime", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(runtimeForm) });
  Object.assign(runtimeForm, settings.value.runtime || {});
  showToast("运行参数已保存");
}
async function saveAiSettings() {
  try {
    settings.value = await api("/api/settings/ai", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        enabled: Boolean(aiForm.enabled),
        provider: aiForm.provider || "openai",
        baseUrl: String(aiForm.baseUrl || "").trim(),
        apiKey: aiForm.apiKey,
        model: String(aiForm.model || "").trim(),
        timeoutSeconds: clampNumber(aiForm.timeoutSeconds, 5, 180, 60),
        maxTokens: clampNumber(aiForm.maxTokens, 128, 393216, 1200),
        systemPrompt: aiForm.systemPrompt,
      }),
    });
    Object.assign(aiForm, settings.value.ai || {});
    aiForm.apiKey = "";
    aiModels.value = [];
    aiModelsError.value = "";
    showToast("AI 配置已保存");
  } catch (error) {
    showToast(`保存失败：${formatValidationError(error)}`);
  }
}
function applyAiStreamEvent(event, assistantIndex) {
  if (event.type === "delta" && aiMessages.value[assistantIndex]) {
    aiMessages.value[assistantIndex].content += event.content || "";
  }
  if (event.type !== "done" || !aiMessages.value[assistantIndex]) return;
  if (!aiMessages.value[assistantIndex].content) aiMessages.value[assistantIndex].content = event.answer || "";
  if (event.truncated) {
    aiMessages.value[assistantIndex].truncated = true;
    aiWarning.value = event.finishReason === "length"
      ? "AI 已达到最大输出 Token，回答可能未完整结束。"
      : "AI 流式连接未完整结束，回答可能不完整。";
  }
}
async function analyzeWithAi(scope = "overview") {
  if (aiLoading.value) return;
  aiLoading.value = true;
  aiError.value = "";
  aiWarning.value = "";
  const question = scope === "history"
    ? `请结合当前选择的历史周期（${historyPeriod.value}）分析公网和内网流量趋势，指出异常。`
    : scope === "monitor"
      ? "请检查监控规则、容器保护、通知渠道和最近告警，指出当前风险与配置建议。"
      : "请分析当前所有统计数据，重点指出公网上传风险、异常进程和 Docker/系统资源问题。";
  if (activeView.value !== "ai") setView("ai");
  await refreshAiHistory();
  aiMessages.value.push({ role: "user", content: question });
  const assistantIndex = aiMessages.value.length;
  aiMessages.value.push({ role: "assistant", content: "" });
  try {
    await streamApi("/api/ai/analyze?stream=true", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ scope, question }),
    }, (event) => {
      applyAiStreamEvent(event, assistantIndex);
    });
  } catch (error) {
    if (!aiMessages.value[assistantIndex]?.content) aiMessages.value.splice(assistantIndex, 1);
    aiError.value = error.message || "AI 分析请求失败";
  } finally {
    aiLoading.value = false;
  }
}
async function sendAiChat() {
  const content = aiInput.value.trim();
  if (!content || aiLoading.value) return;
  await refreshAiHistory();
  aiInput.value = "";
  aiError.value = "";
  aiWarning.value = "";
  aiMessages.value.push({ role: "user", content });
  const requestMessages = aiMessages.value.slice(-19).map((message) => ({
    role: message.role,
    content: String(message.content || "").slice(-6000),
  }));
  const assistantIndex = aiMessages.value.length;
  aiMessages.value.push({ role: "assistant", content: "" });
  aiLoading.value = true;
  try {
    await streamApi("/api/ai/chat?stream=true", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ messages: requestMessages }),
    }, (event) => {
      applyAiStreamEvent(event, assistantIndex);
    });
  } catch (error) {
    if (!aiMessages.value[assistantIndex]?.content) aiMessages.value.splice(assistantIndex, 1);
    aiError.value = error.message || "AI 对话请求失败";
  } finally {
    aiLoading.value = false;
  }
}
async function saveRules() {
  settings.value = await api("/api/settings/monitor", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rules: monitorRules.value }) });
  await refreshSettings();
  showToast("监控规则已保存");
}
async function saveContainerRules() {
  const payload = containerRules.value.map((rule) => ({
    ...rule,
    containerSearch: undefined,
    containerId: String(rule.containerId || "").slice(0, 12),
    containerName: String(rule.containerName || "").trim(),
    composeProject: String(rule.composeProject || "").trim(),
    composeService: String(rule.composeService || "").trim(),
    maxActions: Number(rule.maxActions || 1),
    cooldownSeconds: Number(rule.cooldownSeconds || 0),
    conditions: (rule.conditions || []).map((condition) => ({
      ...condition,
      threshold: Number(condition.threshold || 0),
      durationSeconds: Number(condition.durationSeconds || 0),
    })),
  }));
  settings.value = await api("/api/settings/container-protection", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ rules: payload }),
  });
  await refreshSettings();
  showToast("容器保护已保存");
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
  const rule = { id: `rule-${Date.now()}`, name: "新监控规则", metric: "wan_tx_bps", operator: "gte", threshold: 0, durationSeconds: 0, scope: "wan", direction: "tx", window: "realtime", enabled: false, channelIds: [] };
  monitorRules.value.push(rule);
  expandMonitorCard("traffic", rule.id);
}
function removeRule(id) {
  monitorRules.value = monitorRules.value.filter((item) => item.id !== id);
  expandedMonitorCards.delete(monitorCardKey("traffic", id));
}
function addContainerRule() {
  const rule = {
    id: `protection-${Date.now()}`,
    name: "新容器保护",
    containerId: "",
    containerName: "",
    composeProject: "",
    composeService: "",
    containerSearch: "",
    enabled: false,
    channelIds: [],
    logic: "and",
    action: "restart",
    maxActions: 3,
    cooldownSeconds: 60,
    conditions: [
      { metric: "cpuPercent", operator: "gte", threshold: 90, durationSeconds: 30 },
    ],
  };
  containerRules.value.push(rule);
  expandMonitorCard("container", rule.id);
}
function removeContainerRule(id) {
  containerRules.value = containerRules.value.filter((item) => item.id !== id);
  expandedMonitorCards.delete(monitorCardKey("container", id));
}
function addContainerCondition(rule) {
  rule.conditions = Array.isArray(rule.conditions) ? rule.conditions : [];
  rule.conditions.push({ metric: "cpuPercent", operator: "gte", threshold: 90, durationSeconds: 30 });
}
function removeContainerCondition(rule, index) {
  rule.conditions.splice(index, 1);
}
function toggleRuleChannel(rule, channelId) {
  const values = new Set(rule.channelIds || []);
  if (values.has(channelId)) values.delete(channelId);
  else values.add(channelId);
  rule.channelIds = Array.from(values);
}
function toggleContainerRuleChannel(rule, channelId) {
  const values = new Set(rule.channelIds || []);
  if (values.has(channelId)) values.delete(channelId);
  else values.add(channelId);
  rule.channelIds = Array.from(values);
}
function addChannel() {
  const channel = { id: `channel-${Date.now()}`, name: "新通知渠道", type: "webhook", enabled: false, url: "", token: "", timeout: 5, titleTemplate: "{app} {rule_name}", bodyTemplate: "告警：{message}\n当前值：{value}\n阈值：{threshold}\n时间：{timestamp}", urlTemplate: "", msgType: "text", htmlHeight: 200 };
  channels.value.push(channel);
  expandMonitorCard("channel", channel.id);
}
function removeChannel(id) {
  channels.value = channels.value.filter((item) => item.id !== id);
  expandedMonitorCards.delete(monitorCardKey("channel", id));
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
