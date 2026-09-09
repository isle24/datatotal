// Shared by the NAS UI and the native desktop AI settings.
export const providerPresets = [
  {
    value: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    maxTokens: 1200,
  },
  {
    value: "claude",
    label: "Claude",
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-3-5-haiku-latest",
    maxTokens: 4096,
  },
  {
    value: "deepseek",
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com",
    model: "deepseek-v4-flash",
    maxTokens: 393216,
  },
  {
    value: "kimi",
    label: "Kimi",
    baseUrl: "https://api.moonshot.cn/v1",
    model: "moonshot-v1-8k",
    maxTokens: 4096,
  },
  {
    value: "qwen",
    label: "Qwen",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    maxTokens: 4096,
  },
  {
    value: "minimax",
    label: "MiniMax",
    baseUrl: "https://api.minimaxi.com/v1",
    model: "MiniMax-Text-01",
    maxTokens: 4096,
  },
  {
    value: "custom",
    label: "自定义兼容接口",
    baseUrl: "",
    model: "",
    maxTokens: 1200,
  },
];
