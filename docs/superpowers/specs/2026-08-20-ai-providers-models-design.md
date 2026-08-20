# AI Providers and Model Discovery Design

## Goal

修复 AI 设置保存时的 422 可诊断性和常见输入问题，并增加内置 AI 厂商、模型发现以及 Claude 原生 API 支持，同时保持现有 OpenAI-compatible 配置、SQLite 持久化和按需请求的低负载特性。

## Scope

- AI 设置增加 `provider` 字段，兼容旧 SQLite 配置时默认为 `openai`。
- 内置 OpenAI、Claude、DeepSeek、Kimi、Qwen、MiniMax 和自定义兼容接口。
- 新增后端代理 `GET /api/ai/models`，由服务端访问厂商模型接口，避免浏览器 CORS 和 API Key 暴露。
- Claude 使用 Anthropic `/v1/models` 和 `/v1/messages`；其他内置厂商及自定义厂商使用 `/models` 和 `/chat/completions`。
- 模型响应受大小、数量和 ID 长度限制，并在服务端做 60 秒短缓存。
- 前端选择厂商时填充默认 Base URL/模型，允许用户覆盖；可以手动输入模型，模型接口失败不阻塞保存。
- 前端显示 FastAPI 字段级 422 原因，并在提交前规范化超时和最大 Token。

## Provider Presets

| Provider | Default Base URL | Protocol | Default Model |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | OpenAI-compatible | `gpt-4o-mini` |
| Claude | `https://api.anthropic.com/v1` | Anthropic | `claude-3-5-haiku-latest` |
| DeepSeek | `https://api.deepseek.com/v1` | OpenAI-compatible | `deepseek-chat` |
| Kimi | `https://api.moonshot.cn/v1` | OpenAI-compatible | `moonshot-v1-8k` |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI-compatible | `qwen-plus` |
| MiniMax | `https://api.minimaxi.com/v1` | OpenAI-compatible | `MiniMax-Text-01` |
| Custom | empty | OpenAI-compatible | user supplied |

Presets are defaults only. Users may change the URL and model after selecting a provider.

## Architecture

`server/services/ai.py` owns provider metadata, normalization, HTTP requests, protocol adapters, response parsing and bounded model caching. It never logs API keys or sends them to the frontend. The service returns a stable model shape: `{id, name}`.

`server/main.py` keeps MVC boundaries: Pydantic request models validate the API contract, `TrafficCollector` persists normalized settings and delegates AI operations, and routes only translate HTTP requests to service/collector calls. `GET /api/ai/models` returns a structured 200 response for provider errors (`ok: false`) so an unavailable vendor does not turn the settings page into a 500 error.

The frontend owns form state and presentation. It calls the backend model endpoint, displays a select when models are available, and retains the text input as a fallback. A save request clamps numeric values and the common API helper renders list-shaped FastAPI validation details.

## Error and Security Rules

- Base URLs must be HTTP/HTTPS and must not contain userinfo credentials.
- API keys remain in SQLite and are only returned as `keyConfigured`/masked values.
- Model requests require a configured API key and have the configured timeout, with a bounded response body.
- Model cache keys contain a one-way key digest, never the raw API key.
- Provider errors expose status and a short response excerpt only; request headers are never included.
- Model lists are limited to 200 entries and each identifier is limited to 160 characters.
- Claude requests use `x-api-key` and `anthropic-version`; OpenAI-compatible requests use `Authorization: Bearer`.
- AI calls remain explicit user actions and never run in collection loops.

## Compatibility

Existing payloads without `provider` remain valid and use OpenAI behavior. Existing custom Base URLs remain editable. Empty API key or the displayed mask preserves the previously stored key. Unknown or missing model list support never prevents manual model entry or saving.

## Verification

- Python tests cover normalization, provider presets, request headers/bodies, Claude response parsing, model parsing/cache behavior and error-safe model discovery.
- Frontend contract tests cover provider/model controls, numeric normalization and readable 422 errors.
- Run Python compile/tests, frontend build/UI tests, compose validation, and image runtime checks before release.
