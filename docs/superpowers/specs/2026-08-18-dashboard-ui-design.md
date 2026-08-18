# Dashboard UI Refresh Design

## Goal

Make the NAS Traffic Lens frontend more compact, readable, card-oriented, and mobile-friendly while keeping the current Vue 3 architecture and request lifecycle. The overview page becomes a monitoring dashboard, Docker status becomes icon-led, and monitoring rules/channels become collapsed cards that only render editing controls when opened.

## Scope

- Overview: strengthen the dashboard hierarchy with a summary strip, visual direction indicators, compact status cards, public cumulative totals, and a freshness-aware collector state. Historical curves remain on the dedicated history page so the overview does not add another polling request.
- Docker: replace raw English state text with localized state labels, status icons, color states, and denser cards. Keep statistics lazy and do not add background requests.
- Monitoring center: make runtime, rules, container protection, and notification channels visually separate. Each rule/channel is collapsed by default and expands for editing. Add empty states and card counts.
- Responsive behavior: keep the sidebar usable on narrow screens, preserve touch-sized controls, reduce nested padding, and prevent horizontal overflow except for intentionally wide tables.
- Theme: preserve the existing light/dark switch and update surfaces, borders, and accent usage without introducing a new dependency.

## Design Decisions

1. Keep `front-end/src/App.vue` as the page controller because its existing API timers and dialogs are tightly coupled; use small local render helpers and state maps instead of a broad rewrite.
2. Use CSS grid and `details`-style state managed by Vue (`expandedCards`) so collapsed cards do not mount large form sections. The card shell remains available for status scanning.
3. Use Lucide icons for status and actions. English Docker runtime states are converted at render time, so persisted API values remain unchanged.
4. Do not add polling to closed cards. Docker stats remain opt-in and monitoring settings remain saved through the existing APIs.
5. Existing data remains the source of truth. The UI must tolerate missing history, GPU/NPU, temperature, or Docker detail fields without throwing. Collector freshness is tracked separately from the last successful payload so a stale screen cannot report a healthy collector.

## Acceptance Criteria

- Overview shows a clear first-viewport dashboard with the five key metrics, a public traffic emphasis, and compact status/alert sections on desktop and mobile.
- Docker cards show recognizable state icons and Chinese labels for running, stopped, restarting, paused, and unknown states; cards remain readable at 390px width.
- Monitoring rules, container protection rules, and notification channels are collapsed initially; expanding one card exposes its current editing controls, and adding a card opens only the new card.
- Existing save, delete, test, refresh, dialog, and theme interactions continue to work.
- `npm run build`, `git diff --check`, and the existing backend tests pass.
