# Desktop Preview Implementation Plan

Execute inline without subagents, using the approved desktop-client design.

Goal: ship a usable Tauri preview with local resource/network totals, SQLite history, isolated NAS sessions and tray lifecycle; build/test the Mac app locally and build Windows x64 with GitHub Actions.

Architecture: two Rust crates under `server/desktop` separate the testable core from Tauri controllers. `front-end/desktop.html` loads the desktop shell; existing NAS Vue views use an extracted transport adapter. The normal NAS web build remains a separate entry point.

Constraints: no real credentials or captured personal data in fixtures or commits; local basic metrics must never be labelled WAN metrics; no privileged helper, driver, local process actions or full per-process network attribution in this preview. Existing NAS operations require an authenticated target and retain their confirmation dialogs.

## Tasks

- [ ] Core metrics and storage: add Rust models, system sampler and transactional SQLite history/profile/settings stores. Test first-sample baselines, counter reset, sleep gaps, process identity and history windows with synthetic counters; then implement and run `cargo test -p traffic-lens-core`.
- [ ] NAS transport: add URL/path validation, bounded HTTP/SSE, per-profile sessions, optional OS credential storage and cancellation. Test external redirects, malformed paths, oversized bodies, auth failures and session isolation against local mock HTTP servers. Extract browser transport and test target-specific URL construction/cancellation with `node --test tests/*.test.mjs`.
- [ ] Desktop UI and controllers: add Tauri commands/capabilities, tray, hide/quit lifecycle, autostart and directory actions. Build a local dashboard with actual counters, interfaces, process resource table, period history and connection settings. Reuse the existing NAS App for remote targets, keeping credentials and native permissions outside the WebView.
- [ ] Packaging: add independent desktop version, icons, build scripts and Windows Actions workflow. Run Rust tests, frontend tests and both Vite builds. Build `.app`/`.dmg` for this Apple Silicon Mac; build Intel when the toolchain permits.
- [ ] Acceptance/delivery: open the native Mac app, inspect local sampling/history/target switching/tray, inspect a NAS read-only without saving the test password, and test cancellation/cleanup. Push GitHub, run Windows CI, inspect its result and retrieve installer artifacts. Report unsigned-package and Windows runtime-test limits accurately.

## Acceptance Commands

```sh
cargo test --manifest-path server/desktop/Cargo.toml -p traffic-lens-core
npm --prefix front-end ci
cd front-end
node --test tests/*.test.mjs
npm run build
npm run build:desktop
npm run desktop:build
```

Core test cases use temporary SQLite databases and loopback mock servers. Production NAS tests only read statistics and log in/out; no restart, stop, notification send or history deletion.
