<template>
  <div class="app-shell" :class="{ 'nas-native-content': native, 'menu-open': menuOpen, 'menu-pinned': menuPinned }">
    <div v-if="!native" class="sidebar-backdrop" :class="{ show: menuOpen }" @click="closeMenu"></div>
    <aside v-if="!native" class="sidebar" :class="{ 'sidebar-open': menuOpen }">
      <div class="brand">
        <div class="brand-mark"><Activity :size="22" /></div>
        <div>
          <h1>NAS Traffic Lens</h1>
          <p>v{{ overview?.version || settings?.version || "-" }}</p>
        </div>
      </div>
      <nav class="menu">
        <button v-for="item in navItems" :key="item.key" :class="{ active: activeView === item.key }" @click="navigate(item.key)">
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="sidebar-tools">
        <button type="button" :class="{ active: menuPinned }" :title="menuPinned ? '取消固定，恢复抽屉' : '固定菜单，常驻显示'" @click="setMenuPinned(!menuPinned)">
          <Pin :size="15" />{{ menuPinned ? "取消固定" : "固定菜单" }}
        </button>
        <button type="button" title="收起菜单" @click="closeMenu"><X :size="15" /></button>
      </div>
    </aside>

    <main class="main">
      <header v-if="!native" class="topbar">
        <div>
          <p class="topbar-description">{{ subtitle }}</p>
          <h2>{{ currentTitle }}</h2>
        </div>
        <div class="top-actions">
          <span v-if="toast" class="toast" role="status" aria-live="polite">{{ toast }}</span>
          <button class="icon-button menu-toggle" type="button" :aria-expanded="menuOpen" :title="menuOpen ? '收起菜单（m）' : '打开菜单（m）'" @click="toggleMenu">
            <X v-if="menuOpen" :size="18" />
            <Menu v-else :size="18" />
          </button>
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
      <div v-if="requestError" class="request-error" role="alert"><CircleAlert :size="18" /><span>{{ requestError }}</span><button type="button" @click="refreshActive"><RefreshCw :size="15" />重试</button></div>

      <NavigationView v-if="activeView === 'navigation'" :repository="bookmarks" :scope="targetName || '此 NAS'" />
      <section v-if="activeView === 'overview'" class="view">
        <slot name="overview" :summary="summary" :overview="overview" :connections="connectionSummary" :connection-source="connectionSourceLabel" :fresh="overviewIsFresh" :updated="lastUpdated" :open-connections="openConnections" :navigate="setView" :analyze="() => analyzeWithAi('overview')">
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
        <section class="workbench">
          <div class="workbench-head">
            <div>
              <h3>工作台</h3>
              <p>常用入口，点击进入对应页面</p>
            </div>
            <button class="workbench-menu-button" type="button" @click="toggleMenu">
              <Menu :size="16" />全部页面
            </button>
          </div>
          <div class="workbench-tiles">
            <button v-for="tile in workbenchTiles" :key="tile.key" class="workbench-tile" type="button" @click="navigate(tile.key)">
              <span class="workbench-tile-icon"><component :is="tile.icon" :size="19" /></span>
              <span class="workbench-tile-copy">
                <strong>{{ tile.label }}</strong>
                <small>{{ tile.meta }}</small>
              </span>
              <ArrowRight :size="16" class="workbench-tile-arrow" />
            </button>
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
          <MetricCard title="内网实时上行" accent="cyan" :value="formatRate(summary.lan?.txBps)">
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
              <button type="button" @click="setView('monitor')">查看告警记录</button>
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
        </slot>
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
                <tr v-if="!filteredInterfaces.length"><td colspan="9" class="empty">{{ interfacesLoading ? '正在读取网卡数据…' : ifaceFilter !== 'all' ? '当前筛选没有网卡，请选择全部网卡' : '当前尚未读取到网卡数据，可点击刷新重试' }}</td></tr>
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
          <p class="refresh-note">{{ historyLoading ? '正在更新，当前显示上次结果' : (historyUpdatedAt ? `更新于 ${formatDate(historyUpdatedAt)} · 每 30 秒刷新` : '等待历史数据') }}</p>
        </section>
      </section>

      <section v-if="activeView === 'processes'" class="view">
        <section class="card">
          <CardHead title="进程占用" meta="默认显示排行卡片">
            <div class="controls">
              <label>统计范围<select v-model="processPeriod" @change="processPeriod === 'custom' ? processRangeError = '' : refreshProcesses()">
                <option value="30s">30 秒</option><option value="today">当天</option><option value="1d">1 天</option><option value="3d">3 天</option><option value="7d">7 天</option><option value="30d">30 天</option><option value="custom">自定义</option>
              </select></label>
              <label v-if="processPeriod === 'custom'">开始时间<input v-model="processStart" type="datetime-local" /></label>
              <label v-if="processPeriod === 'custom'">结束时间<input v-model="processEnd" type="datetime-local" /></label>
              <button v-if="processPeriod === 'custom'" type="button" @click="applyProcessRange">应用时间范围</button>
              <label>筛选当前排行<input v-model="processSearch" type="search" placeholder="进程名称 / PID" /></label>
            </div>
          </CardHead>
          <p v-if="processRangeError" class="settings-feedback error" role="alert">{{ processRangeError }}</p>
          <p v-if="processPeriod === 'custom' && (processStart !== appliedProcessRange.start || processEnd !== appliedProcessRange.end)" class="field-hint">修改的时间范围尚未应用，请点击“应用时间范围”。</p>
          <p class="field-hint">显示前 30 名进程，输入框仅筛选当前排行。</p>
          <div v-if="processLoading" class="empty" role="status">正在读取进程排行…</div>
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
          <div v-if="!processLoading && !filteredProcesses.length" class="empty" role="status"><span>{{ processSearch ? '当前排行中没有匹配的进程' : processPeriod === 'custom' && !appliedProcessRange.start ? '请选择完整的时间范围并应用' : '当前时间范围还没有可见的进程流量' }}</span><button v-if="processSearch" type="button" @click="processSearch = ''">清空筛选</button></div>
        </section>
      </section>

      <section v-if="activeView === 'system'" class="view">
        <div class="metric-grid system-grid">
          <MetricCard title="CPU" accent="blue" :value="`${system?.cpu?.percent ?? 0}%`"><Cpu :size="18" /></MetricCard>
          <MetricCard title="内存" accent="cyan" :value="`${system?.memory?.percent ?? 0}%`"><Server :size="18" /></MetricCard>
          <MetricCard title="磁盘" accent="orange" :value="`${system?.disk?.percent ?? 0}%`"><HardDrive :size="18" /></MetricCard>
          <MetricCard title="运行时间" accent="violet" :value="formatDuration(system?.uptimeSeconds)"><Monitor :size="18" /></MetricCard>
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
            <CardHead title="温度" :meta="temperatureGroups.length ? `${temperatureGroups.length} 组传感器 · 点击展开` : 'psutil / sensors'" />
            <div v-if="temperatureGroups.length" class="accordion-stack system-stack">
              <article v-stack-motion
                v-for="group in temperatureGroups"
                :key="temperatureGroupKey(group)"
                :class="['system-card', 'temp-stack-card', { expanded: isSystemCardExpanded('temp', temperatureGroupKey(group)) }]"
              >
                <button class="system-card-trigger" type="button" :aria-expanded="isSystemCardExpanded('temp', temperatureGroupKey(group))" @click="toggleSystemCard('temp', temperatureGroupKey(group))">
                  <span class="system-card-icon"><Thermometer :size="17" /></span>
                  <span class="system-card-copy">
                    <strong>{{ group.name }}</strong>
                    <small>{{ group.rawName }} · {{ group.items.length }} 个传感器</small>
                  </span>
                  <span class="system-card-metric">
                    <b :class="['temp-value', hottestTemperatureItem(group)?.level]">{{ formatTemperature(maxTemperature(group)) }}</b>
                    <small>最高</small>
                  </span>
                  <component :is="isSystemCardExpanded('temp', temperatureGroupKey(group)) ? ChevronUp : ChevronDown" class="accordion-chevron" :size="18" />
                </button>
                <div v-if="isSystemCardExpanded('temp', temperatureGroupKey(group))" class="system-card-body">
                  <div v-for="item in group.items" :key="`${group.rawName}-${item.rawLabel}`" class="temp-reading">
                    <span class="temp-reading-label">
                      <strong>{{ item.label }}</strong>
                      <small>{{ item.rawLabel }}<template v-if="temperatureLimit(item.high)"> · 上限 {{ formatTemperature(item.high) }}</template></small>
                    </span>
                    <span class="temp-reading-bar" role="presentation"><i :class="item.level" :style="{ width: temperatureBarWidth(item) }"></i></span>
                    <b :class="['temp-value', item.level]">{{ formatTemperature(item.current) }}</b>
                  </div>
                </div>
              </article>
            </div>
            <div v-else class="empty">当前环境未暴露温度传感器</div>
          </section>
        </div>
        <section v-if="acceleratorCards.length" class="card">
          <CardHead title="GPU 与 NPU" :meta="`${acceleratorCards.length} 个设备 · 点击展开`" />
          <div class="accordion-stack system-stack">
            <article v-stack-motion
              v-for="item in acceleratorCards"
              :key="item.cardKey"
              :class="['system-card', 'accelerator-card', { expanded: isSystemCardExpanded('accel', item.cardKey) }]"
            >
              <button class="system-card-trigger" type="button" :aria-expanded="isSystemCardExpanded('accel', item.cardKey)" @click="toggleSystemCard('accel', item.cardKey)">
                <span class="system-card-icon"><component :is="item.kind === 'gpu' ? Monitor : Cpu" :size="17" /></span>
                <span class="system-card-copy">
                  <strong>{{ item.name }}</strong>
                  <small>{{ acceleratorSubtitle(item) }}</small>
                </span>
                <span :class="['accel-badge', acceleratorStatus(item).key]">{{ acceleratorStatus(item).label }}</span>
                <span class="system-card-metric">
                  <b :class="['accel-value', acceleratorStatus(item).key]">{{ formatPercent(acceleratorPercent(item)) }}</b>
                  <small>利用率</small>
                </span>
                <component :is="isSystemCardExpanded('accel', item.cardKey) ? ChevronUp : ChevronDown" class="accordion-chevron" :size="18" />
              </button>
              <div v-if="isSystemCardExpanded('accel', item.cardKey)" class="system-card-body">
                <template v-if="item.kind === 'gpu'">
                  <div v-for="engine in item.engines" :key="engine.name" class="temp-reading">
                    <span class="temp-reading-label"><strong>{{ engine.label }}</strong><small>{{ engine.name }}</small></span>
                    <span class="temp-reading-bar" role="presentation"><i :style="{ width: percentBarWidth(engine.busyPercent) }"></i></span>
                    <b class="temp-value">{{ formatPercent(engine.busyPercent) }}</b>
                  </div>
                  <p v-if="!item.engines?.length" class="system-card-note">没有可用的引擎计数器。</p>
                  <div class="fan-detail"><span>驱动</span><b>{{ item.driver || "-" }}</b></div>
                  <div class="fan-detail"><span>核心频率</span><b>{{ item.frequencyMhz ? `${item.frequencyMhz} MHz` : "空闲 0 MHz" }}</b></div>
                  <div v-if="item.idleResidencyPercent != null" class="fan-detail"><span>空闲驻留 (RC6)</span><b>{{ formatPercent(item.idleResidencyPercent) }}</b></div>
                </template>
                <template v-else>
                  <div class="fan-detail"><span>驱动</span><b>{{ item.driver || "-" }}</b></div>
                  <div class="fan-detail"><span>频率</span><b>{{ item.frequencyMhz != null ? `${item.frequencyMhz} / ${item.maxFrequencyMhz || "-"} MHz` : `最高 ${item.maxFrequencyMhz || "-"} MHz` }}</b></div>
                  <div v-if="item.memoryBytes != null" class="fan-detail"><span>常驻显存</span><b>{{ formatBytes(item.memoryBytes) }}</b></div>
                  <div v-if="item.powerState" class="fan-detail"><span>电源状态</span><b>{{ item.powerState }}</b></div>
                  <div v-if="item.schedMode" class="fan-detail"><span>调度模式</span><b>{{ item.schedMode }}</b></div>
                  <div v-if="item.busyTimeUs != null" class="fan-detail"><span>累计忙碌</span><b>{{ formatDuration(item.busyTimeUs / 1000000) }}</b></div>
                </template>
                <p v-if="item.hint" class="system-card-note">{{ item.hint }}</p>
              </div>
            </article>
          </div>
        </section>
        <section class="card">
          <CardHead title="风扇转速" :meta="systemFans.length ? `${systemFans.length} 个传感器 · 点击展开` : 'psutil / hwmon'" />
          <div v-if="systemFans.length" class="accordion-stack system-stack">
            <article v-stack-motion
              v-for="fan in systemFans"
              :key="fanCardKey(fan)"
              :class="['system-card', 'fan-stack-card', { expanded: isSystemCardExpanded('fan', fanCardKey(fan)) }]"
            >
              <button class="system-card-trigger" type="button" :aria-expanded="isSystemCardExpanded('fan', fanCardKey(fan))" @click="toggleSystemCard('fan', fanCardKey(fan))">
                <span class="system-card-icon" :class="{ stopped: fan.status === 'stopped' }"><Fan :size="17" /></span>
                <span class="system-card-copy">
                  <strong>{{ fan.name }}</strong>
                  <small>{{ fan.rawLabel || fan.rawName || "风扇传感器" }}</small>
                </span>
                <span :class="['fan-status', fan.status === 'running' ? 'running' : 'stopped']">{{ fan.status === 'running' ? "运行中" : "已停止" }}</span>
                <span class="system-card-metric">
                  <b>{{ formatFanRpm(fan.rpm) }}</b>
                  <small>转/分</small>
                </span>
                <component :is="isSystemCardExpanded('fan', fanCardKey(fan)) ? ChevronUp : ChevronDown" class="accordion-chevron" :size="18" />
              </button>
              <div v-if="isSystemCardExpanded('fan', fanCardKey(fan))" class="system-card-body">
                <div class="fan-detail"><span>传感器</span><b>{{ fan.rawName || "-" }}</b></div>
                <div class="fan-detail"><span>标识</span><b>{{ fan.rawLabel || "-" }}</b></div>
                <div class="fan-detail"><span>转速</span><b>{{ formatFanRpm(fan.rpm) }} 转/分</b></div>
                <div class="fan-speed">
                  <span class="fan-speed-bar" role="presentation"><i :style="{ width: fanSpeedBarWidth(fan, systemFans) }"></i></span>
                  <small>相对最高转速 {{ formatFanRpm(fanPeakRpm(systemFans)) }} 转/分</small>
                </div>
              </div>
            </article>
          </div>
          <div v-else class="empty fan-empty">当前环境未暴露风扇转速传感器</div>
        </section>
      </section>

      <section v-if="activeView === 'docker'" class="view">
        <section class="card">
          <CardHead title="Docker 容器" :meta="dockerStatusText">
            <input v-model="dockerSearch" class="search-input" type="search" placeholder="搜索容器、镜像、端口、备注" />
            <button type="button" @click="refreshDocker(true)"><RefreshCw :size="16" />刷新</button>
          </CardHead>
          <div class="docker-stack">
            <article v-stack-motion v-for="container in dockerContainers" :key="container.id || container.name" :class="['docker-card', 'accordion-card', { expanded: isDockerCardExpanded(container) }]">
              <button class="docker-card-trigger" type="button" :aria-expanded="isDockerCardExpanded(container)" @click="toggleDockerCard(container)">
                <div class="docker-icon" :title="container.iconSource ? `图标：${container.iconSource === 'builtin' ? '内置' : '自定义'}${container.iconKey ? ` · ${container.iconKey}` : ''}` : '未匹配图标'">
                  <img v-if="container.containerIcon" :src="container.containerIcon" :alt="`${container.name} 图标`" />
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
                  <button v-if="port.accessMode === 'web'" type="button" title="加入服务导航" @click.stop="addDockerNavigation(container, port)"><Compass :size="15" />加入导航</button>
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
            <div v-if="!dockerContainers.length" class="empty" role="status">
              <template v-if="dockerListLoading">正在读取 Docker 容器…</template>
              <template v-else-if="(dockerData.containers || []).length"><strong>没有匹配的容器</strong><button type="button" @click="dockerSearch = ''">清空搜索</button></template>
              <template v-else><strong>尚未发现 Docker 容器</strong><span>在常用设置中开启 Docker 自动发现；已开启时可重新获取列表。</span><button type="button" @click="setView('settings'); settingsSection = 'runtime'">查看 Docker 自动发现</button><button type="button" @click="refreshDocker(true)">重新获取</button></template>
            </div>
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
          <div class="monitor-stat"><span>流量规则</span><strong>{{ statusRules.filter((item) => item.enabled).length }}<small>/{{ statusRules.length }}</small></strong><p>启用规则</p></div>
          <div class="monitor-stat"><span>容器保护</span><strong>{{ statusContainerRules.filter((item) => item.enabled).length }}<small>/{{ statusContainerRules.length }}</small></strong><p>监控中</p></div>
          <div class="monitor-stat"><span>通知渠道</span><strong>{{ statusChannels.filter((item) => item.enabled).length }}<small>/{{ statusChannels.length }}</small></strong><p>可用渠道</p></div>
          <div class="monitor-stat"><span>最近告警</span><strong>{{ overview?.alerts?.length || 0 }}</strong><p>当前缓存</p></div>
        </div>
        <section class="card monitor-section">
          <CardHead title="规则状态" meta="点击展开查看条件；编辑请进入设置">
            <button type="button" @click="setView('settings')"><Settings :size="16" />配置</button>
          </CardHead>
          <div class="accordion-stack monitor-stack">
            <article v-stack-motion v-for="rule in statusRules" :key="`status-${rule.id}`" :class="['monitor-status-card', { expanded: isMonitorCardExpanded('status-traffic', rule.id) }]">
              <button class="monitor-card-trigger" type="button" @click="toggleMonitorCard('status-traffic', rule.id)">
                <span class="monitor-card-icon"><Bell :size="17" /></span>
                <span class="monitor-card-copy"><strong>{{ rule.name || "未命名规则" }}</strong><small>{{ monitorRuleSummary(rule) }}</small></span>
                <span :class="['rule-state', rule.enabled ? 'enabled' : 'disabled']"><component :is="rule.enabled ? CheckCircle2 : CircleOff" :size="14" />{{ rule.enabled ? "启用" : "停用" }}</span>
                <component :is="isMonitorCardExpanded('status-traffic', rule.id) ? ChevronUp : ChevronDown" :size="18" />
              </button>
              <div v-if="isMonitorCardExpanded('status-traffic', rule.id)" class="monitor-card-body">
                <span>指标：{{ metricLabels[rule.metric] || rule.metric }}</span><span>阈值：{{ formatMonitorThreshold(rule) }}</span><span>持续：{{ rule.durationSeconds || 0 }} 秒</span><span>渠道：{{ ruleNotificationSummary(rule) }}</span>
              </div>
            </article>
            <div v-if="!statusRules.length" class="empty card-empty">暂无流量监控规则</div>
          </div>
        </section>
        <section class="card monitor-section">
          <CardHead title="容器保护状态" meta="只在设定条件持续达到阈值后执行动作">
            <button type="button" @click="setView('settings')"><Settings :size="16" />配置</button>
          </CardHead>
          <div class="accordion-stack monitor-stack">
            <article v-stack-motion v-for="rule in statusContainerRules" :key="`status-container-${rule.id}`" :class="['monitor-status-card', { expanded: isMonitorCardExpanded('status-container', rule.id) }]">
              <button class="monitor-card-trigger" type="button" @click="toggleMonitorCard('status-container', rule.id)">
                <span class="monitor-card-icon protection"><ShieldCheck :size="17" /></span>
                <span class="monitor-card-copy"><strong>{{ rule.name || "未命名容器保护" }}</strong><small>{{ containerProtectionSummary(rule) }}</small></span>
                <span :class="['rule-state', rule.enabled ? 'enabled' : 'disabled']"><component :is="rule.enabled ? ShieldCheck : CircleOff" :size="14" />{{ rule.enabled ? "监控中" : "停用" }}</span>
                <component :is="isMonitorCardExpanded('status-container', rule.id) ? ChevronUp : ChevronDown" :size="18" />
              </button>
              <div v-if="isMonitorCardExpanded('status-container', rule.id)" class="monitor-card-body"><span>条件：{{ rule.conditions?.length || 0 }} 条 / {{ rule.logic === "or" ? "任一条件" : "全部条件" }}</span><span>动作：{{ containerProtectionActions.find((item) => item.value === rule.action)?.label || rule.action }}</span><span v-if="rule.action === 'restart'">次数不限</span><span>通知：{{ ruleNotificationSummary(rule) }}</span></div>
            </article>
            <div v-if="!statusContainerRules.length" class="empty card-empty">暂无容器保护规则</div>
          </div>
        </section>
        <section class="card monitor-section">
          <CardHead title="通知渠道状态" meta="渠道配置与模板在设置中维护">
            <button type="button" @click="setView('settings')"><Settings :size="16" />配置</button>
          </CardHead>
          <div class="accordion-stack monitor-stack">
            <article v-stack-motion v-for="channel in statusChannels" :key="`status-channel-${channel.id}`" :class="['monitor-status-card', { expanded: isMonitorCardExpanded('status-channel', channel.id) }]">
              <button class="monitor-card-trigger" type="button" @click="toggleMonitorCard('status-channel', channel.id)">
                <span class="monitor-card-icon channel"><Send :size="17" /></span>
                <span class="monitor-card-copy"><strong>{{ channel.name || "未命名渠道" }}</strong><small>{{ channelTypeLabel(channel.type) }} · {{ channelAddressSummary(channel) }}</small></span>
                <span :class="['rule-state', channel.enabled ? 'enabled' : 'disabled']"><component :is="channel.enabled ? CheckCircle2 : CircleOff" :size="14" />{{ channel.enabled ? "已启用" : "停用" }}</span>
                <component :is="isMonitorCardExpanded('status-channel', channel.id) ? ChevronUp : ChevronDown" :size="18" />
              </button>
              <div v-if="isMonitorCardExpanded('status-channel', channel.id)" class="monitor-card-body"><span>类型：{{ channelTypeLabel(channel.type) }}</span><span>超时：{{ channel.timeout || 5 }} 秒</span><span>模板：{{ channel.bodyTemplate ? "已配置" : "默认" }}</span></div>
            </article>
            <div v-if="!statusChannels.length" class="empty card-empty">暂无通知渠道</div>
          </div>
        </section>

        <section class="card monitor-section upload-diagnostic-card">
          <CardHead title="上传异常记录" :meta="`${alertHistory.length} 条已留存告警证据`">
            <label class="diagnostic-date-control">日期<input v-model="diagnosticDate" type="date" /></label>
            <button type="button" :disabled="diagnosticLoading" @click="refreshUploadDiagnostic"><RefreshCw :size="15" />查询</button>
            <button type="button" :disabled="diagnosticLoading" @click="askAiAboutDiagnostic"><Sparkles :size="15" />AI 排查</button>
          </CardHead>
          <div class="upload-diagnostic-summary">
            <div><span>当日公网下行</span><strong class="rx-text">{{ formatBytes(uploadDiagnostic?.totals?.rxBytes) }}</strong></div>
            <div><span>当日公网上行</span><strong class="tx-text">{{ formatBytes(uploadDiagnostic?.totals?.txBytes) }}</strong></div>
            <div><span>关联告警</span><strong>{{ uploadDiagnostic?.alerts?.length || 0 }}</strong></div>
          </div>
          <div class="diagnostic-grid">
            <div class="diagnostic-panel">
              <h4>上传进程</h4>
              <div v-for="item in uploadDiagnostic?.topProcesses || []" :key="`${item.pid}-${item.name}`" class="diagnostic-row">
                <span><strong>{{ item.container?.label || item.container?.name || item.name || "unknown" }}</strong><small>PID {{ item.pid ?? "-" }}</small></span>
                <b class="tx-text">↑ {{ formatBytes(item.txBytes) }}</b>
              </div>
              <div v-if="!uploadDiagnostic?.topProcesses?.length" class="empty compact">该日没有进程聚合数据</div>
              <p class="diagnostic-note">历史进程为抓包可见的总流量参考；公网网卡总量为判定依据。</p>
            </div>
            <div class="diagnostic-panel">
              <h4>公网网卡</h4>
              <div v-for="item in uploadDiagnostic?.topInterfaces || []" :key="item.iface" class="diagnostic-row">
                <strong>{{ item.iface }}</strong><span>↓ {{ formatBytes(item.rxBytes) }} / <b class="tx-text">↑ {{ formatBytes(item.txBytes) }}</b></span>
              </div>
              <div v-if="!uploadDiagnostic?.topInterfaces?.length" class="empty compact">该日没有公网网卡数据</div>
            </div>
          </div>
          <div class="alert-evidence-list">
            <article v-for="alert in uploadDiagnostic?.alerts || []" :key="alert.id" class="alert-evidence-item">
              <div class="alert-evidence-head"><span><Bell :size="15" /><strong>{{ alert.message }}</strong></span><time>{{ formatDate(alert.timestamp) }}</time></div>
              <p>{{ alert.evidence?.reason || `${formatMonitorMetricValue(alert.value, alert.type)} / 阈值 ${formatMonitorMetricValue(alert.threshold, alert.type)}` }}</p>
              <div class="notification-results"><span>通知投递</span><b v-for="delivery in alert.notifications || []" :key="`${delivery.channelId}-${delivery.timestamp}`" :class="delivery.skipped ? 'delivery-muted' : delivery.ok ? 'delivery-ok' : 'delivery-failed'">{{ delivery.skipped ? '已关闭通知，仅保留记录' : `${delivery.channelName || delivery.channelId || '未匹配渠道'}：${delivery.ok ? '成功' : delivery.detail || '失败'}` }}</b><em v-if="!alert.notifications?.length">旧记录无投递回执</em></div>
            </article>
            <div v-if="uploadDiagnostic && !uploadDiagnostic.alerts?.length" class="empty diagnostic-empty">该日期没有已保存的告警。旧版本不会保存通知回执，因此无法反查当时是否投递失败。</div>
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
            <div>
              <div class="ai-mode-tabs" role="tablist" aria-label="AI 工作模式">
                <button type="button" :class="{ active: aiMode === 'analysis' }" @click="aiMode = 'analysis'"><Sparkles :size="14" />数据分析</button>
                <button type="button" :class="{ active: aiMode === 'configure' }" @click="aiMode = 'configure'"><Settings :size="14" />设置助手</button>
              </div>
              <strong>{{ aiMode === "configure" ? "设置助手" : "数据对话" }}</strong>
              <span>{{ aiMode === "configure" ? "用一句话描述目标，AI 生成预览后一次确认应用" : "上下文为聚合摘要，不发送完整连接原始表" }}</span>
            </div>
            <div v-if="aiMode === 'analysis'" class="card-actions">
              <button type="button" :disabled="aiLoading" @click="analyzeWithAi('all')"><Sparkles :size="15" />快速分析全部数据</button>
              <button type="button" class="subtle-button" :disabled="aiLoading || !aiMessages.length" @click="clearAiHistory"><Trash2 :size="15" />清空记录</button>
            </div>
          </div>
          <div v-if="aiMode === 'analysis'" class="ai-messages" aria-live="polite">
            <div v-if="!aiMessages.length" class="ai-empty"><Sparkles :size="24" /><strong>从一个问题开始</strong><span>例如：最近公网上传是否异常？哪个进程最值得关注？</span></div>
            <div v-for="(message, index) in aiMessages" :key="`${message.role}-${index}`" :class="['ai-message', message.role === 'user' ? 'user' : 'assistant']">
              <span class="ai-message-avatar"><UserRound v-if="message.role === 'user'" :size="15" /><Sparkles v-else :size="15" /></span>
              <div><small>{{ message.role === 'user' ? "你" : "AI 分析助手" }}</small><p v-if="message.role === 'user'">{{ message.content }}</p><p v-else-if="message.streaming" class="ai-streaming-text">{{ message.content }}</p><div v-else class="ai-markdown" v-html="renderMarkdown(message.content)"></div><em v-if="message.truncated" class="ai-message-warning">本次回答未完整结束</em></div>
            </div>
            <div v-if="aiLoading" class="ai-message assistant"><span class="ai-message-avatar"><Sparkles :size="15" /></span><div><small>AI 分析助手</small><p class="ai-thinking">正在读取统计摘要<span>·</span><span>·</span><span>·</span></p></div></div>
          </div>
          <p v-if="aiError" class="ai-error"><CircleAlert :size="15" />{{ aiError }}</p>
          <p v-if="aiWarning" class="ai-warning"><CircleAlert :size="15" />{{ aiWarning }}</p>
          <form v-if="aiMode === 'analysis'" class="ai-composer" @submit.prevent="sendAiChat">
            <textarea v-model="aiInput" rows="2" maxlength="2000" placeholder="输入你想分析的问题，例如：按公网上传排序，给出前 3 个风险来源" @keydown="handleAiComposerKeydown"></textarea>
            <button type="submit" :disabled="aiLoading || !aiInput.trim()"><Send :size="16" />发送</button>
          </form>
          <div v-else class="ai-configure-panel">
            <form class="ai-configure-form" @submit.prevent="requestAiConfiguration">
              <label class="textarea-label">告诉 AI 你想怎么设置<textarea v-model="aiConfigureInput" rows="4" maxlength="2000" placeholder="例如：把采样间隔改为 2 秒，并开启 Docker 自动发现"></textarea></label>
              <div class="ai-configure-actions">
                <span class="muted">敏感凭据、密码、Token、路径和宿主命令不会由 AI 修改。</span>
                <button type="submit" :disabled="aiConfigureLoading || !aiConfigureInput.trim()"><Sparkles :size="16" />{{ aiConfigureLoading ? "生成中" : "生成配置预览" }}</button>
              </div>
            </form>
            <p v-if="aiConfigureError" class="ai-error"><CircleAlert :size="15" />{{ aiConfigureError }}</p>
            <section v-if="aiConfigureProposal" class="ai-proposal" aria-live="polite">
              <div class="ai-proposal-head"><div><strong>配置变更预览</strong><span>确认后才会写入 SQLite · {{ formatDate(aiConfigureProposal.expiresAt) }} 过期</span></div><ShieldCheck :size="20" /></div>
              <div class="ai-proposal-list">
                <article v-for="change in aiConfigureProposal.changes || []" :key="change.path" class="ai-proposal-change">
                  <div class="ai-proposal-change-head"><code>{{ change.path }}</code><span :class="['risk-badge', change.risk === '高' || change.risk === 'high' ? 'high' : 'low']">风险 {{ change.risk || "低" }}</span></div>
                  <p>{{ change.summary }}</p>
                  <p v-if="change.removeIds?.length" class="ai-warning">将删除：{{ change.removeIds.join('、') }}</p>
                  <div class="ai-proposal-values"><span><small>原值</small><b>{{ formatConfigValue(change.oldValue) }}</b></span><ArrowRight :size="15" /><span><small>{{ Array.isArray(change.newValue) || change.path === 'docker.containers' ? '新增或更新的条目' : '新值' }}</small><b>{{ formatConfigValue(change.newValue) }}</b></span></div>
                </article>
              </div>
              <div class="ai-proposal-actions"><button type="button" class="subtle-button" :disabled="aiConfigureLoading" @click="cancelAiConfiguration"><X :size="16" />取消变更</button><button type="button" :disabled="aiConfigureLoading" @click="applyAiConfiguration"><CheckCircle2 :size="16" />{{ aiConfigureLoading ? "应用中" : "确认应用" }}</button></div>
            </section>
          </div>
        </section>
      </section>

      <section v-if="activeView === 'settings'" class="view settings-workspace" :aria-busy="settingsLoading">
        <nav class="settings-tabs" aria-label="设置功能分区">
          <button v-for="section in settingsSections" :key="section.key" type="button" class="settings-tab" :class="{ active: settingsSection === section.key }" :aria-current="settingsSection === section.key ? 'page' : undefined" @click="settingsSection = section.key">
            {{ section.label }}<span v-if="sectionDirty(section.key)" aria-label="有未保存修改">•</span>
          </button>
        </nav>
        <div v-if="!settings" class="empty" role="status">正在读取当前设置…</div>
        <div v-else class="settings-toolbar">
          <p>{{ currentSettingsDescription }}</p>
          <span v-if="sectionDirty(settingsSection)" class="settings-unsaved" role="status">有未保存的修改</span>
          <span v-else class="muted">当前设置已同步</span>
          <button v-if="sectionDirty(settingsSection)" type="button" :disabled="settingsSaving[currentSettingsGroup]" @click="discardSettingsDraft">放弃当前修改</button>
        </div>
        <p v-if="settingsErrors[currentSettingsGroup]" class="settings-feedback error" role="alert">{{ settingsErrors[currentSettingsGroup] }}</p>
        <section v-if="settings && settingsSection === 'maintenance'" class="card">
          <CardHead title="历史数据维护" meta="清理流量历史，保留规则、渠道、图标、AI 对话和告警证据">
            <button type="button" class="danger" @click="clearTrafficHistory"><Trash2 :size="16" />清理流量历史</button>
          </CardHead>
        </section>
        <section v-if="settings && settingsSection === 'maintenance'" class="card">
          <CardHead title="告警记录维护" meta="清理会删除全部告警、异常证据和通知回执，请先确认不再需要。"><button type="button" class="danger" @click="clearAlerts">清除全部告警记录</button></CardHead>
        </section>
        <div v-if="settings && ['runtime', 'maintenance'].includes(settingsSection)" class="grid">
          <section v-if="settingsSection === 'runtime'" class="card">
          <fieldset class="settings-fields" :disabled="settingsSaving.runtime" :aria-busy="settingsSaving.runtime">
            <CardHead title="运行参数" meta="可热更新项会写入 SQLite">
              <button type="button" class="primary-button" :disabled="settingsSaving.runtime" @click="saveRuntime"><Save :size="16" />{{ settingsSaving.runtime ? '保存中…' : '保存常用设置' }}</button>
            </CardHead>
            <div class="form-grid">
              <label>流量采样间隔（秒）<input v-model.number="runtimeForm.sampleSeconds" type="number" min="0.5" step="0.5" /></label>
              <label>短期缓存保留（秒）<input v-model.number="runtimeForm.retentionSeconds" type="number" min="60" /></label>
              <label>统计保存间隔（秒）<input v-model.number="runtimeForm.persistIntervalSeconds" type="number" min="10" /></label>
              <label>流量历史保留（天）<input v-model.number="runtimeForm.historyRetentionDays" type="number" min="1" /></label>
              <div class="field-block">
                <span>Docker 自动发现</span>
                <label class="switch"><input v-model="runtimeForm.dockerDiscovery" type="checkbox" />启用</label>
              </div>
              <div class="field-block">
                <span>阶段统计</span>
                <label class="switch"><input v-model="runtimeForm.autoStartStage" type="checkbox" />自动启动</label>
              </div>
            </div>
            <details class="advanced-fields"><summary>连接采集高级设置</summary><div class="form-grid"><label>活跃连接判断窗口（秒）<input v-model.number="runtimeForm.connectionActiveSeconds" type="number" min="10" /></label><label>连接记录保留（秒）<input v-model.number="runtimeForm.connectionRetentionSeconds" type="number" min="60" /></label><label>宿主连接表刷新间隔（秒）<input v-model.number="runtimeForm.conntrackRefreshSeconds" type="number" :min="settings?.runtime?.minConntrackRefreshSeconds || 15" /></label></div></details>
                    </fieldset>
</section>

          <section v-if="settingsSection === 'maintenance'" class="card">
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

        <section v-if="settings && settingsSection === 'ai'" class="card settings-ai-card">
          <fieldset class="settings-fields" :disabled="settingsSaving.ai" :aria-busy="settingsSaving.ai">
          <CardHead title="AI 分析配置" meta="只在点击分析或发送对话时请求，不参与后台采集">
            <span :class="['rule-state', aiForm.enabled && aiForm.keyConfigured ? 'enabled' : 'disabled']"><component :is="aiForm.enabled && aiForm.keyConfigured ? CheckCircle2 : CircleOff" :size="14" />{{ aiForm.enabled && aiForm.keyConfigured ? "可用" : "未配置" }}</span>
            <button type="button" class="primary-button" :disabled="settingsSaving.ai" @click="saveAiSettings"><Save :size="16" />{{ settingsSaving.ai ? '保存中…' : '保存AI 配置' }}</button>
          </CardHead>
          <div class="form-grid ai-form-grid">
            <div class="field-block"><span>启用 AI 分析</span><label class="switch"><input v-model="aiForm.enabled" type="checkbox" />允许按需请求</label></div>
            <label>AI 厂商<select v-model="aiForm.provider" @change="applyAiProviderPreset"><option v-for="provider in providerPresets" :key="provider.value" :value="provider.value">{{ provider.label }}</option></select></label>
            <label>Base URL<input v-model="aiForm.baseUrl" type="url" placeholder="https://api.openai.com/v1" /></label>
            <label>API Key<input v-model="aiForm.apiKey" type="password" autocomplete="off" :placeholder="aiForm.keyConfigured ? aiForm.apiKeyMasked : '填写后保存，前端只显示掩码'" /></label>
            <div class="field-block">
              <span>模型</span>
              <select v-if="aiModels.length" v-model="aiModelChoice" aria-label="选择 AI 模型"><option v-for="model in aiModels" :key="model.id" :value="model.id">{{ model.name || model.id }}</option><option value="__manual__">手动填写其他型号</option></select>
              <input v-if="aiModelChoice === '__manual__'" v-model="aiForm.model" aria-label="手动填写 AI 模型" placeholder="输入服务提供方给出的模型名称" />
              <button type="button" class="subtle-button" :disabled="aiModelsLoading || settingsSaving.ai" @click="readAiModels"><RefreshCw :size="15" />{{ aiModelsLoading ? "读取中…" : "读取模型列表" }}</button>
              <p class="field-hint">读取列表不会修改已选型号；列表不可用时可手动填写。</p>
            </div>
            <label>请求超时秒<input v-model.number="aiForm.timeoutSeconds" type="number" min="5" max="180" /></label>
            <label>最大输出 Token<input v-model.number="aiForm.maxTokens" type="number" min="128" max="393216" /></label>
            <label class="textarea-label wide">系统提示词<textarea v-model="aiForm.systemPrompt" rows="3" placeholder="定义 AI 分析时的角色和关注点"></textarea></label>
          </div>
          <p v-if="aiModelsError" class="settings-security-note"><CircleAlert :size="15" />{{ aiModelsError }}，仍可手动填写模型。</p>
          <p class="settings-security-note"><ShieldCheck :size="15" /> API Key 只保存在 SQLite，不会回显到页面，也不会写入日志；Base URL 仅允许 HTTP/HTTPS。</p>
                  </fieldset>
</section>

        <section v-if="settings && settingsSection === 'monitor'" class="card">
          <fieldset class="settings-fields" :disabled="settingsSaving.monitor" :aria-busy="settingsSaving.monitor">
          <CardHead title="监控规则" :meta="`${monitorRules.length} 条 · 支持多规则多渠道`">
            <button type="button" @click="addRule"><Plus :size="16" />新增</button>
            <button type="button" class="primary-button" :disabled="settingsSaving.monitor" @click="saveRules"><Save :size="16" />{{ settingsSaving.monitor ? '保存中…' : '保存流量告警' }}</button>
          </CardHead>
          <div class="rule-grid accordion-stack">
            <div v-stack-motion v-for="rule in monitorRules" :key="rule.id" :class="['edit-card', 'collapsible-card', { expanded: isMonitorCardExpanded('traffic', rule.id) }]">
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
                  <label>指标<select v-model="rule.metric" @change="resetThresholdUnit(rule)"><option v-for="(label, key) in metricLabels" :key="key" :value="key">{{ label }}</option></select></label>
                  <label>触发条件<select v-model="rule.operator"><option value="gte">达到或高于阈值</option><option value="lte">达到或低于阈值</option></select></label>
                  <label>阈值<span class="threshold-control"><input v-model.number="rule.thresholdValue" type="number" min="0" step="0.01" /><select v-if="thresholdUnitOptions(rule.metric).length > 1" v-model="rule.thresholdUnit"><option v-for="unit in thresholdUnitOptions(rule.metric)" :key="unit" :value="unit">{{ unit }}</option></select><em v-else>{{ rule.thresholdUnit || "次" }}</em></span></label>
                  <label>持续时间（秒）<input v-model.number="rule.durationSeconds" type="number" min="0" /></label>
                  <p class="field-hint wide">{{ rule.metric === 'daily_wan_tx_bytes' ? '按服务器时区当天 00:00 起的公网上传量判断，每条规则每天最多报警一次；次日重新计算。' : rule.metric === 'stage_wan_tx_bytes' ? '按手动开始的阶段累计上传量判断，阶段不会在午夜自动清零。' : '按实时速率或连接数判断。' }}</p>
                  <div class="field-block wide">
                    <label>通知方式<select v-model="rule.channelMode"><option value="all">全部启用的渠道</option><option value="selected">指定通知渠道</option><option value="none">不发送通知，仅记录告警</option></select></label>
                    <div v-if="rule.channelMode === 'selected'" class="channel-checks">
                      <label v-for="channel in channels" :key="channel.id" class="check-chip"><input :checked="rule.channelIds?.includes(channel.id)" type="checkbox" @change="toggleRuleChannel(rule, channel.id)" />{{ channel.name }}{{ channel.enabled ? '' : '（未启用）' }}</label>
                      <span v-if="!channels.length" class="field-hint">还没有通知渠道，请先到“通知渠道”添加。</span>
                    </div>
                  </div>
                </div>
                <button class="danger" type="button" @click="removeRule(rule.id)"><Trash2 :size="16" />删除规则</button>
              </div>
            </div>
            <div v-if="!monitorRules.length" class="empty card-empty">暂无流量监控规则</div>
          </div>
                  </fieldset>
</section>

        <section v-if="settings && settingsSection === 'protection'" class="card">
          <fieldset class="settings-fields" :disabled="settingsSaving.protection" :aria-busy="settingsSaving.protection">
          <CardHead title="容器保护" :meta="`${containerRules.length} 条 · 监控触发后可复用现有告警渠道`">
            <button type="button" @click="addContainerRule"><Plus :size="16" />新增</button>
            <button type="button" class="primary-button" :disabled="settingsSaving.protection" @click="saveContainerRules"><Save :size="16" />{{ settingsSaving.protection ? '保存中…' : '保存容器保护' }}</button>
          </CardHead>
          <div class="rule-grid accordion-stack">
            <div v-stack-motion v-for="rule in containerRules" :key="rule.id" :class="['edit-card', 'collapsible-card', { expanded: isMonitorCardExpanded('container', rule.id) }]">
              <div class="edit-title card-summary-row">
                <button class="collapse-toggle" type="button" :aria-expanded="isMonitorCardExpanded('container', rule.id)" @click="toggleMonitorCard('container', rule.id)">
                  <component :is="isMonitorCardExpanded('container', rule.id) ? ChevronUp : ChevronDown" :size="16" />
                  <span>
                    <strong>{{ rule.name || "未命名容器保护" }}</strong>
                    <small>{{ containerProtectionSummary(rule) }}</small>
                  </span>
                </button>
                <div class="summary-actions">
                  <span :class="['rule-state', rule.enabled && !protectionState(rule).locked ? 'enabled' : 'disabled']">
                    <component :is="protectionState(rule).locked ? CircleAlert : rule.enabled ? ShieldCheck : CircleOff" :size="14" />{{ protectionRuleStatus(rule) }}
                  </span>
                </div>
              </div>
              <div v-if="isMonitorCardExpanded('container', rule.id)" class="card-editor">
                <div class="form-grid mini">
                <label>规则名称<input v-model="rule.name" placeholder="规则名称" /></label>
                <div class="field-block"><span>状态</span><label class="switch"><input v-model="rule.enabled" type="checkbox" />启用</label></div>
                <label>保护范围<select :value="rule.targetMode" @change="switchProtectionScope(rule, $event.target.value)"><option value="single">单个容器</option><option value="selected">选择多个容器</option><option value="all">全部运行中容器</option></select></label>
                <div v-if="rule.targetMode !== 'all'" class="field-block wide">
                  <span>选择保护容器</span>
                  <ContainerPicker :model-value="selectionForRule(rule)" :containers="dockerData.containers || []"
                    :multiple="rule.targetMode === 'selected'" :loading="containerOptionsLoading" :error="containerOptionsError"
                    @update:model-value="applyContainerSelection(rule, $event)" @refresh="refreshDockerContainerOptions(true)" />
                </div>
                <p v-else class="field-hint wide">自动保护所有运行中的容器，后续新增容器也会纳入。每个容器独立判断阈值。</p>
                <label>触发方式<select v-model="rule.logic"><option v-for="item in containerProtectionLogicOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                <label>达到条件后<select v-model="rule.action"><option v-for="item in containerProtectionActions" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                <label>动作后等待（秒）<input v-model.number="rule.cooldownSeconds" type="number" min="0" /></label>
                <p v-if="rule.action === 'restart'" class="field-hint wide">重启次数不限。每次达到占用阈值并满足持续时间后重启该容器，冷却结束后继续监控。</p>
                <div class="field-block wide">
                  <span>保护记录：{{ protectionState(rule).count || 0 }} 次重启尝试 · {{ protectionState(rule).locked ? '已锁定' : rule.enabled ? '监控中' : '停用' }}</span>
                  <p class="field-hint">{{ protectionState(rule).reason || '累计次数仅作记录，重启次数不限。' }}</p>
                  <p v-if="protectionState(rule).monitorReason" class="field-hint">{{ protectionState(rule).monitorReason }}</p>
                  <div v-if="rule.targetMode !== 'single'" class="protection-target-states">
                    <div v-for="(state, key) in protectionState(rule).containers || {}" :key="key">
                      <strong>{{ state.containerName || state.containerId }}</strong><span>{{ protectionStatusLabel(state.monitorStatus) }} · {{ state.count || 0 }} 次</span>
                      <small>{{ state.monitorReason || protectionMetricSummary(state) || state.reason || '等待采样' }}</small>
                    </div>
                  </div>
                  <button type="button" @click="resetProtection(rule)"><RotateCcw :size="15" />重置计数并解除锁定</button>
                </div>
                <div class="field-block wide">
                  <label>通知方式<select v-model="rule.channelMode"><option value="all">全部启用的渠道</option><option value="selected">指定通知渠道</option><option value="none">不发送通知，仅记录告警</option></select></label>
                  <div v-if="rule.channelMode === 'selected'" class="channel-checks">
                    <label v-for="channel in channels" :key="channel.id" class="check-chip"><input :checked="rule.channelIds?.includes(channel.id)" type="checkbox" @change="toggleContainerRuleChannel(rule, channel.id)" />{{ channel.name }}{{ channel.enabled ? '' : '（未启用）' }}</label>
                    <span v-if="!channels.length" class="field-hint">还没有通知渠道，请先到“通知渠道”添加。</span>
                  </div>
                </div>
                <div class="field-block wide">
                  <span>条件</span>
                  <div class="condition-list">
                    <div v-for="(condition, index) in rule.conditions || []" :key="`${rule.id}-${index}`" class="condition-row">
                      <label>指标<select v-model="condition.metric" @change="resetProtectionThreshold(condition)"><option v-for="(label, key) in containerProtectionMetricLabels" :key="key" :value="key">{{ label }}</option></select></label>
                      <label>比较<select v-model="condition.operator"><option v-for="item in containerProtectionOperators" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
                      <label>阈值<span class="threshold-control"><input v-model.number="condition.thresholdValue" type="number" min="0" step="0.01" /><select v-if="protectionUnitOptions(condition.metric).length > 1" v-model="condition.thresholdUnit"><option v-for="unit in protectionUnitOptions(condition.metric)" :key="unit" :value="unit">{{ unit }}</option></select><em v-else>%</em></span></label>
                      <label>持续时间（秒）<input v-model.number="condition.durationSeconds" type="number" min="0" /></label>
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
                  </fieldset>
</section>

        <section v-if="settings && settingsSection === 'channels'" class="card">
          <fieldset class="settings-fields" :disabled="settingsSaving.channels" :aria-busy="settingsSaving.channels">
          <CardHead title="通知渠道" :meta="`${channels.length} 个 · Webhook / IYUU / MeoW`">
            <button type="button" @click="addChannel"><Plus :size="16" />新增</button>
            <button type="button" class="primary-button" :disabled="settingsSaving.channels" @click="saveChannels"><Save :size="16" />{{ settingsSaving.channels ? '保存中…' : '保存通知渠道' }}</button>
          </CardHead>
          <div class="channel-grid accordion-stack">
            <div v-stack-motion v-for="channel in channels" :key="channel.id" :class="['edit-card', 'channel-card', 'collapsible-card', { expanded: isMonitorCardExpanded('channel', channel.id) }]">
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
                <label>{{ channel.type === 'webhook' ? 'Webhook 通知地址' : '自定义服务地址（可选）' }}<input v-model="channel.url" type="url" :placeholder="channel.type === 'webhook' ? 'https://…' : '留空使用服务商默认地址'" /></label>
                <label v-if="channel.type !== 'webhook'">{{ channel.type === 'iyuu' ? 'IYUU Token' : 'MeoW 昵称' }}<input v-model="channel.token" :type="channel.type === 'iyuu' ? 'password' : 'text'" autocomplete="off" placeholder="IYUU token 或 MeoW 昵称" /></label>
              </div>
                <details class="advanced-fields"><summary>消息模板与高级选项</summary>
                  <label>跳转 URL 模板<input v-model="channel.urlTemplate" placeholder="可用 {rule_id} 等变量" /></label>
                  <label v-if="channel.msgType === 'html'">HTML 高度（像素）<input v-model.number="channel.htmlHeight" type="number" min="100" max="1200" /></label>
                  <label>消息类型<select v-model="channel.msgType"><option value="text">普通文本</option><option value="html">HTML 消息</option></select></label>
                  <label>超时秒<input v-model.number="channel.timeout" type="number" min="1" max="30" /></label>
                <div class="template-help">
                <span>可用变量：</span>
                <code v-for="item in templateVariables" :key="templateKey(item)">{{ templateVar(templateKey(item)) }} · {{ templateLabel(item) }}</code>
                </div>
                <label class="textarea-label">标题模板<textarea v-model="channel.titleTemplate" rows="2"></textarea></label>
                <label class="textarea-label">正文模板<textarea v-model="channel.bodyTemplate" rows="5"></textarea></label>
                </details>
                <div class="edit-actions">
                  <button type="button" :disabled="!!testingChannel || settingsSaving.channels" @click="testChannel(channel.id)"><Send :size="16" />{{ testingChannel === channel.id ? '发送中…' : '保存渠道并发送测试通知' }}</button>
                  <button class="danger" type="button" @click="removeChannel(channel.id)"><Trash2 :size="16" />删除</button>
                </div>
              </div>
            </div>
            <div v-if="!channels.length" class="empty card-empty">暂无通知渠道</div>
          </div>
                  </fieldset>
</section>
      </section>
    </main>

    <dialog ref="connectionDialog" class="modal" @close="stopConnectionTimer">
      <div class="modal-box">
        <CardHead title="连接与端口" :meta="`${connPagination.total || 0} 条筛选结果`">
          <span class="connection-status" :role="connectionError ? 'alert' : 'status'">{{ connectionError || (connLoading ? '更新中' : '') }}</span>
          <button type="button" @click="connectionDialog?.close()"><X :size="16" />关闭</button>
        </CardHead>
        <div class="connection-filters">
          <label>数据来源<select v-model="connFilters.mode" @change="refreshConnections(true)"><option value="capture">抓包归因</option><option value="conntrack">路由器口径</option></select></label>
          <label>网卡<select v-model="connFilters.iface" @change="refreshConnections(true)"><option value="all">全部网卡</option><option v-for="name in interfaceNames" :key="name" :value="name">{{ name }}</option></select></label>
          <label>网络范围<select v-model="connFilters.scope" @change="refreshConnections(true)"><option value="all">全部范围</option><option value="wan">公网</option><option value="lan">内网</option></select></label>
          <label>连接协议<select v-model="connFilters.proto" @change="refreshConnections(true)"><option value="all">全部协议</option><option value="tcp">TCP</option><option value="udp">UDP</option></select></label>
          <label>流量方向<select v-model="connFilters.direction" @change="refreshConnections(true)"><option value="all">全部方向</option><option value="rx">下行</option><option value="tx">上行</option></select></label>
          <label>源地址 / 端口<input v-model="connFilters.source" placeholder="源 IP/端口" @input="debounceConnections" /></label>
          <label>目标地址 / 端口<input v-model="connFilters.dest" placeholder="目标 IP/端口" @input="debounceConnections" /></label>
          <label>进程或容器名称<input v-model="connFilters.owner" placeholder="进程/容器" @input="debounceConnections" /></label>
          <label>最小流量（MB）<input v-model.number="connFilters.minBytes" type="number" min="0" placeholder="最小 MB" @input="debounceConnections" /></label>
          <label>最短连接时间（秒）<input v-model.number="connFilters.minDuration" type="number" min="0" placeholder="最小秒" @input="debounceConnections" /></label>
          <button type="button" @click="resetConnectionFilters">重置筛选</button>
          <button type="button" @click="refreshConnections(false)"><RefreshCw :size="16" />刷新</button>
        </div>
        <div class="table-wrap modal-table" :aria-busy="connLoading">
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

    <dialog ref="dockerEditDialog" class="modal narrow" @cancel.prevent="requestCloseDockerEditor" @click="event => { if (event.target === dockerEditDialog) requestCloseDockerEditor(); }">
      <div class="modal-box">
        <CardHead title="快捷访问与图标" :meta="dockerEditor.name || '-'">
          <button type="button" :disabled="dockerEditSaving" @click="requestCloseDockerEditor"><X :size="16" />关闭</button>
        </CardHead>
        <p class="field-hint">这里维护快捷访问入口，不会修改 Docker 的实际端口映射。</p>
        <p v-if="dockerEditError" class="settings-feedback error" role="alert">{{ dockerEditError }}</p>
        <fieldset class="docker-editor" :disabled="dockerEditSaving">
          <div class="icon-editor">
            <div class="docker-icon large">
              <img v-if="dockerEditor.icon || dockerEditor.iconKey" :src="dockerEditor.icon || dockerIconByKey(dockerEditor.iconKey)" alt="" />
              <Server v-else :size="28" />
            </div>
            <label>内置图标<select v-model="dockerEditor.iconKey" @change="dockerEditor.icon = ''"><option value="">自动匹配</option><option v-for="icon in dockerIcons" :key="icon.key" :value="icon.key">{{ icon.label }}</option></select></label>
            <label class="file-button">
              <ImagePlus :size="16" />上传图标
              <input type="file" accept="image/png,image/jpeg,image/webp" @change="uploadDockerIcon" />
            </label>
            <button type="button" @click="dockerEditor.icon = ''; dockerEditor.iconKey = ''">清除</button>
          </div>
          <div class="port-editor-list">
            <div v-for="(port, index) in dockerEditor.ports" :key="index" class="port-editor">
              <label>协议<select v-model="port.proto"><option value="tcp">TCP</option><option value="udp">UDP</option></select></label>
              <label>NAS 访问端口<input v-model.number="port.hostPort" type="number" min="1" max="65535" /></label>
              <label>容器内部端口<input v-model.number="port.containerPort" type="number" min="1" max="65535" /></label>
              <label>服务类型<select v-model="port.service"><option value="">自动识别</option><option value="web">网页服务</option><option value="redis">Redis</option><option value="mysql">MySQL</option><option value="postgresql">PostgreSQL</option><option value="ssh">SSH</option><option value="other">其他服务</option><option v-if="port.service && !['web','redis','mysql','postgresql','ssh','other'].includes(port.service)" :value="port.service">{{ port.service }}</option></select></label>
              <label>访问方式<select v-model="port.accessMode"><option value="copy">复制地址</option><option value="web">Web 打开</option><option value="hidden">隐藏快捷操作</option></select></label>
              <label v-if="port.accessMode === 'web'">网页协议<select v-model="port.scheme"><option value="http">http</option><option value="https">https</option></select></label>
              <label v-if="port.accessMode === 'web'">网页路径<input v-model="port.path" placeholder="/ 或 /admin" /></label>
              <label>备注<input v-model="port.label" placeholder="如 Redis、QB 管理页" /></label>
              <button class="danger" type="button" @click="removeDockerPort(index)"><Trash2 :size="16" />删除</button>
            </div>
          </div>
          <div class="edit-actions">
            <button type="button" @click="addDockerPort"><Plus :size="16" />添加端口</button>
            <button type="button" class="primary-button" @click="saveDockerPorts"><Save :size="16" />{{ dockerEditSaving ? '保存中…' : '保存访问入口' }}</button>
          </div>
        </fieldset>
      </div>
    </dialog>
    <ConfirmDialog ref="confirmDialog" />
  </div>
</template>

<script setup>
import { computed, defineComponent, h, inject, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { browserTransport } from "./api/transport.js";
import ContainerPicker from "./components/ContainerPicker.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import "./styles/console-theme.css";
import { selectionForRule, applyContainerSelection, switchProtectionScope } from "./utils/container-selection.js";
import { createSettingsDrafts, notificationMode, monitorPayload, validateContainerRules,
  validateMonitorRules, validateChannels, connectionDefaults, validateTimeRange } from "./utils/settings-ux.js";
const transport = inject("trafficTransport", browserTransport);
let disposed = false;
import { createLatestRequest, createPollLoop } from "./utils/requests.js";
import { vStackMotion } from "./utils/stack-motion.js";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { renderMarkdown } from "./utils/markdown.js";
import { temperatureGroupKey, fanCardKey, maxTemperature, hottestTemperatureItem, temperatureLimit,
  temperatureBarWidth, hottestTemperatureGroup, fanPeakRpm,
  fanSpeedBarWidth } from "./utils/system-cards.js";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Bell,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleOff,
  CircleAlert,
  Copy,
  Compass,
  Cpu,
  Database,
  ExternalLink,
  Fan,
  Gauge,
  HardDrive,
  HelpCircle,
  History,
  ImagePlus,
  Menu,
  Moon,
  Pin,
  Monitor,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Send,
  Server,
  ShieldCheck,
  Settings,
  Sparkles,
  Sun,
  Thermometer,
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
  { key: "navigation", label: "导航", icon: Compass },
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
  daily_wan_tx_bytes: "每日公网上传总量（默认）",
  wan_tx_bps: "公网上传速率",
  wan_rx_bps: "公网下载速率",
  lan_tx_bps: "内网上传速率",
  lan_rx_bps: "内网下载速率",
  wan_connections: "公网连接数",
  total_connections: "总连接数",
  stage_wan_tx_bytes: "阶段累计公网上传总量",
};
const transferUnitBytes = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, "B/s": 1, "KB/s": 1024, "MB/s": 1024 ** 2, "GB/s": 1024 ** 3 };
import { providerPresets } from "./utils/ai-providers.js";
import { normalizeProtectionRule, normalizeProtectionCondition, protectionRulePayload, protectionUnitOptions,
  hasProtectionTarget, toggleProtectionTarget, newUploadRule, monitorWindow } from "./utils/container-protection.js";
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
  ["value_human", "可读当前值（如 96.3 GB）"],
  ["threshold_human", "可读阈值（如 50 GB）"],
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
  cpuPercent: "CPU 占用",
  memoryPercent: "内存占用比例",
  memoryUsedBytes: "内存用量",
  blkReadBps: "磁盘读取速度",
  blkWriteBps: "磁盘写入速度",
  blkIoBps: "磁盘总 I/O 速度",
};
const containerProtectionOperators = [
  { value: "gte", label: "大于等于" },
  { value: "lte", label: "小于等于" },
];
const containerProtectionLogicOptions = [
  { value: "and", label: "全部条件满足" },
  { value: "or", label: "任一条件满足" },
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

const props = defineProps({ native: Boolean, view: String, targetName: String, themeMode: String });
const emit = defineEmits(['view', 'toast']);
const activeView = ref(props.view || "overview");
watch(() => props.view, view => { if (view && view !== activeView.value) setView(view); });
watch(() => props.native, () => nextTick(handleResize));
defineExpose({ refresh: refreshActive });
import NavigationView from './components/NavigationView.vue';
import { navigationRepository } from './api/navigation.js';
import { dockerBookmark, navigationIcon, serviceUrl } from './utils/navigation.js';
const bookmarks = navigationRepository(api, transport);
const toast = ref("");
watch(toast, value => emit('toast', value));
const requestError = ref("");
let requestErrorUrl = "";
const theme = ref(localStorage.getItem("ntl-theme") || (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
const menuOpen = ref(false);
const menuPinned = ref(localStorage.getItem("ntl-menu-pinned") === "true");
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
const connectionError = ref("");
const interfaceView = ref("physical");
const ifaceFilter = ref("all");
const historyPeriod = ref("day");
const historyLoading = ref(false);
const historyUpdatedAt = ref(null);
const historyRequest = createLatestRequest();
const connectionRequest = createLatestRequest();
const processRequest = createLatestRequest();
const interfaceRequest = createLatestRequest();
const processPeriod = ref("30s");
const processStart = ref("");
const processEnd = ref("");
const processSearch = ref("");
const dockerSearch = ref("");
const monitorRules = ref([]);
const containerRules = ref([]);
const containerOptionsLoading = ref(false);
const containerOptionsError = ref("");
const settingsLoading = ref(false);
const settingsSection = ref("runtime");
const settingsSaving = reactive({ runtime: false, monitor: false, protection: false, channels: false, ai: false });
const settingsErrors = reactive({});
const settingsDrafts = createSettingsDrafts();
const settingsDraftRevision = ref(0);
const testingChannel = ref("");
const aiModelManual = ref(false);
const processRangeError = ref("");
const appliedProcessRange = ref({ start: "", end: "" });
const processLoading = ref(false);
const interfacesLoading = ref(false);
const dockerListLoading = ref(false);
const dockerEditSaving = ref(false);
const dockerEditError = ref("");
const dockerEditBaseline = ref("");
const settingsSections = [
  { key: "runtime", label: "常用设置", description: "调整流量采样、历史保留和 Docker 自动发现。" },
  { key: "monitor", label: "流量告警", description: "设置上传量、速率或连接数阈值，选择通知方式。" },
  { key: "protection", label: "容器保护", description: "从列表选择容器，达到条件后自动处理。每个容器独立判断。" },
  { key: "channels", label: "通知渠道", description: "配置消息发送位置。发送测试通知前会保存此分区。" },
  { key: "ai", label: "AI 配置", description: "设置服务与模型，仅在主动分析时请求服务。" },
  { key: "maintenance", label: "维护与高级", description: "查看部署参数及维护流量历史。清理历史不会删除配置。" },
];
const currentSettingsGroup = computed(() => settingsSection.value === "maintenance" ? "runtime" : settingsSection.value);
const currentSettingsDescription = computed(() => settingsSections.find(s => s.key === settingsSection.value)?.description || "");
const statusRules = computed(() => settings.value?.monitor?.rules || []);
const statusContainerRules = computed(() => settings.value?.monitor?.containerRules || []);
const statusChannels = computed(() => settings.value?.monitor?.channels || []);
const aiModelChoice = computed({
  get: () => !aiModelManual.value && aiModels.value.some(m => m.id === aiForm.model) ? aiForm.model : "__manual__",
  set: value => { aiModelManual.value = value === "__manual__"; if (!aiModelManual.value) aiForm.model = value; },
});
const channels = ref([]);
const alertHistory = ref([]);
const uploadDiagnostic = ref(null);
const diagnosticDate = ref(new Date().toLocaleDateString("en-CA"));
const diagnosticLoading = ref(false);
const expandedMonitorCards = reactive(new Set());
const expandedDockerCards = reactive(new Set());
const expandedSystemCards = reactive(new Set());
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
const aiMode = ref("analysis");
const aiConfigureInput = ref("");
const aiConfigureProposal = ref(null);
const aiConfigureError = ref("");
const aiConfigureLoading = ref(false);
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
const dockerIcons = ref([]);
const dockerEditor = reactive({ id: "", name: "", icon: "", iconKey: "", ports: [] });
let historyChart = null;
let viewTimer = null;
let connectionTimer = null;
let dockerTimer = null;
let connectionDebounce = null;
let overviewLoading = false;
let systemLoading = false;
let dockerLoading = false;
const handleResize = () => historyChart?.resize();

const connFilters = reactive(connectionDefaults());

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
const systemFans = computed(() => system.value?.fans || []);
const workbenchTiles = computed(() => [
  { key: "docker", label: "Docker", meta: overview.value?.containerStatus?.enabled ? `${overview.value?.containerStatus?.count ?? 0} 个容器` : "容器与端口", icon: Server },
  { key: "monitor", label: "监控中心", meta: "规则与上传异常", icon: Activity },
  { key: "history", label: "历史统计", meta: "今日 / 本周 / 本月流量", icon: History },
  { key: "system", label: "系统状态", meta: "资源、温度与 GPU", icon: Cpu },
  { key: "processes", label: "进程排行", meta: "按流量归因", icon: Database },
  { key: "navigation", label: "服务导航", meta: "常用服务入口", icon: Compass },
  { key: "ai", label: "AI 中心", meta: "问答与设置助手", icon: Sparkles },
  { key: "settings", label: "设置", meta: "运行参数与通知", icon: Settings },
]);
const gpuSummary = computed(() => {
  const gpus = system.value?.gpu || [];
  if (!gpus.length) return "未检测到或未映射 /dev/dri";
  return gpus.map((gpu) => {
    const percent = acceleratorPercent(gpu);
    const driver = gpu.driver ? `${gpu.driver} · ` : "";
    if (percent === null) return `${driver}${gpu.name || "GPU"} 已映射，暂无利用率读数`;
    const frequency = gpu.frequencyMhz ? ` · ${gpu.frequencyMhz} MHz` : "";
    return `${driver}${gpu.name || "GPU"} ${formatPercent(percent)}${frequency}`;
  }).join(" / ");
});
const npuSummary = computed(() => {
  const npus = system.value?.npu || [];
  if (!npus.length) return "未检测到或未映射 /dev/accel";
  return npus.map((npu) => {
    const percent = acceleratorPercent(npu);
    const frequency = npu.frequencyMhz ? ` · ${npu.frequencyMhz}/${npu.maxFrequencyMhz || "-"} MHz` : "";
    if (percent === null) return `${npu.name || "NPU"} 已映射，暂无利用率读数`;
    return `${npu.name || "NPU"} ${formatPercent(percent)}${frequency}`;
  }).join(" / ");
});
const acceleratorCards = computed(() => {
  const gpus = (system.value?.gpu || []).map((item) => ({ ...item, kind: "gpu", cardKey: `gpu:${item.index ?? 0}` }));
  const npus = (system.value?.npu || []).map((item) => ({ ...item, kind: "npu", cardKey: `npu:${item.index ?? 0}` }));
  return [...gpus, ...npus];
});

function acceleratorPercent(item) {
  const value = Number(item?.utilPercent);
  return Number.isFinite(value) ? value : null;
}
function acceleratorStatus(item) {
  const percent = acceleratorPercent(item);
  if (percent === null) return { key: "unknown", label: "无读数" };
  if (percent >= 1) return { key: "busy", label: "使用中" };
  return { key: "idle", label: "空闲" };
}
function acceleratorSubtitle(item) {
  const parts = [item.driver || (item.kind === "gpu" ? "drm" : "accel")];
  if (item.kind === "gpu") {
    if (item.engines?.length) parts.push(`${item.engines.length} 个引擎`);
    if (item.path) parts.push(item.path);
  } else if (item.device) {
    parts.push(item.device);
  }
  return parts.join(" · ");
}
function percentBarWidth(value) {
  const number = Number(value);
  return `${Math.max(2, Math.min(100, Number.isFinite(number) ? number : 0))}%`;
}
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
function isTransferMetric(metric) {
  return String(metric || "").endsWith("_bps") || String(metric || "").endsWith("_bytes");
}
function thresholdUnitOptions(metric) {
  if (String(metric || "").endsWith("_bps")) return ["B/s", "KB/s", "MB/s", "GB/s"];
  if (String(metric || "").endsWith("_bytes")) return ["B", "KB", "MB", "GB"];
  return [""];
}
function thresholdToBytes(value, unit) {
  const numeric = Math.max(0, Number(value || 0));
  return Math.round(numeric * (transferUnitBytes[unit] || 1));
}
function thresholdFromBytes(value, metric) {
  const bytes = Math.max(0, Number(value || 0));
  if (!isTransferMetric(metric)) return { thresholdValue: bytes, thresholdUnit: "" };
  const suffix = String(metric).endsWith("_bps") ? "/s" : "";
  const baseUnit = bytes >= 1024 ** 3 ? "GB" : bytes >= 1024 ** 2 || !bytes ? "MB" : bytes >= 1024 ? "KB" : "B";
  const unit = `${baseUnit}${suffix}`;
  const numeric = bytes / transferUnitBytes[unit];
  return { thresholdValue: numeric, thresholdUnit: unit };
}
function normalizeMonitorRuleForm(rule = {}) {
  return { ...rule, channelMode: notificationMode(rule), ...thresholdFromBytes(rule.threshold, rule.metric) };
}
function resetThresholdUnit(rule) {
  rule.window = monitorWindow(rule.metric);
  if (isTransferMetric(rule.metric) && rule.thresholdUnit) {
    Object.assign(rule, thresholdFromBytes(thresholdToBytes(rule.thresholdValue, rule.thresholdUnit), rule.metric));
  } else {
    const units = thresholdUnitOptions(rule.metric);
    rule.thresholdUnit = units.includes('MB') ? 'MB' : units.includes('MB/s') ? 'MB/s' : units[0];
    rule.thresholdValue = 0;
  }
}
function formatMonitorMetricValue(value, metric) {
  if (String(metric || "").endsWith("_bps")) return formatRate(value);
  if (String(metric || "").endsWith("_bytes") || String(metric || "").includes("wan_upload")) return formatBytes(value);
  return String(Math.max(0, Number(value || 0)));
}
function formatMonitorThreshold(rule = {}) {
  if (rule.thresholdValue != null) return `${rule.thresholdValue}${rule.thresholdUnit ? ` ${rule.thresholdUnit}` : ""}`;
  return formatMonitorMetricValue(rule.threshold, rule.metric);
}
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
function formatConfigValue(value) {
  if (value === undefined || value === null || value === "") return "未设置";
  if (typeof value === "object") {
    try {
      const text = JSON.stringify(value, null, 0);
      return text.length > 180 ? `${text.slice(0, 177)}...` : text;
    } catch {
      return "复杂值";
    }
  }
  if (typeof value === "boolean") return value ? "开启" : "关闭";
  return String(value);
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
function formatFanRpm(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("zh-CN", { maximumFractionDigits: 1 }) : "-";
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
function systemCardKey(type, id) {
  return id ? `${type}:${id}` : "";
}
function isSystemCardExpanded(type, id) {
  const key = systemCardKey(type, id);
  return Boolean(key) && expandedSystemCards.has(key);
}
function toggleSystemCard(type, id) {
  const key = systemCardKey(type, id);
  if (!key) return;
  if (expandedSystemCards.has(key)) expandedSystemCards.delete(key);
  else expandedSystemCards.add(key);
}
// Temperature groups arrive with the first system snapshot; open the hottest one once and keep the
// sensor order stable afterwards so the cards do not swap places on every 5 秒 refresh.
let temperatureDefaultSeeded = false;
watch(temperatureGroups, (groups) => {
  if (temperatureDefaultSeeded || !groups.length) return;
  temperatureDefaultSeeded = true;
  const group = hottestTemperatureGroup(groups);
  const key = systemCardKey("temp", group ? temperatureGroupKey(group) : "");
  if (key) expandedSystemCards.add(key);
});
function monitorRuleSummary(rule = {}) {
  const metric = metricLabels[rule.metric] || "未选择指标";
  const duration = Number(rule.durationSeconds || 0);
  return `${metric} · 阈值 ${formatMonitorThreshold(rule)}${duration ? ` · 持续 ${duration} 秒` : " · 条件满足立即触发"}`;
}
function ruleNotificationSummary(rule) {
  const mode = notificationMode(rule);
  return mode === 'none' ? '不发送通知' : mode === 'all' ? '全部启用渠道' : `${rule.channelIds?.length || 0} 个指定渠道`;
}
function containerProtectionSummary(rule = {}) {
  const target = rule.targetMode === "all" ? "所有运行中容器" : rule.targetMode === "selected" ? `已选 ${rule.containers?.length || 0} 个容器` : rule.containerName || rule.composeService || "未选择容器";
  const logic = rule.logic === "or" ? "任一条件" : "全部条件";
  const action = containerProtectionActions.find((item) => item.value === rule.action)?.label || "重启";
  return `${target} · ${logic} · ${rule.conditions?.length || 0} 条 · ${action}`;
}
function channelAddressSummary(channel) {
  if (!channel.url) return '服务商默认地址';
  try { return new URL(channel.url).hostname; } catch { return '自定义通知地址'; }
}
function channelTypeLabel(type) {
  const labels = { webhook: "Webhook", iyuu: "IYUU", meow: "MeoW" };
  return labels[String(type || "").toLowerCase()] || "自定义";
}
function rateOf(name, scope, key) {
  return snapshot.value?.rates?.[name]?.scopes?.[scope]?.[key] || 0;
}
import { readApiJson } from './api/json.js';
const readJson = response => readApiJson(response, () => transport.authenticationRequired());
async function api(url, options) {
  if (disposed) throw new DOMException("页面已关闭", "AbortError");
  const controller = new AbortController();
  const view = activeView.value;
  const abort = () => controller.abort();
  options?.signal?.addEventListener("abort", abort, { once: true });
  if (options?.signal?.aborted) abort();
  const timer = setTimeout(abort, url.startsWith('/api/ai/') ? 190000 : 15000);
  try {
    const value = await readJson(await transport.fetch(url, { cache: "no-store", ...options, signal: controller.signal }));
    if (view === activeView.value && requestErrorUrl === url) requestError.value = "";
    return value;
  } catch (error) {
    if (!options?.localError && !options?.signal?.aborted && view === activeView.value) {
      requestErrorUrl = url;
      requestError.value = error.name === "AbortError" ? "请求超时，显示上次成功的数据" : `请求失败：${error.message}`;
    }
    throw error;
  } finally {
    clearTimeout(timer);
    options?.signal?.removeEventListener("abort", abort);
  }
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
  const response = await transport.fetch(url, { cache: "no-store", ...options });
  if (response.status === 401) {
    transport.authenticationRequired();
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
  interfacesLoading.value = true;
  try { return await interfaceRequest.run((signal) => api(`/api/snapshot?interfaces=${encodeURIComponent(interfaceView.value)}`, { signal }), (data) => { snapshot.value = data; }); }
  finally { interfacesLoading.value = false; }
}
async function refreshHistory(period = historyPeriod.value) {
  historyPeriod.value = period;
  historyLoading.value = true;
  try {
    await historyRequest.run((signal) => api(`/api/history?period=${encodeURIComponent(period)}`, { signal }), async (data) => {
      historyData.value = data;
      historyUpdatedAt.value = Date.now() / 1000;
      await nextTick();
      renderHistoryChart();
    });
  } finally {
    historyLoading.value = historyRequest.busy;
  }
}
async function refreshProcesses() {
  if (processPeriod.value === 'custom' && !appliedProcessRange.value.start) return;
  const params = new URLSearchParams({ period: processPeriod.value, limit: '30' });
  if (processPeriod.value === 'custom') {
    params.set('start', Math.floor(new Date(appliedProcessRange.value.start).getTime() / 1000));
    params.set('end', Math.floor(new Date(appliedProcessRange.value.end).getTime() / 1000));
  }
  processLoading.value = true;
  try { return await processRequest.run(signal => api(`/api/processes?${params.toString()}`, { signal }), data => { processes.value = data.processes || []; }); }
  finally { processLoading.value = false; }
}
function applyProcessRange() {
  processRangeError.value = validateTimeRange(processStart.value, processEnd.value);
  if (processRangeError.value) return;
  appliedProcessRange.value = { start: processStart.value, end: processEnd.value };
  refreshProcesses();
}
const confirmDialog = ref(null);
function confirmAction(message) {
  const discard = message.includes('放弃');
  return confirmDialog.value.ask(message, { title: discard ? '放弃尚未保存的修改？' : '确认操作',
    confirmLabel: discard ? '放弃修改' : message.includes('清') ? '确认清理' : '确认', cancelLabel: discard ? '继续编辑' : '取消' });
}
function settingsDraftValue(group) {
  return { monitor: monitorRules.value, protection: containerRules.value, channels: channels.value, runtime: runtimeForm, ai: aiForm }[group];
}
function sectionDirty(section) {
  settingsDraftRevision.value;
  const group = section === 'maintenance' ? 'runtime' : section;
  return settingsDrafts.isDirty(group, settingsDraftValue(group));
}
function acceptSettings(data, forceGroups = [], submitted = {}) {
  settings.value = { ...(settings.value || {}), ...data, monitor: { ...(settings.value?.monitor || {}), ...(data.monitor || {}) } };
  const incoming = {};
  if (data.monitor?.rules) incoming.monitor = data.monitor.rules.map(normalizeMonitorRuleForm);
  if (data.monitor?.containerRules) incoming.protection = data.monitor.containerRules.map(normalizeContainerRuleForm);
  if (data.monitor?.channels) incoming.channels = data.monitor.channels;
  if (data.runtime) incoming.runtime = data.runtime;
  if (data.ai) incoming.ai = { ...data.ai, apiKey: '' };
  for (const [group, value] of Object.entries(incoming)) {
    const result = submitted[group]
      ? settingsDrafts.applySaved(group, value, settingsDraftValue(group), submitted[group])
      : settingsDrafts.hydrate(group, value, settingsDraftValue(group), forceGroups.includes(group));
    if (group === 'monitor') monitorRules.value = result;
    if (group === 'protection') containerRules.value = result;
    if (group === 'channels') channels.value = result;
    if (group === 'runtime') Object.assign(runtimeForm, result);
    if (group === 'ai') Object.assign(aiForm, result);
  }
  settingsDraftRevision.value++;
}
async function refreshSettings(forceGroups = []) {
  if (settingsLoading.value) return;
  settingsLoading.value = true;
  try { acceptSettings(await api('/api/settings'), forceGroups); }
  finally { settingsLoading.value = false; }
  if (activeView.value === "settings") refreshDockerContainerOptions();
}
async function discardSettingsDraft() {
  if (!await confirmAction('放弃当前分区尚未保存的修改，并重新读取服务器设置？')) return;
  await refreshSettings([currentSettingsGroup.value]);
  settingsErrors[currentSettingsGroup.value] = '';
}
async function saveSettingsGroup(group, action, validation = '') {
  if (settingsSaving[group]) return false;
  settingsErrors[group] = '';
  if (validation) { settingsErrors[group] = validation; return false; }
  settingsSaving[group] = true;
  const submitted = JSON.parse(JSON.stringify(settingsDraftValue(group)));
  try { acceptSettings(await action(), [group], { [group]: submitted }); showToast(`${settingsSections.find(s => s.key === group)?.label || '设置'}已保存${sectionDirty(group) ? '，还有新的未保存修改' : ''}`); return true; }
  catch (error) { settingsErrors[group] = '保存失败：' + formatValidationError(error); return false; }
  finally { settingsSaving[group] = false; }
}
async function refreshAlertHistory() {
  const data = await api("/api/alerts?limit=100");
  alertHistory.value = Array.isArray(data?.alerts) ? data.alerts : [];
}
async function refreshUploadDiagnostic() {
  if (!diagnosticDate.value || diagnosticLoading.value) return;
  diagnosticLoading.value = true;
  try {
    const [diagnostic] = await Promise.all([
      api(`/api/diagnostics/upload?date=${encodeURIComponent(diagnosticDate.value)}`),
      refreshAlertHistory(),
    ]);
    uploadDiagnostic.value = diagnostic;
  } catch (error) {
    showToast(`诊断读取失败：${formatValidationError(error)}`);
  } finally {
    diagnosticLoading.value = false;
  }
}
async function askAiAboutDiagnostic() {
  const date = diagnosticDate.value;
  await analyzeWithAi("history", `请重点排查 ${date} 的异常公网上传，结合当天总量、进程、网卡、告警证据和通知投递结果，说明最可能来源及证据局限。`);
}
async function refreshAiSettings() {
  acceptSettings({ ai: await api('/api/settings/ai') });
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
  if (!await confirmAction("清空 AI 历史对话？此操作不可撤销。")) return;
  await api("/api/ai/history", { method: "DELETE" });
  aiMessages.value = [];
  aiHistoryLoaded.value = true;
  aiWarning.value = "";
  showToast("AI 记录已清空");
}
async function requestAiConfiguration() {
  const request = aiConfigureInput.value.trim();
  if (!request || aiConfigureLoading.value) return;
  aiConfigureLoading.value = true;
  aiConfigureError.value = "";
  aiConfigureProposal.value = null;
  try {
    const messages = aiMessages.value.slice(-8).filter((message) => ["user", "assistant"].includes(message.role)).map((message) => ({
      role: message.role,
      content: String(message.content || "").slice(-6000),
    }));
    const result = await api("/api/ai/configure", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ request, messages }),
    });
    if (!result?.ok) throw new Error(result?.detail || "配置预览生成失败");
    aiConfigureProposal.value = result.proposal || null;
    if (!aiConfigureProposal.value) throw new Error("AI 未返回配置预览");
  } catch (error) {
    aiConfigureError.value = formatValidationError(error);
  } finally {
    aiConfigureLoading.value = false;
  }
}
function cancelAiConfiguration() {
  aiConfigureProposal.value = null;
  aiConfigureError.value = "";
}
async function applyAiConfiguration() {
  const proposalId = aiConfigureProposal.value?.id;
  if (!proposalId || aiConfigureLoading.value) return;
  aiConfigureLoading.value = true;
  aiConfigureError.value = "";
  try {
    const result = await api("/api/ai/configure/apply", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ proposalId }),
    });
    if (!result?.ok) throw new Error(result?.detail || "配置应用失败");
    aiConfigureProposal.value = null;
    await refreshSettings();
    showToast("AI 配置已应用");
  } catch (error) {
    aiConfigureError.value = formatValidationError(error);
  } finally {
    aiConfigureLoading.value = false;
  }
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
    aiModels.value = Array.isArray(result.models) ? result.models : [];

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
async function refreshDocker(force = false) {
  if (dockerLoading) return;
  dockerLoading = true;
  dockerListLoading.value = true;
  try {
  const data = await api(`/api/docker/containers${force === true ? '?refresh=true' : ''}`);
  dockerData.value = { ...data, containers: mergeDockerContainers(data.containers || []) };
  } finally {
    dockerLoading = false;
    dockerListLoading.value = false;
  }
}
async function refreshDockerContainerOptions(force = false) {
  if (containerOptionsLoading.value || dockerLoading || (!force && (dockerData.value?.containers || []).length)) return;
  containerOptionsLoading.value = true;
  containerOptionsError.value = '';
  try { await refreshDocker(force); if (!dockerData.value.enabled) containerOptionsError.value = 'Docker 自动发现未开启，请在常用设置中启用后重新获取。'; }
  catch (error) { containerOptionsError.value = '获取容器失败：' + formatValidationError(error); }
  finally { containerOptionsLoading.value = false; }
}
function dockerKey(container) {
  return container?.id || container?.name || "";
}
function dockerIconByKey(key) {
  return dockerIcons.value.find((item) => item.key === key)?.dataUrl || "";
}
function normalizeDockerContainer(container = {}, previous = {}) {
  const keepPorts = Array.isArray(previous.ports) ? previous.ports : [];
  return {
    ...previous,
    ...container,
    ports: Array.isArray(container.ports) ? container.ports : keepPorts,
    portsLoaded: Array.isArray(container.ports) ? true : Boolean(previous.portsLoaded),
    containerIcon: container.containerIcon || previous.containerIcon || "",
    iconKey: container.iconKey || previous.iconKey || "",
    iconSource: container.iconSource || previous.iconSource || "",
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
function normalizeContainerRuleForm(rule = {}) { return normalizeProtectionRule(rule); }
function resetProtectionThreshold(condition) {
  const units = protectionUnitOptions(condition.metric);
  condition.thresholdUnit = units.includes("MB") ? "MB" : units.includes("MB/s") ? "MB/s" : units[0];
  condition.thresholdValue = 0;
}
function protectionStatusLabel(status) {
  return { healthy: "正常", exceeded: "占用超限", locked: "已锁定", unavailable: "采样失败", missing: "容器未运行/不可见", stale: "采样过期", waiting: "等待下轮", monitoring: "监控中" }[status] || "等待采样";
}
function protectionMetricSummary(state) {
  return (state.metricDetails || []).map(item => {
    const metric = containerProtectionMetricLabels[item.metric] || item.metric;
    const value = item.metric.endsWith("Percent") ? `${Number(item.value).toFixed(1)}%` : item.metric.endsWith("Bps") ? formatRate(item.value) : formatBytes(item.value);
    return `${metric} ${value}${item.hot && !item.ready ? ` · 等待持续 ${item.durationSeconds} 秒` : ''}`;
  }).join(" · ");
}
function protectionRuleStatus(rule) {
  if (!rule.enabled) return "停用";
  const state = protectionState(rule);
  if (state.locked) return "已锁定";
  if (["unavailable", "missing", "stale"].includes(state.monitorStatus)) return protectionStatusLabel(state.monitorStatus);
  const failures = Object.values(state.containers || {}).filter(s => ["unavailable", "missing", "stale"].includes(s.monitorStatus)).length;
  return failures ? `${failures} 个采样异常` : "监控中";
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
async function refreshDockerIcons() {
  if (dockerIcons.value.length) return;
  try {
    const data = await api("/api/docker/icons");
    dockerIcons.value = Array.isArray(data?.icons) ? data.icons : [];
  } catch (error) {
    console.warn("load docker icons failed", error);
  }
}
async function showDockerStats(container) {
  container.showStats = true;
  await refreshDockerStats(container);
}
async function refreshDockerStats(container) {
  if (!container?.id || container.statsLoading) return;
  container.statsLoading = true;
  try {
  const key = encodeURIComponent(container.id);
  const data = await api(`/api/docker/containers/${key}/stats`);
  if (!data.ok) throw new Error(data.detail || "容器统计暂时不可用");
  container.stats = data.stats;
  } finally { container.statsLoading = false; }
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
    showToast(`已识别为 Web：${port.scheme}://${transport.hostname()}:${port.hostPort}`);
  } else {
    port.accessMode = "copy";
    showToast("探测完成：看起来不是 Web 服务");
  }
  await saveDockerPortsFor(container);
}
async function refreshVisibleDockerStats() {
  if (activeView.value !== "docker") return;
  const targets = dockerContainers.value.filter((container) => container.showStats && container.id && isDockerCardExpanded(container));
  for (const container of targets) {
    if (transport.hidden() || activeView.value !== "docker") break;
    try {
      await refreshDockerStats(container);
    } catch (error) {
      console.warn("refresh docker stats failed", error);
    }
  }
}
async function refreshConnections(resetPage = false) {
  if (resetPage) connOffset.value = 0;
  connLoading.value = true;
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
    await connectionRequest.run((signal) => api(`/api/connections?${params.toString()}`, { signal }), (data) => {
      connections.value = data.connections || [];
      connPagination.value = data.pagination || {};
      connectionError.value = "";
    });
  } catch (error) {
    connectionError.value = "刷新失败，保留上次结果";
  } finally {
    connLoading.value = connectionRequest.busy;
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
    color: ["#2f80ed", "#f2994a", "#00a8c8", "#6d5bd0"],
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
function toggleMenu() {
  menuOpen.value = !menuOpen.value;
}
function closeMenu() {
  menuOpen.value = false;
}
function setMenuPinned(value) {
  menuPinned.value = Boolean(value);
  localStorage.setItem("ntl-menu-pinned", menuPinned.value ? "true" : "false");
  if (menuPinned.value) menuOpen.value = false;
}
function handleMenuKeydown(event) {
  if (event.key === "Escape" && menuOpen.value) closeMenu();
  if (event.key.toLowerCase() === "m" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    const target = event.target;
    const typing = target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
    if (!typing && !target?.isContentEditable) {
      event.preventDefault();
      toggleMenu();
    }
  }
}
function navigate(view) {
  setView(view);
  if (!menuPinned.value) closeMenu();
}
function setView(view) {
  [historyRequest, connectionRequest, processRequest, interfaceRequest].forEach((request) => request.cancel());
  requestError.value = "";
  if (activeView.value === "history" && view !== "history" && historyChart) {
    historyChart.dispose();
    historyChart = null;
  }
  if (view !== "docker") stopDockerTimer();
  activeView.value = view;
  emit('view', view);
  refreshActive();
  startViewTimer();
  if (view === "docker") startDockerTimer();
}
async function refreshActive() {
  try {
  if (activeView.value === "overview") await refreshOverview();
  if (activeView.value === "interfaces") await refreshInterfaces();
  if (activeView.value === "history") await refreshHistory();
  if (activeView.value === "processes") await refreshProcesses();
  if (activeView.value === "monitor") {
    await refreshSettings();
    await refreshUploadDiagnostic();
  }
  if (activeView.value === "settings") await refreshSettings();
  if (activeView.value === "ai") await refreshAiSettings();
  if (activeView.value === "system") await refreshSystem();
  if (activeView.value === "docker") await refreshDocker();
  } catch (error) { console.warn("refresh failed", error); }
}
function startViewTimer() {
  if (disposed) return;
  viewTimer?.stop();
  const view = activeView.value;
  const delay = { overview: 2000, interfaces: 2000, processes: 10000, system: 5000, history: 30000 }[view];
  if (!delay) return;
  viewTimer = createPollLoop(async () => {
    if (historyRequest.busy || processRequest.busy || interfaceRequest.busy) return;
    await refreshActive();
  }, delay, { shouldRun: () => !disposed && !transport.hidden() && activeView.value === view });
  viewTimer.start();
}
function startDockerTimer() {
  if (disposed) return;
  stopDockerTimer();
  dockerTimer = createPollLoop(refreshVisibleDockerStats, 5000, { shouldRun: () => !disposed && !transport.hidden() && activeView.value === "docker" });
  dockerTimer.start();
}
function stopDockerTimer() {
  dockerTimer?.stop();
  dockerTimer = null;
}
function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}
function openConnections(options = {}) {
  Object.assign(connFilters, connectionDefaults(options));
  connOffset.value = 0;
  if (!connectionDialog.value.open) connectionDialog.value.showModal();
  refreshConnections();
  startConnectionTimer();
}
function openWanConnections() {
  const mode = connectionSummary.value.source === "conntrack" ? "conntrack" : "capture";
  Object.assign(connFilters, connectionDefaults({ mode, scope: "wan" }));
  connOffset.value = 0;
  if (!connectionDialog.value.open) connectionDialog.value.showModal();
  refreshConnections();
  startConnectionTimer();
}
function resetConnectionFilters() { Object.assign(connFilters, connectionDefaults()); refreshConnections(true); }
function startConnectionTimer() {
  connectionTimer?.stop();
  connectionTimer = createPollLoop(() => connectionRequest.busy ? undefined : refreshConnections(false), 5000, { shouldRun: () => !disposed && !transport.hidden() && connectionDialog.value?.open });
  connectionTimer.start();
}
function stopConnectionTimer() {
  connectionTimer?.stop();
  connectionRequest.cancel();
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
  if (!await confirmAction('清除全部告警记录、异常证据和通知回执？此操作不可撤销，流量历史与配置仍会保留。')) return;
  await api("/api/alerts/clear", { method: "POST" });
  showToast("全部告警记录已清除");
  refreshOverview();
  refreshAlertHistory();
  if (activeView.value === "monitor") refreshUploadDiagnostic();
}
function protectionState(rule) { return settings.value?.monitor?.containerStates?.[rule.id] || {}; }
async function resetProtection(rule) {
  if (!await confirmAction(`重置“${rule.name}”的保护计数并解除锁定？启用的规则将恢复监控。`)) return;
  settings.value = await api(`/api/settings/container-protection/${encodeURIComponent(rule.id)}/reset`, { method: "POST" });
  showToast("保护计数已重置");
}
async function clearTrafficHistory() {
  if (!await confirmAction("清除全部网卡和进程流量历史？此操作不可撤销。规则、通知渠道、AI 对话和告警证据会保留。")) return;
  await api("/api/history/clear", { method: "POST" });
  historyData.value = { buckets: [], totals: {} };
  showToast("流量历史已清理，配置已保留");
}
async function saveRuntime() {
  return saveSettingsGroup('runtime', () => api('/api/settings/runtime', { localError: true, method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(runtimeForm) }));
}
async function saveAiSettings() {
  return saveSettingsGroup('ai', () => api('/api/settings/ai', {
    localError: true, method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({
      enabled: Boolean(aiForm.enabled), provider: aiForm.provider || 'openai', baseUrl: String(aiForm.baseUrl || '').trim(),
      apiKey: aiForm.apiKey, model: String(aiForm.model || '').trim(), timeoutSeconds: clampNumber(aiForm.timeoutSeconds, 5, 180, 60),
      maxTokens: clampNumber(aiForm.maxTokens, 128, 393216, 1200), systemPrompt: aiForm.systemPrompt,
    }),
  }));
}

function applyAiStreamEvent(event, assistantIndex) {
  if (event.type === "delta" && aiMessages.value[assistantIndex]) {
    aiMessages.value[assistantIndex].content += event.content || "";
  }
  if (event.type !== "done" || !aiMessages.value[assistantIndex]) return;
  aiMessages.value[assistantIndex].streaming = false;
  if (!aiMessages.value[assistantIndex].content) aiMessages.value[assistantIndex].content = event.answer || "";
  if (event.truncated) {
    aiMessages.value[assistantIndex].truncated = true;
    aiWarning.value = event.finishReason === "length"
      ? "AI 已达到最大输出 Token，回答可能未完整结束。"
      : "AI 流式连接未完整结束，回答可能不完整。";
  }
}
async function analyzeWithAi(scope = "overview", customQuestion = "") {
  if (aiLoading.value) return;
  aiLoading.value = true;
  aiError.value = "";
  aiWarning.value = "";
  const question = customQuestion || (scope === "history"
    ? `请结合当前选择的历史周期（${historyPeriod.value}）分析公网和内网流量趋势，指出异常。`
    : scope === "monitor"
      ? "请检查监控规则、容器保护、通知渠道和最近告警，指出当前风险与配置建议。"
      : "请分析当前所有统计数据，重点指出公网上传风险、异常进程和 Docker/系统资源问题。");
  if (activeView.value !== "ai") setView("ai");
  await refreshAiHistory();
  aiMessages.value.push({ role: "user", content: question });
  const assistantIndex = aiMessages.value.length;
  aiMessages.value.push({ role: "assistant", content: "", streaming: true });
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
    if (aiMessages.value[assistantIndex]) aiMessages.value[assistantIndex].streaming = false;
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
  aiMessages.value.push({ role: "assistant", content: "", streaming: true });
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
    if (aiMessages.value[assistantIndex]) aiMessages.value[assistantIndex].streaming = false;
    aiLoading.value = false;
  }
}
function handleAiComposerKeydown(event) {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  sendAiChat();
}
async function saveRules() {
  return saveSettingsGroup('monitor', () => api('/api/settings/monitor', { localError: true, method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ rules: monitorRules.value.map(monitorPayload) }) }), validateMonitorRules(monitorRules.value));
}
async function saveContainerRules() {
  return saveSettingsGroup('protection', () => api('/api/settings/container-protection', { localError: true, method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ rules: containerRules.value.map(protectionRulePayload) }) }), validateContainerRules(containerRules.value));
}
async function saveChannels() {
  return saveSettingsGroup('channels', () => api('/api/settings/channels', { localError: true, method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ channels: channels.value }) }), validateChannels(channels.value));
}
async function testChannel(channelId) {
  if (testingChannel.value) return;
  const channel = channels.value.find(row => row.id === channelId);
  const error = validateChannels([{ ...channel, enabled: true }]);
  if (error) { settingsErrors.channels = error; return; }
  if (!await saveChannels()) return;
  testingChannel.value = channelId;
  try {
    const result = await api('/api/notifications/test', { localError: true, method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ channelId }) });
    if (!result.ok) throw new Error(result.detail || result.body || '发送失败');
    showToast('测试通知已发送');
  } catch (error) { settingsErrors.channels = '测试通知发送失败：' + formatValidationError(error); }
  finally { testingChannel.value = ''; }
}
function addRule() {
  const rule = normalizeMonitorRuleForm(newUploadRule(`rule-${Date.now()}`));
  monitorRules.value.push(rule);
  expandMonitorCard("traffic", rule.id);
}
function removeRule(id) {
  monitorRules.value = monitorRules.value.filter((item) => item.id !== id);
  expandedMonitorCards.delete(monitorCardKey("traffic", id));
}
function addContainerRule() {
  const rule = normalizeProtectionRule({
    id: `protection-${Date.now()}`,
    name: "新容器保护",
    containerId: "",
    containerName: "",
    composeProject: "",
    composeService: "",
    containerSearch: "",
    targetMode: "single",
    containers: [],
    enabled: false,
    channelIds: [],
    logic: "and",
    action: "restart",
    cooldownSeconds: 60,
    conditions: [
      { metric: "cpuPercent", operator: "gte", threshold: 90, durationSeconds: 30 },
    ],
  });
  containerRules.value.push(rule);
  expandMonitorCard("container", rule.id);
}
function removeContainerRule(id) {
  containerRules.value = containerRules.value.filter((item) => item.id !== id);
  expandedMonitorCards.delete(monitorCardKey("container", id));
}
function addContainerCondition(rule) {
  rule.conditions = Array.isArray(rule.conditions) ? rule.conditions : [];
  rule.conditions.push(normalizeProtectionCondition({ metric: "cpuPercent", operator: "gte", threshold: 90, durationSeconds: 30 }));
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
  const label = await transport.prompt("给这个容器端口设置备注，留空则清除", current || "");
  if (label === null) return;
  await api("/api/labels", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key, label }) });
  refreshConnections();
}
function openContainerPort(port) {
  transport.open(serviceUrl(port, transport.hostname()));
}
async function addDockerNavigation(container, port) {
  try {
    const entry = dockerBookmark(container, port, transport.hostname());
    entry.icon = await navigationIcon(entry.icon);
    await bookmarks.save(entry);
    showToast('已加入导航');
  } catch (error) { showToast(error.message || String(error)); }
}
function containerPortAddress(port) {
  return `${transport.hostname()}:${port.hostPort}`;
}
async function copyContainerPort(port) {
  const text = containerPortAddress(port);
  try {
    await navigator.clipboard.writeText(text);
    showToast(`已复制 ${text}`);
  } catch {
    await transport.prompt("复制连接地址", text);
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
  await refreshDockerIcons();
  const detail = container.portsLoaded ? container : (await loadDockerDetail(container)) || container;
  dockerEditor.id = detail.id || "";
  dockerEditor.name = detail.name || "";
  dockerEditor.icon = detail.containerIcon || "";
  dockerEditor.iconKey = detail.iconSource === "builtin" ? (detail.iconKey || "") : "";
  dockerEditor.ports = (detail.ports || []).map(normalizeEditorPort);
  dockerEditBaseline.value = JSON.stringify(dockerEditor);
  dockerEditError.value = "";
  dockerEditDialog.value?.showModal();
}
function addDockerPort() {
  dockerEditor.ports.push(normalizeEditorPort({ proto: "tcp", hostPort: 8080, containerPort: 8080, accessMode: "web", service: "web" }));
}
function removeDockerPort(index) {
  dockerEditor.ports.splice(index, 1);
}
async function requestCloseDockerEditor() {
  if (dockerEditSaving.value) return;
  if (JSON.stringify(dockerEditor) !== dockerEditBaseline.value && !await confirmAction('放弃尚未保存的访问入口和图标修改？')) return;
  dockerEditDialog.value?.close();
}
async function saveDockerPorts() {
  if (dockerEditSaving.value) return;
  dockerEditError.value = '';
  const seen = new Set();
  for (const port of dockerEditor.ports) {
    if (![port.hostPort, port.containerPort].every(n => Number.isInteger(Number(n)) && Number(n) >= 1 && Number(n) <= 65535)) { dockerEditError.value = '请输入 1–65535 范围内的有效端口'; return; }
    const key = `${port.proto}:${port.hostPort}`;
    if (seen.has(key)) { dockerEditError.value = '同一协议的主机访问端口不能重复，请修改后再保存'; return; }
    seen.add(key);
  }
  dockerEditSaving.value = true;
  try {
    await saveDockerPortsFor({ id: dockerEditor.id, name: dockerEditor.name, containerIcon: dockerEditor.icon, iconKey: dockerEditor.iconKey, ports: dockerEditor.ports });
    dockerEditDialog.value?.close(); showToast('访问入口已保存');
  } catch (error) { dockerEditError.value = '保存失败：' + formatValidationError(error); }
  finally { dockerEditSaving.value = false; }
}
async function saveDockerPortsFor(container) {
  const data = await api("/api/docker/containers/ports", {
    localError: true, method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      containerId: container.id || "",
      containerName: container.name || "",
      icon: (container.iconKey || dockerEditor.iconKey) ? "" : (container.containerIcon || dockerEditor.icon || ""),
      iconKey: container.iconKey || dockerEditor.iconKey || "",
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
    dockerEditor.iconKey = "";
  };
  reader.readAsDataURL(file);
}
async function logout() {
  await transport.logout();
}
function showToast(message) {
  toast.value = message;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.value = "";
  }, 3000);
}

watch(theme, (value) => {
  transport.themeChanged?.(value);
  document.documentElement.dataset.theme = value;
  localStorage.setItem("ntl-theme", value);
  nextTick(renderHistoryChart);
}, { immediate: true });
watch(() => props.themeMode, value => { if (value === 'dark' || value === 'light') theme.value = value; });

onMounted(async () => {
  await refreshOverview();
  if (!disposed && activeView.value !== 'overview') await refreshActive();
  if (disposed) return;
  startViewTimer();
  document.addEventListener("visibilitychange", handleVisibility);
  window.addEventListener("resize", handleResize);
  window.addEventListener("keydown", handleMenuKeydown);
});
onUnmounted(() => {
  disposed = true;
  [viewTimer, connectionTimer, dockerTimer].forEach((timer) => timer?.stop());
  [historyRequest, connectionRequest, processRequest, interfaceRequest].forEach((request) => request.cancel());
  document.removeEventListener("visibilitychange", handleVisibility);
  window.removeEventListener("keydown", handleMenuKeydown);
  window.clearTimeout(showToast.timer);
  if (connectionDebounce) clearTimeout(connectionDebounce);
  window.removeEventListener("resize", handleResize);
  historyChart?.dispose();
});
function handleVisibility() {
  if (transport.hidden()) {
    [viewTimer, connectionTimer, dockerTimer].forEach((timer) => timer?.stop());
    [historyRequest, connectionRequest, processRequest, interfaceRequest].forEach((request) => request.cancel());
  } else {
    refreshActive();
    startViewTimer();
    if (activeView.value === "docker") startDockerTimer();
    if (connectionDialog.value?.open) { refreshConnections(); startConnectionTimer(); }
  }
}
</script>
