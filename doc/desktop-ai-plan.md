# Desktop AI 0.2.0 Implementation Plan

**Goal:** Publish Mac ARM64, Mac x64 and Windows x64 clients with local AI and multiple independent NAS sessions.

**Architecture:** Vue views call thin Tauri controllers. Rust services own provider requests, cancellation, bounded context and SQLite conversations. NAS mode keeps using each server's existing AI and database.

**Constraints:** No subagents. Preserve NAS VERSION and Docker images. Never persist secrets in SQLite or documentation. API keys use the OS credential store. AI only runs on user request. Native AI cannot execute shell commands or control other NAS targets.

- [x] Core tests and services: validate endpoint/settings, OpenAI-compatible and Anthropic SSE, cancellation/EOF/size bounds, chat restart persistence. Store local settings separately from NAS sessions. Preserve partial responses with interrupted status.
- [x] Multi-NAS: cancel outgoing requests on switch while retaining profile cookies; explicit disconnect and independent status; regression tests for two targets.
- [x] UI: local AI configuration, built-in providers and model discovery, streaming Markdown, Enter/Shift+Enter, persisted conversations, history range/interface and opt-in process context, analysis shortcuts. Local preference proposals require a separate reviewed apply action.
- [x] Verify: 15 Rust tests, core Clippy, 11 frontend tests, NAS and desktop builds. Native Mac verified model discovery, streaming Markdown, Enter send, setting preview/apply, light/dark rendering and chat recovery after restart, using a local mock provider. Both Mac DMGs passed integrity checks. Windows Actions 34319823942 succeeded on source fdd6d06. Real GUI NAS LAN authorization remains an explicitly documented limitation.
- [x] Deliver: [desktop-v0.2.0](https://github.com/isle24/datatotal/releases/tag/desktop-v0.2.0), built from main source fdd6d06, contains Mac ARM64/x64 DMGs, Windows Actions NSIS installer and SHA256 checksums. Apple account/signing requirements and runtime limits are documented. The local Mac app was updated; temporary AI mock configuration and synthetic chat were cleaned up.

Verification commands: `cargo test --manifest-path server/desktop/Cargo.toml -p traffic-lens-core`, `cargo clippy --manifest-path server/desktop/Cargo.toml -p traffic-lens-core --all-targets -- -D warnings`, `npm --prefix front-end test`, `npm --prefix front-end run build`, `npm --prefix front-end run desktop:mac`.
