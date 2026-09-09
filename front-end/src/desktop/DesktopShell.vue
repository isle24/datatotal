<template>
  <div class="desktop-shell" :class="{ 'ds-remote': source !== 'local' && !settingsOpen }">
    <header class="ds-sourcebar">
      <div class="ds-brand"><span class="ds-brand-icon"><Activity :size="21" /></span><strong>Traffic Lens</strong><span class="ds-version">DESKTOP {{ config.version }}</span></div>
      <div class="ds-source-controls">
        <Monitor :size="17" />
        <select aria-label="数据来源" :value="source" @change="switchSource($event.target.value)"><option value="local">本机</option><option v-for="profile in config.profiles" :value="profile.id" :key="profile.id">{{ profile.name }}</option></select>
        <button class="ds-icon" title="桌面设置" aria-label="桌面设置" :class="{ selected: settingsOpen }" @click="settingsOpen = !settingsOpen"><Settings2 :size="19" /></button>
        <button class="ds-icon" :title="dark ? '浅色模式' : '深色模式'" aria-label="切换主题" @click="dark = !dark"><Sun v-if="dark" :size="19" /><Moon v-else :size="19" /></button>
      </div>
    </header>
    <div v-if="error" class="ds-error" role="alert"><CircleAlert :size="17" /><span>{{ error }}</span><button class="ds-icon" aria-label="关闭提示" @click="error = ''"><X :size="16" /></button></div>
    <main v-if="settingsOpen" class="ds-content ds-settings">
      <div class="ds-heading"><div><span class="ds-eyebrow">PREFERENCES</span><h1>桌面设置</h1></div><button class="ds-button" @click="settingsOpen = false"><ArrowLeft :size="16" />返回监控</button></div>
      <section class="ds-settings-section"><h2>本机监控</h2>
        <label class="ds-setting-row"><span><strong>关闭窗口后继续监控</strong><small>可从托盘菜单退出并停止采集</small></span><input type="checkbox" :checked="config.closeToTray" @change="preference('closeToTray', $event.target.checked)" /></label>
        <label class="ds-setting-row"><span><strong>登录系统时启动</strong></span><input type="checkbox" :checked="autostart" @change="setAutostart($event.target.checked)" /></label>
        <label class="ds-setting-row"><span><strong>历史保留时间</strong><small>只保存本机实际采集的网卡流量；每小时清理过期记录</small></span><select :value="config.retentionDays" @change="preference('retentionDays', Number($event.target.value))"><option v-for="days in [7, 30, 90, 180, 365]" :value="days">{{ days }} 天</option></select></label>
        <div class="ds-setting-row"><span><strong>本地数据与日志</strong><small>SQLite 持久化；日志按大小轮转</small></span><div class="ds-actions"><button class="ds-button" @click="run(() => invoke('open_directory', { kind: 'data' }))"><FolderOpen :size="16" />数据目录</button><button class="ds-button" @click="run(() => invoke('open_directory', { kind: 'logs' }))"><FolderOpen :size="16" />日志目录</button><button class="ds-button ds-danger" @click="clearHistory"><Trash2 :size="16" />清空历史</button></div></div>
      </section>
      <section class="ds-settings-section"><div class="ds-section-title"><h2>NAS 连接 <small>{{ config.profiles.length }}</small></h2><button class="ds-button ds-primary" @click="editProfile()"><Plus :size="16" />添加 NAS</button></div>
        <p v-if="!config.profiles.length" class="ds-empty">还没有保存的 NAS 连接</p>
        <div class="ds-profile-list"><article v-for="profile in config.profiles" :key="profile.id" class="ds-profile"><Server :size="24" /><div><strong>{{ profile.name }}</strong><small>{{ profile.url }}</small></div><div class="ds-actions"><button class="ds-button" @click="switchSource(profile.id)">连接<ArrowRight :size="15" /></button><button class="ds-icon" title="编辑连接" aria-label="编辑连接" @click="editProfile(profile)"><Pencil :size="16" /></button><button class="ds-icon ds-danger" title="删除连接" aria-label="删除连接" @click="deleteProfile(profile)"><Trash2 :size="16" /></button></div></article></div>
      </section>
      <section class="ds-settings-section"><h2>桌面预览版</h2><p class="ds-muted">本机支持 CPU、内存、磁盘空间、进程资源和网卡总流量。公网归属、进程网络流量、连接明细及硬件传感器尚未接入；NAS 模式使用远端已有能力。</p><button class="ds-button" @click="invoke('quit_app')"><Power :size="16" />退出并停止本机监控</button></section>
    </main>
    <template v-else-if="source === 'local'">
      <nav class="ds-tabs" aria-label="本机页面"><button v-for="item in tabs" :key="item.id" :class="{ active: view === item.id }" @click="view = item.id"><component :is="item.icon" :size="17" />{{ item.name }}</button></nav>
      <main class="ds-content">
        <div class="ds-heading"><div><span class="ds-eyebrow">LOCAL MONITOR</span><h1>{{ tabs.find(t => t.id === view)?.name }}</h1><p>{{ snapshot.host || '正在读取本机信息' }} <span class="ds-dot">·</span> {{ snapshot.os }}</p></div><div class="ds-live"><span :class="{ stale: stale }"></span>{{ stale ? '等待采样' : '实时采集中' }}<small>{{ updatedAt }}</small></div></div>
        <div v-if="snapshot.error" class="ds-error">{{ snapshot.error }}</div>
        <template v-if="view === 'overview'">
          <div class="ds-metrics">
            <article class="ds-metric"><div><span class="ds-metric-icon ds-green"><ArrowDown :size="20" /></span><span>网卡实时下行</span></div><strong class="ds-number ds-green">{{ bytes(activeInterface.rx_bps) }}<small>/s</small></strong><footer>{{ selected || '等待网卡' }}</footer></article>
            <article class="ds-metric"><div><span class="ds-metric-icon ds-pink"><ArrowUp :size="20" /></span><span>网卡实时上行</span></div><strong class="ds-number ds-pink">{{ bytes(activeInterface.tx_bps) }}<small>/s</small></strong><footer>包含公网与内网</footer></article>
            <article class="ds-metric"><div><span class="ds-metric-icon"><Cpu :size="20" /></span><span>CPU 占用</span></div><strong class="ds-number">{{ (snapshot.cpu_percent || 0).toFixed(1) }}<small>%</small></strong><footer>{{ snapshot.cpu_count || '—' }} 个逻辑核心</footer></article>
            <article class="ds-metric"><div><span class="ds-metric-icon"><MemoryStick :size="20" /></span><span>内存使用</span></div><strong class="ds-number">{{ bytes(snapshot.memory_bytes) }}</strong><footer>共 {{ bytes(snapshot.total_memory_bytes) }} · {{ memoryPercent }}%</footer></article>
          </div>
          <section class="ds-section"><div class="ds-section-title"><div><h2>网络趋势</h2><p>最近 4 分钟 · 网卡总流量</p></div><select aria-label="监控网卡" :value="selected" @change="selectInterface($event.target.value)"><option v-for="nic in snapshot.interfaces" :key="nic.name" :value="nic.name">{{ nic.name }} · {{ kindLabel(nic.kind) }}</option></select></div><TrafficChart :points="livePoints" :dark="dark" /><div class="ds-chart-footer"><span>系统网卡累计</span><strong class="ds-green">↓ {{ bytes(activeInterface.system_rx_bytes) }}</strong><strong class="ds-pink">↑ {{ bytes(activeInterface.system_tx_bytes) }}</strong><small>可能随系统或网卡重启归零</small></div></section>
          <div class="ds-system-strip"><Cpu :size="20" /><strong>{{ snapshot.cpu_name || 'CPU' }}</strong><span>已运行 {{ uptime }}</span><span class="ds-muted">GPU / 温度 / 风扇：此预览版暂不支持</span></div>
        </template>
        <template v-else-if="view === 'interfaces'">
          <div class="ds-section-title"><p class="ds-muted">{{ filteredInterfaces.length }} / {{ snapshot.interfaces?.length || 0 }} 个网卡 · 多网卡可能记录同一条流量，不合并为公网总量</p><select v-model="interfaceFilter" aria-label="网卡类型筛选"><option value="all">全部网卡</option><option value="interface">常规网卡</option><option value="virtual">虚拟 / 隧道</option><option value="loopback">回环</option></select></div>
          <div class="ds-interface-grid"><article v-for="nic in filteredInterfaces" :key="nic.name" class="ds-interface"><div class="ds-section-title"><h2><Network :size="19" />{{ nic.name }}</h2><span class="ds-muted">{{ kindLabel(nic.kind) }}</span></div><div class="ds-nic-rates"><span class="ds-green">↓ <strong>{{ bytes(nic.rx_bps) }}</strong>/s</span><span class="ds-pink">↑ <strong>{{ bytes(nic.tx_bps) }}</strong>/s</span></div><div class="ds-nic-total"><span>系统累计下行<strong>{{ bytes(nic.system_rx_bytes) }}</strong></span><span>系统累计上行<strong>{{ bytes(nic.system_tx_bytes) }}</strong></span></div><button class="ds-button" @click="selectInterface(nic.name); view = 'history'">查看历史<ArrowRight :size="15" /></button></article></div>
        </template>
        <template v-else-if="view === 'processes'">
          <div class="ds-table-tools"><label class="ds-search"><Search :size="17" /><input v-model="search" placeholder="搜索进程或 PID" aria-label="搜索进程或 PID" /></label><select v-model="sort" aria-label="进程排序"><option value="cpu_percent">CPU 从高到低</option><option value="memory_bytes">内存从高到低</option><option value="read_bps">磁盘读取从高到低</option><option value="write_bps">磁盘写入从高到低</option></select><span class="ds-muted">{{ filteredProcesses.length }} / {{ snapshot.process_count || 0 }} 个进程</span></div>
          <div class="ds-table-wrap"><table><thead><tr><th>进程</th><th>PID</th><th>CPU</th><th>内存</th><th>磁盘读取</th><th>磁盘写入</th></tr></thead><tbody><tr v-for="p in pagedProcesses" :key="`${p.pid}-${p.started_at}`"><td>{{ p.name }}</td><td>{{ p.pid }}</td><td><div class="ds-cpu-cell"><span :style="{ width: `${Math.min(100, p.cpu_percent)}%` }"></span><strong>{{ p.cpu_percent.toFixed(1) }}%</strong></div></td><td>{{ bytes(p.memory_bytes) }}</td><td>{{ bytes(p.read_bps) }}/s</td><td>{{ bytes(p.write_bps) }}/s</td></tr><tr v-if="!pagedProcesses.length"><td colspan="6" class="ds-empty">{{ snapshot.processes_at ? '没有匹配进程' : '正在采集进程，首次速率需等待两个采样周期' }}</td></tr></tbody></table></div>
          <div class="ds-pagination"><small>CPU 以整机为 100%；可见范围受系统权限限制</small><button class="ds-icon" aria-label="上一页" :disabled="page <= 1" @click="page--"><ChevronLeft :size="18" /></button><span>{{ page }} / {{ pages }}</span><button class="ds-icon" aria-label="下一页" :disabled="page >= pages" @click="page++"><ChevronRight :size="18" /></button></div>
        </template>
        <template v-else-if="view === 'history'">
          <div class="ds-table-tools"><div class="ds-segments"><button v-for="p in periods" :key="p.id" :class="{ active: period === p.id }" @click="period = p.id">{{ p.name }}</button></div><select v-model="selected" aria-label="历史网卡"><option v-for="nic in snapshot.interfaces" :key="nic.name" :value="nic.name">{{ nic.name }}</option></select><button class="ds-icon" aria-label="刷新历史" title="刷新历史" :disabled="historyBusy" @click="refreshHistory"><RefreshCw :size="18" /></button></div>
          <div class="ds-history-totals"><div><ArrowDown class="ds-green" :size="22" /><span>累计下行<strong>{{ bytes(history.rx_bytes) }}</strong></span></div><div><ArrowUp class="ds-pink" :size="22" /><span>累计上行<strong>{{ bytes(history.tx_bytes) }}</strong></span></div><p>仅含 {{ selected }} 的已采集数据<br />每 30 秒落库，不回填安装前的流量</p></div>
          <TrafficChart :points="historyPoints" :dark="dark" history :start="historyRange.start" :end="historyRange.end" label="历史上行与下行流量" /><p v-if="!history.points.length" class="ds-empty">此时间段暂无已保存的流量，请在有网络活动后等待约 30 秒。</p>
        </template>
        <template v-else-if="view === 'system'">
          <section class="ds-section"><div class="ds-section-title"><h2><HardDrive :size="20" />磁盘空间</h2><span class="ds-muted">每分钟更新</span></div><div class="ds-interface-grid"><article v-for="disk in snapshot.disks" :key="disk.mount" class="ds-interface"><h3>{{ disk.name }}</h3><small class="ds-muted">{{ disk.mount }}</small><progress :value="disk.total_bytes - disk.available_bytes" :max="disk.total_bytes"></progress><p>可用 {{ bytes(disk.available_bytes) }} / {{ bytes(disk.total_bytes) }}</p></article></div></section>
          <section class="ds-section"><h2>硬件传感器</h2><p class="ds-muted">GPU、NPU、温度和风扇采集尚未在桌面预览版中接入。</p></section>
        </template>
      </main>
    </template>
    <template v-else>
      <div class="ds-target"><Server :size="15" /><strong>{{ currentProfile?.name }}</strong><span>{{ currentProfile?.url }}</span><span class="ds-muted">数据与操作均来自此 NAS</span></div>
      <NasView v-if="authenticated && currentProfile" :key="sessionKey" :profile="currentProfile" :prompt="promptText" @expired="authenticated = false" />
      <div v-else class="ds-login-wrap"><form class="ds-login" @submit.prevent="login(false)"><Server :size="32" /><h1>连接 {{ currentProfile?.name }}</h1><p>{{ currentProfile?.url }}</p><label>访问密码<input v-model="password" type="password" autocomplete="current-password" autofocus /></label><label class="ds-checkbox"><input v-model="remember" type="checkbox" />保存到系统凭据库</label><button class="ds-button ds-primary" :disabled="loginBusy">{{ loginBusy ? '正在连接…' : '连接 NAS' }}<ArrowRight :size="17" /></button><button type="button" class="ds-button" :disabled="loginBusy" @click="login(true)">使用已保存的密码</button><small>未启用密码的 NAS 可留空。HTTP 连接不加密。</small></form></div>
    </template>
    <div v-if="profileEditor" class="ds-modal-backdrop" @click.self="profileEditor = null"><form class="ds-modal" @submit.prevent="saveProfile"><h2>{{ profileEditor.id ? '编辑 NAS' : '添加 NAS' }}</h2><label>名称<input v-model="profileEditor.name" maxlength="60" required autofocus placeholder="家里的 NAS" /></label><label>服务地址<input v-model="profileEditor.url" required type="url" placeholder="http://192.168.1.10:8088" /></label><div class="ds-actions"><button type="button" class="ds-button" @click="profileEditor = null">取消</button><button class="ds-button ds-primary" :disabled="profileBusy">保存连接</button></div></form></div>
    <div v-if="promptState" class="ds-modal-backdrop"><form class="ds-modal" @submit.prevent="resolvePrompt(promptState.value)"><h2>{{ promptState.message }}</h2><input v-model="promptState.value" autofocus /><div class="ds-actions"><button type="button" class="ds-button" @click="resolvePrompt(null)">取消</button><button class="ds-button ds-primary">确定</button></div></form></div>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { confirm } from "@tauri-apps/plugin-dialog";
import { enable, disable, isEnabled } from "@tauri-apps/plugin-autostart";
import { Activity, Monitor, Server, Settings2, Sun, Moon, X, CircleAlert, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, FolderOpen, Trash2, Plus, Pencil, Power, Cpu, MemoryStick, Network, Search, ChevronLeft, ChevronRight, RefreshCw, HardDrive, History, LayoutDashboard } from "@lucide/vue";
import TrafficChart from "./TrafficChart.vue";
const NasView = defineAsyncComponent(() => import("./NasView.vue"));
const config = reactive({ version: "", profiles: [], closeToTray: true, retentionDays: 30 });
const snapshot = ref({ interfaces: [], processes: [], disks: [] });
const error = ref("");
const source = ref("local"), settingsOpen = ref(false), view = ref("overview");
const selected = ref(""), dark = ref(localStorage.getItem("ntl-theme") === "dark");
const autostart = ref(false), livePoints = ref([]), authenticated = ref(false), sessionKey = ref(0);
const password = ref(""), remember = ref(false), loginBusy = ref(false), profileBusy = ref(false), profileEditor = ref(null), promptState = ref(null);
const search = ref(""), sort = ref("cpu_percent"), page = ref(1), interfaceFilter = ref("all");
const period = ref("today"), history = ref({ rx_bytes: 0, tx_bytes: 0, points: [] }), historyRange = ref({}), historyBusy = ref(false);
const tabs = [{ id: "overview", name: "实时概览", icon: LayoutDashboard }, { id: "interfaces", name: "网卡", icon: Network }, { id: "processes", name: "进程", icon: Cpu }, { id: "history", name: "流量历史", icon: History }, { id: "system", name: "系统", icon: HardDrive }];
const periods = [{ id: "today", name: "今日" }, { id: "week", name: "本周" }, { id: "month", name: "本月" }, { id: "30days", name: "近 30 天" }];
const currentProfile = computed(() => config.profiles.find(p => p.id === source.value));
const activeInterface = computed(() => snapshot.value.interfaces.find(n => n.name === selected.value) || {});
const filteredInterfaces = computed(() => snapshot.value.interfaces.filter(n => interfaceFilter.value === "all" || n.kind === interfaceFilter.value));
const memoryPercent = computed(() => Math.round(100 * (snapshot.value.memory_bytes || 0) / (snapshot.value.total_memory_bytes || 1)));
const stale = computed(() => !snapshot.value.timestamp || Date.now() / 1000 - snapshot.value.timestamp > 10);
const updatedAt = computed(() => snapshot.value.timestamp ? new Date(snapshot.value.timestamp * 1000).toLocaleTimeString() : "");
const uptime = computed(() => `${Math.floor((snapshot.value.uptime || 0) / 86400)} 天 ${Math.floor((snapshot.value.uptime || 0) % 86400 / 3600)} 小时`);
const filteredProcesses = computed(() => snapshot.value.processes.filter(p => `${p.name} ${p.pid}`.toLowerCase().includes(search.value.toLowerCase())).sort((a, b) => b[sort.value] - a[sort.value] || a.pid - b.pid));
const pages = computed(() => Math.max(1, Math.ceil(filteredProcesses.value.length / 30)));
const pagedProcesses = computed(() => filteredProcesses.value.slice((page.value - 1) * 30, page.value * 30));
const historyPoints = computed(() => history.value.points.map(p => ({ timestamp: p.timestamp, rx: p.rx_bytes, tx: p.tx_bytes })));
const kindLabel = kind => ({ interface: "常规网卡", virtual: "虚拟 / 隧道", loopback: "回环" }[kind] || kind);
function bytes(value) { if (value == null || !Number.isFinite(value)) return "—"; const units = ["B", "KiB", "MiB", "GiB", "TiB"]; const index = Math.min(4, Math.floor(Math.log2(Math.max(1, value)) / 10)); return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`; }
async function run(task) { try { return await task(); } catch (e) { error.value = String(e?.message || e); } }
async function loadConfig() { Object.assign(config, await invoke("desktop_config")); }
async function preference(key, value) { await run(async () => { await invoke("set_preference", { key, value }); await loadConfig(); }); }
async function setAutostart(value) { await run(async () => { await (value ? enable() : disable()); autostart.value = await isEnabled(); }); }
function selectInterface(name) { selected.value = name; preference("interface", name); }
function editProfile(profile) { profileEditor.value = { id: profile?.id || null, name: profile?.name || "", url: profile?.url || "" }; }
async function saveProfile() { profileBusy.value = true; await run(async () => { const saved = await invoke("save_profile", { ...profileEditor.value }); if (source.value === saved.id) { authenticated.value = false; sessionKey.value++; } await loadConfig(); profileEditor.value = null; }); profileBusy.value = false; }
async function deleteProfile(profile) { if (await confirm(`删除 ${profile.name} 的连接和本机保存的凭据？`, { title: "删除连接", kind: "warning" })) await run(async () => { if (source.value === profile.id) switchSource("local"); await invoke("delete_profile", { id: profile.id }); await loadConfig(); }); }
let sourceGeneration = 0;
function switchSource(id) { if (source.value !== "local") invoke("nas_disconnect", { id: source.value }).catch(() => {}); sourceGeneration++; authenticated.value = false; password.value = ""; remember.value = false; source.value = id; sessionKey.value++; settingsOpen.value = false; error.value = ""; }
async function login(saved) { if (loginBusy.value) return; loginBusy.value = true; error.value = ""; const id = source.value, generation = sourceGeneration; const secret = password.value; password.value = ""; try { await invoke("nas_login", { id, password: saved ? null : secret, remember: saved || remember.value }); if (generation !== sourceGeneration) { await invoke("nas_disconnect", { id }); return; } authenticated.value = true; sessionKey.value++; } catch (e) { if (generation === sourceGeneration) error.value = String(e); } finally { loginBusy.value = false; } }
function promptText(message, value) { return new Promise(resolve => { promptState.value?.resolve(null); promptState.value = { message, value, resolve }; }); }
function resolvePrompt(value) { promptState.value?.resolve(value); promptState.value = null; }
async function clearHistory() { if (await confirm("清空本机网卡历史？NAS 数据、连接和设置会保留。", { title: "清空本机历史", kind: "warning" })) await run(() => invoke("clear_local_history")); }
let historyGeneration = 0, lastHistory = 0;
async function refreshHistory() {
  if (!selected.value) return;
  const generation = ++historyGeneration;
  historyBusy.value = true;
  const end = new Date(), start = new Date(end);
  start.setHours(0, 0, 0, 0);
  if (period.value === "week") start.setDate(start.getDate() - (start.getDay() + 6) % 7);
  if (period.value === "month") start.setDate(1);
  if (period.value === "30days") start.setDate(start.getDate() - 29);
  const range = { start: Math.floor(+start / 1000), end: Math.floor(+end / 1000) + 1 };
  const bucket = period.value === "today" ? 300 : period.value === "week" ? 3600 : 21600;
  try { const data = await invoke("local_history", { ...range, interface: selected.value, bucket }); if (generation === historyGeneration) { history.value = data; historyRange.value = range; lastHistory = Date.now(); } } catch (e) { if (generation === historyGeneration) error.value = String(e); } finally { if (generation === historyGeneration) historyBusy.value = false; }
}
let timer, stopped = false, polling = false;
async function poll() {
  if (stopped || polling || document.hidden || source.value !== "local" || settingsOpen.value) return;
  polling = true;
  try {
    const data = await invoke("local_snapshot", { processes: view.value === "processes" });
    if (stopped || source.value !== "local" || settingsOpen.value) return;
    snapshot.value = data;
    if (!selected.value && data.interfaces.length) selected.value = data.interfaces.find(n => n.kind === "interface" && n.system_rx_bytes > 0)?.name || data.interfaces[0].name;
    const nic = data.interfaces.find(n => n.name === selected.value);
    if (view.value === "overview" && nic && livePoints.value.at(-1)?.timestamp !== data.timestamp) {
      const prev = livePoints.value.at(-1);
      const gap = prev && data.timestamp - prev.timestamp > 15 ? [{ timestamp: data.timestamp - 1, rx: null, tx: null }] : [];
      livePoints.value = [...livePoints.value, ...gap, { timestamp: data.timestamp, rx: nic.rx_bps, tx: nic.tx_bps }].filter(p => p.timestamp >= data.timestamp - 240).slice(-121);
    }
    if (view.value === "history" && !historyBusy.value && Date.now() - lastHistory > 30000) await refreshHistory();
  } catch (e) { error.value = String(e); } finally { polling = false; }
}
function visibility() { if (!document.hidden) poll(); }
watch(dark, value => { document.documentElement.dataset.theme = value ? "dark" : "light"; localStorage.setItem("ntl-theme", value ? "dark" : "light"); }, { immediate: true });
watch([period, selected], () => { livePoints.value = []; lastHistory = 0; if (view.value === "history" && !settingsOpen.value && source.value === "local") refreshHistory(); });
watch([view, settingsOpen, source], () => { if (view.value === "history") lastHistory = 0; poll(); });
watch([search, sort], () => page.value = 1);
watch(pages, count => { if (page.value > count) page.value = count; });
onMounted(async () => { await run(async () => { await loadConfig(); selected.value = config.interface || ""; autostart.value = await isEnabled(); }); await poll(); timer = setInterval(poll, 2000); document.addEventListener("visibilitychange", visibility); });
onUnmounted(() => { stopped = true; clearInterval(timer); historyGeneration++; resolvePrompt(null); document.removeEventListener("visibilitychange", visibility); });
</script>
