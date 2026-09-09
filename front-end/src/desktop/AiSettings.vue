<template>
  <section class="ds-settings-section">
    <div class="ds-section-title">
      <h2><Sparkles :size="19" />本机 AI</h2>
      <span class="ds-muted">{{ hasKey ? "凭据已保存" : "未保存凭据" }}</span>
    </div>
    <p class="ds-muted">
      只在你发送问题时连接所选服务。本机 AI 与每台 NAS 的 AI 配置独立。
    </p>
    <div v-if="error" class="ds-error" role="alert">{{ error }}</div>
    <p v-if="notice" class="ds-success" role="status">{{ notice }}</p>
    <form v-if="loaded" @submit.prevent="save" class="ds-ai-form">
      <label class="ds-checkbox"
        ><input v-model="form.enabled" type="checkbox" />启用本机 AI</label
      >
      <div class="ds-form-grid">
        <label
          >厂商<select v-model="form.provider" @change="preset">
            <option
              v-for="item in providerPresets"
              :key="item.value"
              :value="item.value"
            >
              {{ item.label }}
            </option>
          </select></label
        >
        <label
          >接口协议<select v-model="form.protocol">
            <option value="openai">OpenAI 兼容</option>
            <option value="anthropic">Anthropic Messages</option>
          </select></label
        >
        <label class="ds-span-2"
          >服务地址<input
            v-model="form.baseUrl"
            type="url"
            maxlength="1024"
            required
            @input="hasKey = false"
          /><small v-if="form.baseUrl.startsWith('http://')"
            >HTTP 不加密，请仅用于可信本地服务。</small
          ></label
        >
        <label class="ds-span-2"
          >API Key<input
            v-model="apiKey"
            type="password"
            autocomplete="new-password"
            maxlength="4096"
            :placeholder="hasKey ? '留空保留现有凭据' : '本地免鉴权服务可留空'"
          /><small>保存在 macOS 钥匙串 / Windows 凭据库。</small></label
        >
        <label
          >模型<input
            v-model="form.model"
            list="desktop-ai-models"
            maxlength="160"
            required /><datalist id="desktop-ai-models">
            <option
              v-for="model in models"
              :key="model"
              :value="model"
            /></datalist
        ></label>
        <div class="ds-form-command">
          <button
            type="button"
            class="ds-button"
            :disabled="busy"
            @click="loadModels"
          >
            <RefreshCw :size="16" />保存并读取模型
          </button>
        </div>
        <label
          >最大输出 tokens<input
            v-model.number="form.maxTokens"
            type="number"
            min="128"
            max="393216"
            required
        /></label>
        <label
          >无响应等待时间（秒）<input
            v-model.number="form.timeoutSeconds"
            type="number"
            min="10"
            max="600"
            required
        /></label>
        <label class="ds-span-2"
          >附加系统提示词<textarea
            v-model="form.systemPrompt"
            rows="3"
            maxlength="4000"
            placeholder="例如：重点关注磁盘读写和异常上传"
          />
        </label>
      </div>
      <div class="ds-actions">
        <button class="ds-button ds-primary" :disabled="busy">
          <Save :size="16" />{{ busy ? "处理中…" : "保存配置" }}</button
        ><button type="button" class="ds-button" :disabled="busy" @click="test">
          <FlaskConical :size="16" />测试连接</button
        ><button
          type="button"
          class="ds-button ds-danger"
          :disabled="busy || !hasKey"
          @click="removeKey"
        >
          <Trash2 :size="16" />删除此地址凭据
        </button>
      </div>
    </form>
  </section>
</template>
<script setup>
import { onMounted, reactive, ref } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { confirm } from "@tauri-apps/plugin-dialog";
import { Sparkles, Save, RefreshCw, Trash2, FlaskConical } from "@lucide/vue";
import { providerPresets } from "../utils/ai-providers.js";
const emit = defineEmits(["saved"]);
const form = reactive({
  enabled: false,
  provider: "openai",
  protocol: "openai",
  baseUrl: "",
  model: "",
  maxTokens: 4096,
  timeoutSeconds: 180,
  systemPrompt: "",
});
const loaded = ref(false),
  hasKey = ref(false),
  apiKey = ref(""),
  models = ref([]),
  busy = ref(false),
  error = ref(""),
  notice = ref("");
function accept(result) {
  Object.assign(form, result.settings);
  hasKey.value = result.hasKey;
  apiKey.value = "";
  loaded.value = true;
}
function preset() {
  const item = providerPresets.find((p) => p.value === form.provider);
  Object.assign(form, {
    baseUrl: item.baseUrl,
    model: item.model,
    maxTokens: item.maxTokens,
    protocol: item.value === "claude" ? "anthropic" : "openai",
  });
  apiKey.value = "";
  hasKey.value = false;
  models.value = [];
}
async function perform(action) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    await action();
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}
async function persist(clearKey = false) {
  accept(
    await invoke("local_ai_save", {
      settings: { ...form },
      apiKey: apiKey.value || null,
      clearKey,
    }),
  );
  emit("saved");
}
function save() {
  return perform(async () => {
    await persist();
    notice.value = "AI 配置已保存";
  });
}
function loadModels() {
  return perform(async () => {
    await persist();
    models.value = await invoke("local_ai_models");
    notice.value = `已读取 ${models.value.length} 个模型，可在模型输入框中选择`;
  });
}
function test() {
  return perform(async () => {
    await persist();
    await invoke("local_ai_test");
    notice.value = "模型流式连接正常";
  });
}
async function removeKey() {
  if (
    await confirm("删除当前服务地址的 AI 凭据？", {
      title: "删除 AI 凭据",
      kind: "warning",
    })
  )
    await perform(async () => {
      apiKey.value = "";
      await persist(true);
      notice.value = "凭据已删除";
    });
}
onMounted(() => perform(async () => accept(await invoke("local_ai_settings"))));
</script>
