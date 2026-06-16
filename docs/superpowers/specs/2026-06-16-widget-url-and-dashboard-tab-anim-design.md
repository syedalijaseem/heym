# Widget URL link + Dashboard tab hover animation — Design

Date: 2026-06-16

Two small, independent changes to the dashboard experience.

## Feature 1 — Widget external URL

### Goal
Let a dashboard widget carry an optional URL set on the workflow canvas. When set, the
widget card shows an external-link icon next to its title; clicking the icon opens the URL
in a new browser tab. The property is available for **all** widget (chart) types.

### Data flow (existing, reused)
Canvas `chartOutput` node config → `build_chart_payload(node_data, source_data)`
→ stored as `cached_payload` → `WidgetDataResponse.payload` → `DashboardWidgetCard.vue`.
The `title` and `unit` fields already work exactly this way; `url` follows the same path.

### Changes

1. **Canvas config field** — `frontend/src/components/Panels/PropertiesPanel.vue`,
   `chartOutput` template. Add a **Website URL** field rendered as `ExpressionInput`
   (same component/pattern as the existing **Title** field), placed right after Title so it
   shows for every chart type. Bound to `selectedNode.data.url` via
   `updateNodeData('url', $event)`. Register it in `chartOutputExpressionFields` /
   `ChartOutputExpressionFieldKey` so navigation/expand dialogs include it. Placeholder:
   `https://… (optional)`.

2. **Payload build** — `backend/app/services/chart_payload.py`, `build_chart_payload`.
   After computing the per-type payload, if `config.get("url")` is a non-empty string,
   set `payload["url"] = url.strip()`. Applies to every chart type (added once near the
   top, after `title`, so all return branches include it). Keep the function side-effect free.

3. **Types** — `frontend/src/types/dashboard.ts`: add `url?: string` to `ChartPayload`.

4. **Widget card** — `frontend/src/components/Dashboards/DashboardWidgetCard.vue`.
   - Add a computed `externalUrl` that returns `payload.value?.url` only when it is a
     safe absolute `http(s)` URL (parsed via `new URL()`, protocol in `{http:, https:}`);
     otherwise `null`. This rejects `javascript:`/`data:`/relative values — important
     because the URL can come from a dynamic expression over upstream data (XSS guard).
   - In the header, when `externalUrl` is set, render a small `ExternalLink` (lucide)
     anchor/button immediately after the title button, before the action icon row.
     `target="_blank"`, `rel="noopener noreferrer"`, `title="Open link"`,
     styled like the existing header action buttons
     (`rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground`).
   - Title click behavior is unchanged (still opens inline rename).

### Security
Only `http://` and `https://` absolute URLs render the icon. Any other scheme or an
unparseable value yields no icon and no link. This is enforced in the frontend computed
(the click target) and is the authoritative guard.

### Tests
`backend/tests/` — extend the chart_payload test module:
- `url` is copied into the payload when present (for at least one representative chart
  type, e.g. `bar`, and one scalar type, e.g. `numeric`).
- empty/missing `url` produces no `url` key.
Frontend has no test harness (per repo convention) — verify via lint + typecheck + manual.

## Feature 2 — Dashboard tab hover animation

### Goal
Every nav tab in `DashboardNav.vue` has a per-tab icon hover animation except the
**Dashboard** tab (no `data-tab-id="dashboard"` rule exists). Add one consistent with
the others.

### Change
`frontend/src/components/Layout/DashboardNav.vue`, `<style scoped>`, per-tab hover block.
Add:
```css
.tab-item[data-tab-id="dashboard"]:hover .tab-icon { animation: icon-pop 0.35s ease-out; }
```
Reuses the existing `icon-pop` keyframe (same as the `templates` tab, also a layout-type
icon). Respects the existing `prefers-reduced-motion` reset already in the file.

### Tests
None (CSS-only, no test harness for frontend). Verify visually + lint/typecheck.

## Out of scope
- Per-widget URL stored separately from the chart payload (widget-level column). Reusing
  the payload path matches the "given on the canvas" requirement and the existing `title`
  pattern.
- Editing the URL from the dashboard widget settings dialog.

## Verification
- `bun run lint && bun run typecheck` (frontend)
- `SECRET_KEY=test-secret-key-for-tests-only-32-bytes ./run_tests.sh` (backend) or targeted
  chart_payload test run.
- Manual: set a URL on a chartOutput node, open dashboard, confirm icon appears and opens
  the link in a new tab; confirm a `javascript:` value shows no icon; hover the Dashboard tab.
