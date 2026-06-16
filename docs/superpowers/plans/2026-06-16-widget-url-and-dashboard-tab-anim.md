# Widget URL link + Dashboard tab hover animation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional URL to dashboard widgets (set on the canvas `chartOutput` node) that surfaces as an external-link icon in the widget title, and give the Dashboard nav tab the hover animation every other tab already has.

**Architecture:** The `chartOutput` node config flows through `build_chart_payload()` into the cached payload returned to `DashboardWidgetCard.vue` — the same path `title`/`unit` already use. We add a `url` config field, copy it into the payload (backend), expose `url?` on the `ChartPayload` type, and render a sanitized external-link button in the widget card. The tab animation is a one-line CSS rule.

**Tech Stack:** Vue 3 (`<script setup>`, Composition API), TypeScript (strict), Python 3.11 + FastAPI, pytest.

---

## File Structure

- `backend/app/services/chart_payload.py` — add `url` passthrough into payload (all chart types).
- `backend/tests/test_chart_payload.py` — tests for `url` present / absent / non-string.
- `frontend/src/types/dashboard.ts` — add `url?: string` to `ChartPayload`.
- `frontend/src/components/Panels/PropertiesPanel.vue` — add **Website URL** `ExpressionInput` field to the `chartOutput` config (canvas), register it in the expression-field list/type.
- `frontend/src/components/Dashboards/DashboardWidgetCard.vue` — sanitized `externalUrl` computed + `ExternalLink` icon button in the header.
- `frontend/src/components/Layout/DashboardNav.vue` — Dashboard tab hover animation CSS rule.

---

## Task 1: Backend — copy `url` into the chart payload

**Files:**
- Modify: `backend/app/services/chart_payload.py:49-57`
- Test: `backend/tests/test_chart_payload.py`

- [ ] **Step 1: Write the failing tests**

Add these methods to the `TestBuildChartPayload` class in `backend/tests/test_chart_payload.py`:

```python
    def test_url_passthrough_for_bar(self):
        config = {
            "chartType": "bar",
            "labelField": "month",
            "valueField": "revenue",
            "url": "https://example.com/report",
        }
        data = [{"month": "Jan", "revenue": 120}]
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["url"], "https://example.com/report")

    def test_url_passthrough_for_numeric_and_is_trimmed(self):
        config = {"chartType": "numeric", "valueField": "count", "url": "  https://example.com  "}
        data = [{"count": 5}]
        payload = build_chart_payload(config, data)
        self.assertEqual(payload["url"], "https://example.com")

    def test_no_url_key_when_missing_or_blank(self):
        for url_val in (None, "", "   "):
            config = {"chartType": "bar", "labelField": "m", "valueField": "v", "url": url_val}
            payload = build_chart_payload(config, [{"m": "Jan", "v": 1}])
            self.assertNotIn("url", payload)

    def test_no_url_key_when_non_string(self):
        config = {"chartType": "bar", "labelField": "m", "valueField": "v", "url": 123}
        payload = build_chart_payload(config, [{"m": "Jan", "v": 1}])
        self.assertNotIn("url", payload)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_chart_payload.py -v -k url`
Expected: FAIL — `KeyError: 'url'` / assertion errors (no `url` handling yet).

- [ ] **Step 3: Add the `url` passthrough**

In `backend/app/services/chart_payload.py`, the start of `build_chart_payload` currently reads:

```python
    chart_type = config.get("chartType", "bar")
    title = config.get("title")
    rows = _resolve_rows(data, config.get("dataPath"))

    payload: dict = {"type": chart_type}
    if title:
        payload["title"] = title
```

Add the `url` block immediately after the `title` block (before any chart-type branch, so it
applies to every return path):

```python
    chart_type = config.get("chartType", "bar")
    title = config.get("title")
    rows = _resolve_rows(data, config.get("dataPath"))

    payload: dict = {"type": chart_type}
    if title:
        payload["title"] = title

    url = config.get("url")
    if isinstance(url, str) and url.strip():
        payload["url"] = url.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_chart_payload.py -v`
Expected: PASS (all existing + 4 new).

- [ ] **Step 5: Lint/format backend**

Run: `cd backend && uv run ruff format app/services/chart_payload.py tests/test_chart_payload.py && uv run ruff check app/services/chart_payload.py tests/test_chart_payload.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/chart_payload.py backend/tests/test_chart_payload.py
git commit -m "feat: pass optional widget url through chart payload"
```

---

## Task 2: Frontend type — add `url` to ChartPayload

**Files:**
- Modify: `frontend/src/types/dashboard.ts:7-33`

- [ ] **Step 1: Add the field**

In `frontend/src/types/dashboard.ts`, add `url?: string;` to the `ChartPayload` interface, right after the `title?: string;` line (currently line 32):

```typescript
  max?: number;
  title?: string;
  // Optional external link set on the chartOutput node; rendered as an icon in the widget title.
  url?: string;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && bun run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/dashboard.ts
git commit -m "feat: add url field to ChartPayload type"
```

---

## Task 3: Canvas — add Website URL field to chartOutput config

**Files:**
- Modify: `frontend/src/components/Panels/PropertiesPanel.vue:493-503` (type union)
- Modify: `frontend/src/components/Panels/PropertiesPanel.vue:3086` (expression fields list)
- Modify: `frontend/src/components/Panels/PropertiesPanel.vue:8678-8699` (template, after Title)

- [ ] **Step 1: Add `"url"` to the expression-field key type**

Change the `ChartOutputExpressionFieldKey` union (line 493) to include `"url"`:

```typescript
type ChartOutputExpressionFieldKey =
  | "text"
  | "valueField"
  | "dataPath"
  | "labelField"
  | "xField"
  | "yField"
  | "min"
  | "max"
  | "unit"
  | "title"
  | "url";
```

- [ ] **Step 2: Register the field in `chartOutputExpressionFields`**

In the `chartOutputExpressionFields` computed, the tail currently reads (line ~3086):

```typescript
  fields.push({ key: "title", label: "Title" });
  return fields;
```

Change it to also push the URL field (shown for all chart types, after Title):

```typescript
  fields.push({ key: "title", label: "Title" });
  fields.push({ key: "url", label: "Website URL" });
  return fields;
```

- [ ] **Step 3: Add the Website URL input to the template**

In the `chartOutput` template, immediately after the **Title** `<div class="space-y-2">…</div>`
block (which ends at line ~8699, just before the closing `</template>` at line 8700), add:

```html
            <div class="space-y-2">
              <Label>Website URL</Label>
              <ExpressionInput
                :ref="(el: unknown) => setChartOutputExpressionInputRef('url', el)"
                :model-value="selectedNode.data.url || ''"
                placeholder="https://… (optional)"
                single-line
                :nodes="workflowStore.nodes"
                :node-results="workflowStore.nodeResults"
                :edges="workflowStore.edges"
                :current-node-id="selectedNode.id"
                :dialog-node-label="selectedNodeEvaluateDialogLabel"
                dialog-key-label="Website URL"
                field-key="url"
                :navigation-enabled="chartOutputExpressionFieldCount > 1"
                :navigation-index="chartOutputExpressionFieldIndex('url')"
                :navigation-total="chartOutputExpressionFieldCount"
                @navigate="handleChartOutputExpressionFieldNavigate"
                @register-field-index="onChartOutputRegisterExpressionFieldIndex"
                @update:model-value="updateNodeData('url', $event)"
              />
            </div>
```

- [ ] **Step 4: Lint + typecheck**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: PASS. (`updateNodeData`, `selectedNode.data` are dynamic — no new type needed.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Panels/PropertiesPanel.vue
git commit -m "feat: add Website URL field to chartOutput node config"
```

---

## Task 4: Widget card — render sanitized external-link icon

**Files:**
- Modify: `frontend/src/components/Dashboards/DashboardWidgetCard.vue:1-9` (imports)
- Modify: `frontend/src/components/Dashboards/DashboardWidgetCard.vue:24` (computed near `payload`)
- Modify: `frontend/src/components/Dashboards/DashboardWidgetCard.vue:157-165` (header template)

- [ ] **Step 1: Import `ExternalLink` and `computed`**

Line 1 currently:

```typescript
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
```
Change to add `computed`:

```typescript
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
```

Line 5 currently:

```typescript
import { Loader2, MoreVertical, Pencil, RefreshCw, Settings, Sparkles, Trash2 } from "lucide-vue-next";
```
Change to add `ExternalLink` (keep alphabetical-ish order consistent with the file):

```typescript
import { ExternalLink, Loader2, MoreVertical, Pencil, RefreshCw, Settings, Sparkles, Trash2 } from "lucide-vue-next";
```

- [ ] **Step 2: Add the `externalUrl` computed**

After the `payload` ref declaration (line 24: `const payload = ref<ChartPayload | null>(null);`), add:

```typescript
// Only surface http(s) links. The url can come from a dynamic expression over upstream
// data, so reject javascript:/data:/relative values to avoid an injected-link XSS.
const externalUrl = computed<string | null>(() => {
  const raw = payload.value?.url;
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
});
```

- [ ] **Step 3: Add the icon button to the header**

In the template, the title `<button v-else …>{{ widget.title }}</button>` block ends at line 164
(`</button>`), followed by a blank line and the `<!-- sm+: inline icon row -->` comment.
Insert the link button between the title button and that comment:

```html
      </button>

      <a
        v-if="externalUrl"
        :href="externalUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
        title="Open link"
      >
        <ExternalLink class="h-3.5 w-3.5" />
      </a>

      <!-- sm+: inline icon row -->
```

- [ ] **Step 4: Lint + typecheck**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Dashboards/DashboardWidgetCard.vue
git commit -m "feat: show external-link icon on widgets with a url"
```

---

## Task 5: Dashboard nav tab hover animation

**Files:**
- Modify: `frontend/src/components/Layout/DashboardNav.vue:303-318` (per-tab hover block)

- [ ] **Step 1: Add the CSS rule**

In the `<style scoped>` "per-tab hover animations" block, after the `templates` line
(line 306) add a rule for the dashboard tab (reuse `icon-pop`, consistent with `templates`):

```css
.tab-item[data-tab-id="templates"]:hover       .tab-icon { animation: icon-pop    0.35s ease-out; }
.tab-item[data-tab-id="dashboard"]:hover       .tab-icon { animation: icon-pop    0.35s ease-out; }
```

- [ ] **Step 2: Lint + typecheck**

Run: `cd frontend && bun run lint && bun run typecheck`
Expected: PASS.

- [ ] **Step 3: Manual visual check**

Hover the **Dashboard** tab in the nav — the icon should "pop" (scale up and back) like the
Templates tab. Confirm it respects reduced-motion (the existing `prefers-reduced-motion` rule
already disables `.tab-icon` animations).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Layout/DashboardNav.vue
git commit -m "feat: add hover animation to dashboard nav tab"
```

---

## Task 6: Full verification

- [ ] **Step 1: Backend tests + frontend gates**

Run from repo root:
```bash
cd frontend && bun run lint && bun run typecheck
cd ../backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_chart_payload.py -v
```
Expected: all PASS.

- [ ] **Step 2: Manual end-to-end check**

1. Open a workflow with a `chartOutput` node; set **Website URL** to `https://example.com`.
2. Add/refresh the dashboard widget for it → an external-link icon appears next to the title;
   clicking opens `https://example.com` in a new tab.
3. Set the URL to `javascript:alert(1)` → no icon renders.
4. Leave URL blank → no icon renders.
5. Hover the Dashboard nav tab → icon pops.

---

## Notes
- Per repo convention there is no frontend test harness; frontend changes are verified via
  `bun run lint` + `bun run typecheck` + manual checks.
- This is a medium UI feature — if doc updates are wanted, the `heym-documentation` skill
  covers `frontend/src/docs/content/nodes/chart-output-node.md` (the Website URL field) after
  implementation. Not required for this plan to be functionally complete.
