# Desktop NAS workspace, navigation and updates

Goal: provide per-NAS desktop/web layouts, persistent service launchers on every edition, and signed GitHub desktop updates.

Architecture: reuse the NAS Vue views and transport in a separate desktop workspace shell. Local navigation uses Rust/SQLite; NAS navigation uses authenticated Python controllers and its own SQLite table. Tauri's updater verifies signed platform-specific packages from a dedicated GitHub desktop update channel.

Constraints: no subagents; preserve all existing settings/history; no real passwords in source; no background Docker probing or navigation polling; data and actions remain scoped to the selected NAS. Desktop remains Tauri/Vue, with native HTTP and OS integration, not platform widget rendering.

- [x] Navigation: model validation, bounded atomic SQLite CRUD, authenticated router; Rust local equivalent. Test persistence, duplicate Docker imports, unsafe URLs/icons, missing records, and preservation of existing data.
- [x] Shared navigation view: grouped/searchable service cards, name/address/icon/group/notes/order maintenance, upload raster icons, explicit delete confirmation, Docker Web-port import. Mount only on demand.
- [x] NAS desktop workspace: own sidebar/header/overview layout, all existing feature views, per-profile saved layout, preserved page on mode change, canceled requests on source change, responsive dark/light styles.
- [x] Updates: official Tauri updater, public verification key, private signing key outside repository and encrypted GitHub Actions secret; check at startup/on demand, progress/error/retry and explicit install/restart; desktop-only channel manifest with Windows x64 and macOS arm64/x64.
- [ ] Delivery: Python/Rust/frontend tests and builds, native/browser inspection; Mac packages and Windows CI; version bump, docs, source push and signed release/channel publication. Record actual runtime limitations.

Tests: `npm --prefix front-end test`; `cargo test --manifest-path server/desktop/Cargo.toml -p traffic-lens-core`; `cargo clippy --manifest-path server/desktop/Cargo.toml --all-targets -- -D warnings`; Python unittest navigation and existing audit suite. Build both web and desktop and verify signed update artifacts before publishing manifests.
