# Desktop Preview Implementation Plan

Execute inline without subagents, using the approved desktop-client design.

Goal: ship a usable Tauri preview with local resource/network totals, SQLite history, isolated NAS sessions and tray lifecycle; build/test the Mac app locally and build Windows x64 with GitHub Actions.

Architecture: two Rust crates under `server/desktop` separate the testable core from Tauri controllers. `front-end/desktop.html` loads the desktop shell; existing NAS Vue views use an extracted transport adapter. The normal NAS web build remains a separate entry point.

Constraints: no real credentials or captured personal data in fixtures or commits; local basic metrics must never be labelled WAN metrics; no privileged helper, driver, local process actions or full per-process network attribution in this preview. Existing NAS operations require an authenticated target and retain their confirmation dialogs.

## Tasks

- [x] Core metrics and storage: Rust system sampler, bounded in-memory counters and transactional SQLite stores. Synthetic tests cover baselines, resets, sleep gaps, restart persistence, interface isolation and history windows; process identity includes PID and start time.
- [x] NAS transport: validated URL/path, bounded HTTP/SSE, per-profile cookies, optional OS credential storage and cancellation. Mock tests cover redirects, malformed paths, oversized responses, auth failures and session isolation; frontend transport tests cover stream bytes and disposed targets. Real NAS read-only Rust probe returned HTTP 200 and logged out without saving the password.
- [x] Desktop UI and controllers: Tauri capabilities, tray, hide/quit, single instance, optional autostart and fixed directory actions. Native Mac UI verified local values, process search, charts, history restoration, theme and source settings. Existing NAS Vue views use the injected transport.
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

Mac GUI NAS acceptance limitation: macOS 27 rejected local-network access for the ad-hoc-signed app, with `No team ID found` in the OS log. There is no installed Apple signing identity. Local monitoring and the same Rust transport run as a read-only development probe were verified; signed GUI LAN acceptance remains pending. No system privacy protections were bypassed.
