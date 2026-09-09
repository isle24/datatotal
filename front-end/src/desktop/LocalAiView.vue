<template>
  <div class="ds-ai-workspace">
    <aside class="ds-ai-sidebar">
      <div class="ds-section-title">
        <h2>对话</h2>
        <button
          class="ds-icon"
          title="新建对话"
          aria-label="新建对话"
          :disabled="busy"
          @click="selectChat(null)"
        >
          <Plus :size="18" />
        </button>
      </div>
      <div class="ds-chat-list">
        <button
          v-for="chat in chats"
          :key="chat.id"
          :class="{ active: chat.id === chatId }"
          :disabled="busy"
          @click="selectChat(chat.id)"
        >
          <MessageSquare :size="16" /><span>{{ chat.title }}</span>
        </button>
      </div>
      <button class="ds-button" @click="emit('settings')">
        <Settings2 :size="16" />AI 设置
      </button>
    </aside>
    <section class="ds-ai-main">
      <div class="ds-section-title">
        <h2><Sparkles :size="19" />本机 AI 中心</h2>
        <div class="ds-actions">
          <span class="ds-muted">{{ config?.settings?.model || "未配置" }}</span
          ><button
            class="ds-icon ds-danger"
            title="删除当前对话"
            aria-label="删除当前对话"
            :disabled="busy || !chatId"
            @click="remove"
          >
            <Trash2 :size="17" />
          </button>
        </div>
      </div>
      <div v-if="error" class="ds-error" role="alert">{{ error }}</div>
      <div v-if="!config?.settings?.enabled" class="ds-ai-callout">
        <span>本机 AI 尚未启用</span
        ><button class="ds-button" @click="emit('settings')">
          打开 AI 设置
        </button>
      </div>
      <div class="ds-ai-scope">
        <label
          >模式<select v-model="mode" :disabled="busy">
            <option value="analysis">数据分析</option>
            <option value="configure">设置助手</option>
          </select></label
        >
        <label
          >分析网卡<select v-model="nic" :disabled="busy">
            <option
              v-for="item in interfaces"
              :key="item.name"
              :value="item.name"
            >
              {{ item.name }}
            </option>
          </select></label
        >
        <label
          >历史范围<select v-model="period" :disabled="busy">
            <option value="today">今日</option>
            <option value="week">本周</option>
            <option value="month">本月</option>
            <option value="30days">近 30 天</option>
            <option value="custom">自定义</option>
          </select></label
        >
        <template v-if="period === 'custom'"
          ><label
            >开始<input
              v-model="startDate"
              type="datetime-local"
              :disabled="busy" /></label
          ><label
            >结束<input
              v-model="endDate"
              type="datetime-local"
              :disabled="busy" /></label
        ></template>
        <label class="ds-checkbox"
          ><input
            v-model="includeProcesses"
            type="checkbox"
            :disabled="busy"
          />发送实时进程摘要</label
        >
      </div>
      <p class="ds-ai-disclosure">
        发送所选网卡流量历史、当前 CPU / 内存及磁盘空间摘要给
        {{
          config?.settings?.provider || "所选 AI 服务"
        }}。网卡流量包含公网与内网。
      </p>
      <div ref="transcript" class="ds-ai-transcript" @click="openLink">
        <button
          v-if="hasMore"
          class="ds-button"
          :disabled="busy"
          @click="older"
        >
          查看更早消息
        </button>
        <div v-if="!messages.length" class="ds-ai-empty">
          <Sparkles :size="32" />
          <h3>从本机数据开始分析</h3>
          <div class="ds-ai-prompts">
            <button
              v-for="text in suggestions"
              :key="text"
              class="ds-button"
              @click="prompt = text"
            >
              {{ text }}
            </button>
          </div>
        </div>
        <article
          v-for="message in messages"
          :key="message.id"
          class="ds-ai-message"
          :class="message.role"
        >
          <div class="ds-ai-message-meta">
            <strong>{{
              message.role === "user" ? "你" : "Traffic Lens AI"
            }}</strong
            ><small>{{ message.model }}</small>
          </div>
          <div
            v-if="message.role === 'assistant'"
            class="ds-markdown"
            v-html="renderMarkdown(message.content)"
          />
          <p v-else class="ds-user-message">{{ message.content }}</p>
          <small v-if="message.status === 'streaming'" class="ds-ai-state"
            >正在生成…</small
          ><small
            v-else-if="message.status === 'interrupted'"
            class="ds-ai-state"
            >回复已中断，内容已保留</small
          ><small v-else-if="message.status === 'truncated'" class="ds-ai-state"
            >达到输出上限，可继续提问或调整 tokens</small
          >
        </article>
      </div>
      <section v-if="proposal" class="ds-ai-proposal">
        <div class="ds-section-title">
          <h3>本机设置变更预览</h3>
          <span class="ds-muted"
            >{{
              new Date(proposal.expires * 1000).toLocaleTimeString()
            }}
            过期</span
          >
        </div>
        <div
          v-for="change in proposal.changes"
          :key="change.key"
          class="ds-setting-row"
        >
          <strong>{{ preferenceLabels[change.key] || change.key }}</strong
          ><span
            >{{ displayValue(change.before) }} →
            {{ displayValue(change.after) }}</span
          >
        </div>
        <p class="ds-muted">缩短保留时间会在下一次清理时删除过期流量历史。</p>
        <div class="ds-actions">
          <button
            class="ds-button ds-primary"
            :disabled="busy || applying"
            @click="applyProposal"
          >
            <Check :size="16" />确认应用</button
          ><button class="ds-button" @click="proposal = null">收起预览</button>
        </div>
      </section>
      <form class="ds-ai-composer" @submit.prevent="send">
        <textarea
          v-model="prompt"
          rows="3"
          maxlength="5000"
          aria-label="AI 问题"
          placeholder="询问本机流量或资源情况…"
          @keydown="keydown"
        />
        <div class="ds-composer-actions">
          <span class="ds-muted">{{
            busy ? "正在分析所选本机数据" : "对话保存在本机"
          }}</span
          ><button v-if="busy" type="button" class="ds-button" @click="stop">
            <Square :size="15" />停止</button
          ><button
            v-else
            class="ds-button ds-primary"
            :disabled="!prompt.trim() || !config?.settings?.enabled || !nic"
          >
            <Send :size="16" />发送
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
<script setup>
import { ref, onMounted, onUnmounted, nextTick } from "vue";
import { invoke, Channel } from "@tauri-apps/api/core";
import { confirm } from "@tauri-apps/plugin-dialog";
import {
  Sparkles,
  Settings2,
  Plus,
  Trash2,
  Send,
  Square,
  MessageSquare,
  Check,
} from "@lucide/vue";
import { renderMarkdown } from "../utils/markdown.js";
const props = defineProps({
  interfaces: Array,
  selected: String,
  initialPeriod: String,
  initialPrompt: String,
});
const emit = defineEmits(["settings", "preferences"]);
const mode = ref("analysis"),
  proposal = ref(null),
  applying = ref(false);
const preferenceLabels = {
  retentionDays: "历史保留天数",
  closeToTray: "关闭窗口后继续监控",
  interface: "默认网卡",
};
const displayValue = (value) =>
  typeof value === "boolean" ? (value ? "开启" : "关闭") : value || "自动";
async function applyProposal() {
  applying.value = true;
  await perform(async () => {
    await invoke("local_ai_apply", { id: proposal.value.id });
    proposal.value = null;
    emit("preferences");
  });
  applying.value = false;
}
const config = ref(null),
  chats = ref([]),
  messages = ref([]),
  chatId = ref(null),
  hasMore = ref(false),
  busy = ref(false),
  error = ref(""),
  prompt = ref(props.initialPrompt || ""),
  nic = ref(props.selected || ""),
  period = ref(props.initialPeriod || "today"),
  includeProcesses = ref(false),
  startDate = ref(""),
  endDate = ref(""),
  transcript = ref(null);
const suggestions = [
  "分析这段时间的上传和下载趋势",
  "当前资源占用有什么需要关注的？",
  "如何进一步定位异常上传的来源？",
];
let requestId = "",
  disposed = false,
  generation = 0,
  flushTimer,
  pendingText = "",
  streamMessage = null;
async function perform(fn) {
  try {
    await fn();
  } catch (e) {
    if (!disposed) error.value = String(e);
  }
}
async function loadChats() {
  const rows = await invoke("local_ai_chats");
  if (!disposed) chats.value = rows;
}
async function selectChat(id) {
  if (busy.value) return;
  const ticket = ++generation;
  error.value = "";
  chatId.value = id;
  messages.value = [];
  hasMore.value = false;
  if (id)
    await perform(async () => {
      const page = await invoke("local_ai_messages", { id, before: null });
      if (!disposed && ticket === generation) {
        messages.value = page.messages;
        hasMore.value = page.has_more;
        await scroll(true);
      }
    });
}
async function older() {
  await perform(async () => {
    const id = chatId.value,
      ticket = generation;
    const page = await invoke("local_ai_messages", {
      id,
      before: messages.value[0]?.id,
    });
    if (!disposed && ticket === generation) {
      messages.value = page.messages;
      hasMore.value = page.has_more;
    }
  });
}
function range() {
  const end = new Date(),
    start = new Date(end);
  start.setHours(0, 0, 0, 0);
  if (period.value === "week")
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  if (period.value === "month") start.setDate(1);
  if (period.value === "30days") start.setDate(start.getDate() - 29);
  const a = period.value === "custom" ? new Date(startDate.value) : start,
    b = period.value === "custom" ? new Date(endDate.value) : end;
  if (!Number.isFinite(+a) || !Number.isFinite(+b) || +b <= +a)
    throw new Error("请选择有效的历史时间范围");
  return {
    start: Math.floor(+a / 1000),
    end: Math.floor(+b / 1000) + 1,
    interface: nic.value,
    processes: includeProcesses.value,
  };
}
async function scroll(force = false) {
  const el = transcript.value,
    nearBottom = el && el.scrollHeight - el.scrollTop - el.clientHeight < 150;
  await nextTick();
  if (el && (force || nearBottom)) el.scrollTop = el.scrollHeight;
}
function flush() {
  clearTimeout(flushTimer);
  flushTimer = null;
  if (streamMessage && pendingText) {
    streamMessage.content += pendingText;
    pendingText = "";
    scroll();
  }
}
async function send() {
  if (busy.value || !prompt.value.trim() || !config.value?.settings?.enabled)
    return;
  error.value = "";
  let scope;
  try {
    scope = range();
  } catch (e) {
    error.value = e.message;
    return;
  }
  busy.value = true;
  const text = prompt.value.trim();
  prompt.value = "";
  requestId = crypto.randomUUID();
  let started = false;
  const channel = new Channel();
  channel.onmessage = (packet) => {
    if (disposed) return;
    if (packet.type === "start") {
      started = true;
      chatId.value = packet.chat_id;
      messages.value.push({
        id: `user-${requestId}`,
        role: "user",
        content: text,
        status: "complete",
      });
      messages.value.push({
        id: requestId,
        role: "assistant",
        content: "",
        status: "streaming",
        model: config.value.settings.model,
      });
      streamMessage = messages.value.at(-1);
      scroll(true);
    }
    if (packet.type === "delta") {
      pendingText += packet.text;
      if (!flushTimer)
        flushTimer = setTimeout(
          flush,
          (streamMessage?.content.length || 0) > 250000 ? 500 : 100,
        );
    }
    if (packet.type === "done") {
      flush();
      if (streamMessage) streamMessage.status = packet.status;
    }
  };
  const packetHandler = channel.onmessage;
  channel.onmessage = (packet) => {
    packetHandler(packet);
    if (!disposed && packet.type === "proposal")
      proposal.value = packet.proposal;
  };
  try {
    await invoke("local_ai_chat", {
      request: {
        requestId,
        chatId: chatId.value,
        prompt: text,
        scope,
        configure: mode.value === "configure",
      },
      onPacket: channel,
    });
  } catch (e) {
    if (!disposed) {
      error.value = String(e);
      if (!started) prompt.value = text;
    }
  } finally {
    flush();
    if (streamMessage?.status === "streaming")
      streamMessage.status = "interrupted";
    streamMessage = null;
    requestId = "";
    if (!disposed)
      await perform(async () => {
        await loadChats();
        if (started && chatId.value) {
          const page = await invoke("local_ai_messages", {
            id: chatId.value,
            before: null,
          });
          if (!disposed) {
            messages.value = page.messages;
            hasMore.value = page.has_more;
            await scroll();
          }
        }
      });
    busy.value = false;
  }
}
function keydown(event) {
  if (
    event.key !== "Enter" ||
    event.shiftKey ||
    event.isComposing ||
    event.keyCode === 229
  )
    return;
  event.preventDefault();
  send();
}
function stop() {
  if (requestId) invoke("local_ai_cancel", { id: requestId }).catch(() => {});
}
async function remove() {
  if (
    await confirm("删除当前本机 AI 对话及消息？", {
      title: "删除对话",
      kind: "warning",
    })
  )
    await perform(async () => {
      await invoke("local_ai_delete", { id: chatId.value });
      await selectChat(null);
      await loadChats();
    });
}
function openLink(event) {
  const anchor = event.target.closest("a");
  if (!anchor) return;
  event.preventDefault();
  const url = anchor.getAttribute("href");
  if (/^https?:\/\//i.test(url))
    perform(() => invoke("open_external", { url }));
}
onMounted(() =>
  perform(async () => {
    config.value = await invoke("local_ai_settings");
    proposal.value = await invoke("local_ai_proposal");
    await loadChats();
    if (chats.value.length && !props.initialPrompt)
      await selectChat(chats.value[0].id);
  }),
);
onUnmounted(() => {
  disposed = true;
  generation++;
  stop();
  clearTimeout(flushTimer);
  pendingText = "";
  streamMessage = null;
});
</script>
