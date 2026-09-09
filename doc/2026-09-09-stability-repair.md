# Stability Repair Plan

Goal: fix the verified audit findings without changing existing saved rules or NAS configuration.

Architecture: retain Vue/FastAPI/Go; keep network collection in Go, persist bounded aggregates in SQLite, and expose Docker actions through the existing protected API. Execute inline without subagents.

## Constraints

- No real credentials in source, documentation, fixtures, images or commits.
- Never exercise restart/stop, notification delivery or history deletion against the production NAS during verification.
- Keep existing SQLite settings and schema compatible; no database replacement.
- Build both linux/amd64 and linux/arm64 with a new version.

## Work

- [x] Collector boundary: test loopback binding, POST-only mutations, large valid JSON and oversized response failure; add bounded response parsing and short snapshot cache.
- [x] Container protection: test duration for restart/stop, recovery between spikes, durable action limits, failed actions, disk rate deltas; persist only action transitions and expose explicit reset.
- [x] Go integration: test common rate/alert input, complete process aggregate persistence, restart-safe deltas and Go-based alert evidence; avoid silent zero fallback.
- [x] Configuration safety: test AI list edits preserve unseen entries and explicit deletion previews; provide transactional history-only cleanup, preserving settings, labels and evidence.
- [x] API isolation: verify slow Docker/system/notification calls do not block the event loop; coalesce same-container stats requests.
- [x] Frontend lifecycle: test latest-response handling, hidden-page polling and timer cleanup; show recoverable errors and history refresh state.
- [x] Verification: run Python, Go (including race checks), frontend tests/build, image smoke tests and credential scan; build both architecture images. Delivery uses the existing GitHub remote and Docker push script.

## Verification Commands

```sh
./.venv/bin/python -m unittest discover -s server/tests -p 'test_audit*.py' -v
cd server/go-collector
go test -race ./...
cd ../../front-end
node --test tests/*.test.mjs
npm run build
```

Existing function-style Python suites must also run through their test entry points or the discovery harness. Production NAS inspection is read-only; passing local checks does not mean the remote image has been upgraded.

## Results

- Version: `2026.09.09-1`; no Compose or SQLite schema migration required.
- Python: 25 new regression tests plus 69 existing function-style tests pass locally. Entrypoint helper tests pass.
- Go: `go test -race ./...` passes for both packages.
- Frontend: 8 tests and production build pass. The existing large JavaScript chunk warning remains; this repair does not reorganize the entire frontend.
- Local browser: history period totals and curves change together; curves survive navigation; mobile history has no horizontal overflow; protection lock state and reset control are visible.
- Isolated Linux containers: main JSON endpoints respond successfully; unauthenticated protected routes return 401; Go is reachable only on loopback and rejects GET mutations with 405.
- Both final amd64/arm64 images pass the 25 regression tests on Python 3.12. A paused collector in the isolated test container shows a recoverable error in the connections dialog; resuming it clears the error after refresh.
- A short 300-request local check returned no errors; Python RSS changed from 89.6 to 90.1 MiB. This is not a multi-day NAS memory or throughput benchmark.
- History-only cleanup preserves settings, labels, alerts and evidence in a transactional regression test. Production data was not cleared or modified.
- Existing process history cannot be reconstructed if an older version never saved it. Process history includes observed LAN and WAN traffic; WAN interface totals retain their separate scope.
