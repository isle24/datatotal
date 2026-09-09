# Desktop AI 0.2.0 Implementation Plan

**Goal:** Publish Mac ARM64, Mac x64 and Windows x64 clients with local AI and multiple independent NAS sessions.

**Architecture:** Vue views call thin Tauri controllers. Rust services own provider requests, cancellation, bounded context and SQLite conversations. NAS mode keeps using each server's existing AI and database.

**Constraints:** No subagents. Preserve NAS VERSION and Docker images. Never persist secrets in SQLite or documentation. API keys use the OS credential store. AI only runs on user request. Native AI cannot execute shell commands or control other NAS targets.

- [x] Core tests and services: validate endpoint/settings, OpenAI-compatible and Anthropic SSE, cancellation/EOF/size bounds, chat restart persistence. Store local settings separately from NAS sessions. Preserve partial responses with interrupted status.
- [x] Multi-NAS: cancel outgoing requests on switch while retaining profile cookies; explicit disconnect and independent status; regression tests for two targets.
- [x] UI: local AI configuration, built-in providers and model discovery, streaming Markdown, Enter/Shift+Enter, persisted conversations, history range/interface and opt-in process context, analysis shortcuts. Local preference proposals require a separate reviewed apply action.
- [ ] Verify: Rust tests/Clippy, frontend tests, NAS and desktop builds, native Mac UI smoke including chat mock provider and persistence. No real API keys required for mock verification.
- [ ] Deliver: desktop 0.2.0, Mac ARM64/x64 DMGs and Windows Actions NSIS installer, SHA256 checksums, published GitHub prerelease from main, signing/account documentation.

Verification commands: `cargo test --manifest-path server/desktop/Cargo.toml -p traffic-lens-core`, `cargo clippy --manifest-path server/desktop/Cargo.toml -p traffic-lens-core --all-targets -- -D warnings`, `npm --prefix front-end test`, `npm --prefix front-end run build`, `npm --prefix front-end run desktop:mac`.
