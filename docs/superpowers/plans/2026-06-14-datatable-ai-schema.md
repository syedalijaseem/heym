# DataTable AI-Assisted Schema Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users generate DataTable column schemas from a plain-text description or pasted JSON via an LLM, review/edit the columns inline, then create a new table or append columns to an existing one.

**Architecture:** A new backend endpoint `POST /api/data-tables/generate-schema` resolves the user's LLM credential, calls the model with a strict JSON-schema prompt, parses the fenced ```json block, and normalizes the columns server-side (type coercion, blank/dupe drop, id/order assignment). A new Vue dialog `DataTableAISchemaDialog.vue` collects the prompt + credential/model, calls the endpoint, and shows a fully editable column form before saving via the existing `dataTablesApi.create` / `update` endpoints. Wired into `DataTablePanel.vue` at two entry points (create + extend).

**Tech Stack:** FastAPI + Pydantic + SQLAlchemy async (backend), OpenAI-compatible client via `get_openai_client`, Vue 3 `<script setup>` + TypeScript strict + Tailwind (frontend), pytest (`unittest.IsolatedAsyncioTestCase` + `MagicMock`/`AsyncMock`).

---

## File Structure

**Backend**
- Modify `backend/app/models/schemas.py` — add `DataTableSchemaGenerateRequest` + `DataTableSchemaSuggestionResponse` (after the existing DataTable schemas, ~line 1264).
- Modify `backend/app/api/data_tables.py` — add imports, helpers (`_normalize_generated_columns`, `_extract_schema_payload`, prompt builders) and the `generate_data_table_schema` endpoint.
- Create `backend/tests/test_data_table_schema_generation.py` — unit tests for the helpers and endpoint.

**Frontend**
- Modify `frontend/src/types/dataTable.ts` — add `DataTableSchemaSuggestion`.
- Modify `frontend/src/services/api.ts` — add `dataTablesApi.generateSchema` + type import.
- Create `frontend/src/components/DataTable/DataTableAISchemaDialog.vue` — the two-phase dialog.
- Modify `frontend/src/components/DataTable/DataTablePanel.vue` — wire in both entry points.

**Docs**
- Update DataTable docs via the `heym-documentation` skill (Task 7).

Notes that hold across tasks:
- The existing `DataTableColumnDef` (schemas.py:1213) is the canonical column shape: `id, name, type, required, defaultValue, unique, order`. `type` is pattern-validated to `string|number|boolean|date|json`. `required` == "notEmpty".
- The `Dialog.vue` UI component already closes on ESC (`closeOnEscape` defaults true, emits `close`) — no custom ESC handling needed.
- `ai_assistant.py` does NOT import `data_tables.py`, so importing helpers from `ai_assistant` into `data_tables` is safe (no circular import). Tests patch these names in the **`app.api.data_tables`** namespace.

---

## Task 1: Backend schemas

**Files:**
- Modify: `backend/app/models/schemas.py` (after `DataTableListResponse`, before `DataTableRowCreate` at line 1267)

- [ ] **Step 1: Add the request/response Pydantic models**

Insert after `DataTableListResponse` (line 1265) in `backend/app/models/schemas.py`:

```python
class DataTableSchemaGenerateRequest(BaseModel):
    credential_id: uuid.UUID
    model: str
    prompt: str = Field(min_length=1, max_length=10000)
    existing_columns: list[DataTableColumnDef] | None = None


class DataTableSchemaSuggestionResponse(BaseModel):
    name: str
    description: str | None = None
    columns: list[DataTableColumnDef] = Field(default_factory=list)
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `cd backend && uv run python -c "from app.models.schemas import DataTableSchemaGenerateRequest, DataTableSchemaSuggestionResponse; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/schemas.py
git commit -m "feat: add DataTable schema-generation request/response models"
```

---

## Task 2: Backend helpers + endpoint (TDD)

**Files:**
- Modify: `backend/app/api/data_tables.py`
- Test: `backend/tests/test_data_table_schema_generation.py`

- [ ] **Step 1: Write the failing test for the normalization helper**

Create `backend/tests/test_data_table_schema_generation.py`:

```python
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.api.data_tables import (
    _normalize_generated_columns,
    _extract_schema_payload,
    generate_data_table_schema,
)
from app.db.models import CredentialType
from app.models.schemas import DataTableColumnDef, DataTableSchemaGenerateRequest


class NormalizeGeneratedColumnsTests(unittest.TestCase):
    def test_assigns_ids_and_sequential_order(self) -> None:
        cols = _normalize_generated_columns(
            [
                {"name": "title", "type": "string"},
                {"name": "count", "type": "number", "required": True, "unique": True},
            ],
            existing_names=set(),
        )
        self.assertEqual([c.name for c in cols], ["title", "count"])
        self.assertEqual([c.order for c in cols], [0, 1])
        self.assertTrue(all(isinstance(c.id, uuid.UUID) for c in cols))
        self.assertEqual(cols[1].type, "number")
        self.assertTrue(cols[1].required)
        self.assertTrue(cols[1].unique)

    def test_coerces_unknown_type_to_string_and_drops_blank_names(self) -> None:
        cols = _normalize_generated_columns(
            [
                {"name": "weird", "type": "timestamp"},
                {"name": "  ", "type": "string"},
                {"name": "ok", "type": "DATE"},
            ],
            existing_names=set(),
        )
        self.assertEqual([c.name for c in cols], ["weird", "ok"])
        self.assertEqual(cols[0].type, "string")
        self.assertEqual(cols[1].type, "date")

    def test_dedupes_against_existing_and_within_batch_case_insensitive(self) -> None:
        cols = _normalize_generated_columns(
            [
                {"name": "Email", "type": "string"},
                {"name": "email", "type": "string"},
                {"name": "phone", "type": "string"},
            ],
            existing_names={"EMAIL"},
        )
        self.assertEqual([c.name for c in cols], ["phone"])

    def test_non_list_input_returns_empty(self) -> None:
        self.assertEqual(_normalize_generated_columns(None, set()), [])
        self.assertEqual(_normalize_generated_columns("oops", set()), [])


class ExtractSchemaPayloadTests(unittest.TestCase):
    def test_extracts_from_fenced_block(self) -> None:
        content = 'Here you go:\n```json\n{"name": "T", "columns": []}\n```\nDone.'
        self.assertEqual(_extract_schema_payload(content), {"name": "T", "columns": []})

    def test_extracts_bare_json(self) -> None:
        self.assertEqual(_extract_schema_payload('{"name": "T"}'), {"name": "T"})

    def test_returns_none_for_unparseable(self) -> None:
        self.assertIsNone(_extract_schema_payload("no json here at all"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_data_table_schema_generation.py -v`
Expected: FAIL — `ImportError: cannot import name '_normalize_generated_columns' from 'app.api.data_tables'`

- [ ] **Step 3: Add imports + helpers to `data_tables.py`**

In `backend/app/api/data_tables.py`, add `import re` after `import io` (line 2). Extend the `app.db.models` import (lines 13-21) to also import `CredentialType`. Add these new imports after the existing `from app.services.upload_limits import ...` (line 37):

```python
from app.api.ai_assistant import (
    _parse_json_object,
    get_credential_for_user,
    get_openai_client,
)
from app.models.schemas import (
    DataTableColumnDef,
    DataTableSchemaGenerateRequest,
    DataTableSchemaSuggestionResponse,
)
from app.services.encryption import decrypt_config
from app.services.llm_provider import is_reasoning_model
```

(Merge `DataTableColumnDef`, `DataTableSchemaGenerateRequest`, `DataTableSchemaSuggestionResponse` into the existing `from app.models.schemas import (...)` block at lines 23-36 rather than duplicating the import statement.)

Then add the helpers in the `# ── Helpers ──` section (after line 42):

```python
_ALLOWED_COLUMN_TYPES = {"string", "number", "boolean", "date", "json"}
_SCHEMA_JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _normalize_generated_columns(
    raw_columns: Any, existing_names: set[str]
) -> list[DataTableColumnDef]:
    """Coerce LLM-proposed columns into a valid DataTableColumnDef list.

    Drops blank names, dedupes (case-insensitive) against existing_names and within
    the batch, coerces unknown types to "string", and assigns sequential order.
    """
    if not isinstance(raw_columns, list):
        return []
    seen = {name.lower() for name in existing_names}
    result: list[DataTableColumnDef] = []
    for raw in raw_columns:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        col_type = str(raw.get("type") or "string").strip().lower()
        if col_type not in _ALLOWED_COLUMN_TYPES:
            col_type = "string"
        result.append(
            DataTableColumnDef(
                name=name,
                type=col_type,
                required=bool(raw.get("required", False)),
                unique=bool(raw.get("unique", False)),
                defaultValue=raw.get("defaultValue"),
                order=len(result),
            )
        )
    return result


def _extract_schema_payload(content: str) -> dict[str, Any] | None:
    """Pull a JSON object out of a model response (fenced block or bare JSON)."""
    candidates = [m.group(1).strip() for m in _SCHEMA_JSON_BLOCK_PATTERN.finditer(content)]
    candidates.append(content.strip())
    for candidate in candidates:
        parsed = _parse_json_object(candidate)
        if parsed is not None:
            return parsed
    return None


def _build_schema_system_prompt(extending: bool) -> str:
    base = (
        "You design schemas for a no-code data table. Given a user's description or "
        "pasted JSON, infer the columns. Reply with exactly one fenced ```json code "
        "block containing an object: "
        '{"name": string, "description": string, "columns": '
        '[{"name": string, "type": one of "string"|"number"|"boolean"|"date"|"json", '
        '"required": boolean, "unique": boolean, "defaultValue": value or null}]}. '
        "Use simple lower_snake_case column names. Do not add an id column. "
        "Return only the JSON block, no prose."
    )
    if extending:
        base += (
            " The table already exists; propose ONLY new columns that are not already "
            "present. The name and description fields will be ignored."
        )
    return base


def _build_schema_user_prompt(prompt: str, existing_cols: list[DataTableColumnDef]) -> str:
    if existing_cols:
        existing_desc = ", ".join(f"{c.name} ({c.type})" for c in existing_cols)
        return f"Existing columns: {existing_desc}\n\nRequest:\n{prompt}"
    return prompt
```

- [ ] **Step 4: Run the helper tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_data_table_schema_generation.py::NormalizeGeneratedColumnsTests tests/test_data_table_schema_generation.py::ExtractSchemaPayloadTests -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Write the failing endpoint tests**

Append to `backend/tests/test_data_table_schema_generation.py`:

```python
def _make_request(existing=None) -> DataTableSchemaGenerateRequest:
    return DataTableSchemaGenerateRequest(
        credential_id=uuid.uuid4(),
        model="gpt-4o-mini",
        prompt="A table of books with title and page count",
        existing_columns=existing,
    )


def _llm_client_returning(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = completion
    return client


class GenerateDataTableSchemaEndpointTests(unittest.IsolatedAsyncioTestCase):
    def _credential(self) -> MagicMock:
        credential = MagicMock()
        credential.id = uuid.uuid4()
        credential.type = CredentialType.openai
        credential.encrypted_config = "enc"
        return credential

    async def test_returns_normalized_suggestion(self) -> None:
        content = (
            '```json\n{"name": "Books", "description": "My books", "columns": ['
            '{"name": "title", "type": "string", "required": true}, '
            '{"name": "pages", "type": "number"}]}\n```'
        )
        with (
            patch(
                "app.api.data_tables.get_credential_for_user",
                AsyncMock(return_value=self._credential()),
            ),
            patch("app.api.data_tables.decrypt_config", return_value={"api_key": "x"}),
            patch(
                "app.api.data_tables.get_openai_client",
                return_value=(_llm_client_returning(content), "openai"),
            ),
        ):
            result = await generate_data_table_schema(
                request=_make_request(),
                current_user=MagicMock(id=uuid.uuid4()),
                db=AsyncMock(),
            )
        self.assertEqual(result.name, "Books")
        self.assertEqual(result.description, "My books")
        self.assertEqual([c.name for c in result.columns], ["title", "pages"])
        self.assertTrue(result.columns[0].required)
        self.assertEqual(result.columns[1].type, "number")

    async def test_dedupes_against_existing_columns_in_extend_mode(self) -> None:
        existing = [DataTableColumnDef(name="title", type="string", order=0)]
        content = (
            '```json\n{"name": "X", "columns": ['
            '{"name": "Title", "type": "string"}, '
            '{"name": "isbn", "type": "string"}]}\n```'
        )
        with (
            patch(
                "app.api.data_tables.get_credential_for_user",
                AsyncMock(return_value=self._credential()),
            ),
            patch("app.api.data_tables.decrypt_config", return_value={"api_key": "x"}),
            patch(
                "app.api.data_tables.get_openai_client",
                return_value=(_llm_client_returning(content), "openai"),
            ),
        ):
            result = await generate_data_table_schema(
                request=_make_request(existing=existing),
                current_user=MagicMock(id=uuid.uuid4()),
                db=AsyncMock(),
            )
        self.assertEqual([c.name for c in result.columns], ["isbn"])

    async def test_missing_credential_returns_400(self) -> None:
        with patch(
            "app.api.data_tables.get_credential_for_user",
            AsyncMock(return_value=None),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await generate_data_table_schema(
                    request=_make_request(),
                    current_user=MagicMock(id=uuid.uuid4()),
                    db=AsyncMock(),
                )
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_unparseable_output_returns_422(self) -> None:
        with (
            patch(
                "app.api.data_tables.get_credential_for_user",
                AsyncMock(return_value=self._credential()),
            ),
            patch("app.api.data_tables.decrypt_config", return_value={"api_key": "x"}),
            patch(
                "app.api.data_tables.get_openai_client",
                return_value=(_llm_client_returning("no json here"), "openai"),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await generate_data_table_schema(
                    request=_make_request(),
                    current_user=MagicMock(id=uuid.uuid4()),
                    db=AsyncMock(),
                )
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_no_usable_columns_returns_422(self) -> None:
        content = '```json\n{"name": "Empty", "columns": []}\n```'
        with (
            patch(
                "app.api.data_tables.get_credential_for_user",
                AsyncMock(return_value=self._credential()),
            ),
            patch("app.api.data_tables.decrypt_config", return_value={"api_key": "x"}),
            patch(
                "app.api.data_tables.get_openai_client",
                return_value=(_llm_client_returning(content), "openai"),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await generate_data_table_schema(
                    request=_make_request(),
                    current_user=MagicMock(id=uuid.uuid4()),
                    db=AsyncMock(),
                )
        self.assertEqual(ctx.exception.status_code, 422)
```

- [ ] **Step 6: Run the endpoint tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_data_table_schema_generation.py::GenerateDataTableSchemaEndpointTests -v`
Expected: FAIL — `ImportError: cannot import name 'generate_data_table_schema'`

- [ ] **Step 7: Add the endpoint to `data_tables.py`**

Add at the end of `backend/app/api/data_tables.py`:

```python
@router.post("/generate-schema", response_model=DataTableSchemaSuggestionResponse)
async def generate_data_table_schema(
    request: DataTableSchemaGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DataTableSchemaSuggestionResponse:
    """Generate column suggestions for a data table from a description or JSON."""
    credential = await get_credential_for_user(request.credential_id, current_user, db)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM credential not found",
        )
    if credential.type not in (
        CredentialType.openai,
        CredentialType.google,
        CredentialType.custom,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential must be an LLM type (OpenAI, Google, or Custom)",
        )

    existing_cols = request.existing_columns or []
    existing_names = {col.name for col in existing_cols}

    config = decrypt_config(credential.encrypted_config)
    client, _ = get_openai_client(credential.type, config)

    kwargs: dict[str, Any] = {
        "model": request.model,
        "messages": [
            {"role": "system", "content": _build_schema_system_prompt(bool(existing_cols))},
            {"role": "user", "content": _build_schema_user_prompt(request.prompt, existing_cols)},
        ],
        "extra_body": {"disable_reasoning": True},
    }
    if not is_reasoning_model(request.model):
        kwargs["temperature"] = 0.2

    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or ""

    payload = _extract_schema_payload(content)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not parse a table schema from the model response",
        )

    columns = _normalize_generated_columns(payload.get("columns"), existing_names)
    if not columns:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The model did not return any usable columns",
        )

    name = str(payload.get("name") or "").strip() or "New Table"
    description_raw = payload.get("description")
    description = str(description_raw).strip() if description_raw else None

    return DataTableSchemaSuggestionResponse(
        name=name,
        description=description,
        columns=columns,
    )
```

- [ ] **Step 8: Run the full test file to verify all pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run pytest tests/test_data_table_schema_generation.py -v`
Expected: PASS (12 tests)

- [ ] **Step 9: Verify no circular import + lint/format**

Run: `cd backend && SECRET_KEY=test-secret-key-for-tests-only-32-bytes uv run python -c "import app.main; print('import ok')" && uv run ruff format app/api/data_tables.py app/models/schemas.py tests/test_data_table_schema_generation.py && uv run ruff check app/api/data_tables.py tests/test_data_table_schema_generation.py`
Expected: prints `import ok`, ruff reports no errors. If the `import app.main` step raises a circular-import error, move the three `from app.api.ai_assistant import ...` names into a function-local import inside `generate_data_table_schema` (and keep tests patching `app.api.data_tables.<name>` — bind them at module top via `from app.api.ai_assistant import get_credential_for_user as get_credential_for_user` only if needed). Confirm `import app.main` is clean before continuing.

- [ ] **Step 10: Commit**

```bash
git add backend/app/api/data_tables.py backend/tests/test_data_table_schema_generation.py
git commit -m "feat: add DataTable AI schema-generation endpoint"
```

---

## Task 3: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/dataTable.ts`
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Add the suggestion type**

Append to `frontend/src/types/dataTable.ts` (after `DataTableImportResult`):

```ts
export interface DataTableSchemaSuggestion {
  name: string;
  description: string | null;
  columns: DataTableColumn[];
}
```

- [ ] **Step 2: Import the type in api.ts**

In `frontend/src/services/api.ts`, add `DataTableSchemaSuggestion` to the `@/types/dataTable` import block (lines 2475-2482), keeping alphabetical order:

```ts
import type {
  DataTable,
  DataTableImportResult,
  DataTableListItem,
  DataTableRow,
  DataTableSchemaSuggestion,
  DataTableShare,
  DataTableTeamShare,
} from "@/types/dataTable";
```

- [ ] **Step 3: Add the `generateSchema` method**

In `frontend/src/services/api.ts`, inside the `dataTablesApi` object, add after the `update` method (line 2503):

```ts
  generateSchema: async (payload: {
    credential_id: string;
    model: string;
    prompt: string;
    existing_columns?: DataTableColumn[];
  }): Promise<DataTableSchemaSuggestion> => {
    const response = await api.post<DataTableSchemaSuggestion>(
      "/data-tables/generate-schema",
      payload,
    );
    return response.data;
  },
```

Also add `DataTableColumn` to the `@/types/dataTable` import block from Step 2 (it is used in the payload type). Final import block:

```ts
import type {
  DataTable,
  DataTableColumn,
  DataTableImportResult,
  DataTableListItem,
  DataTableRow,
  DataTableSchemaSuggestion,
  DataTableShare,
  DataTableTeamShare,
} from "@/types/dataTable";
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && bun run typecheck`
Expected: PASS (no errors)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/dataTable.ts frontend/src/services/api.ts
git commit -m "feat: add generateSchema API client + DataTableSchemaSuggestion type"
```

---

## Task 4: Frontend `DataTableAISchemaDialog.vue`

**Files:**
- Create: `frontend/src/components/DataTable/DataTableAISchemaDialog.vue`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/DataTable/DataTableAISchemaDialog.vue`:

```vue
<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import { Sparkles, Trash2, Plus, ChevronDown } from "lucide-vue-next";

import type { CredentialListItem, LLMModel } from "@/types/credential";
import type { DataTable, DataTableColumn, DataTableSchemaSuggestion } from "@/types/dataTable";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Input from "@/components/ui/Input.vue";
import Label from "@/components/ui/Label.vue";
import Textarea from "@/components/ui/Textarea.vue";
import { credentialsApi, dataTablesApi } from "@/services/api";

const props = defineProps<{
  mode: "create" | "extend";
  existingTable?: DataTable | null;
}>();
const emit = defineEmits<{ created: [table: DataTable]; updated: [table: DataTable]; close: [] }>();

const COLUMN_TYPES: DataTableColumn["type"][] = ["string", "number", "boolean", "date", "json"];

const phase = ref<"input" | "review">("input");
const prompt = ref("");
const credentialId = ref("");
const modelName = ref("");
const credentials = ref<CredentialListItem[]>([]);
const models = ref<LLMModel[]>([]);
const generating = ref(false);
const saving = ref(false);
const error = ref("");

const name = ref("");
const description = ref("");
const columns = ref<DataTableColumn[]>([]);

const existingColumns = computed<DataTableColumn[]>(() => props.existingTable?.columns ?? []);

const canGenerate = computed(
  () => prompt.value.trim().length > 0 && credentialId.value !== "" && modelName.value !== "",
);
const canSave = computed(
  () =>
    columns.value.length > 0 &&
    columns.value.every((c) => c.name.trim().length > 0) &&
    (props.mode === "extend" || name.value.trim().length > 0),
);

watchEffect(async () => {
  if (credentials.value.length === 0) {
    credentials.value = await credentialsApi.listLLM();
    if (credentials.value.length > 0) {
      credentialId.value = credentials.value[0].id;
    }
  }
});

async function loadModels(): Promise<void> {
  modelName.value = "";
  models.value = [];
  if (!credentialId.value) return;
  models.value = await credentialsApi.getModels(credentialId.value);
  if (models.value.length > 0) {
    modelName.value = models.value[models.value.length - 1].id;
  }
}

watchEffect(() => {
  if (credentialId.value) void loadModels();
});

async function handleGenerate(): Promise<void> {
  if (!canGenerate.value) return;
  generating.value = true;
  error.value = "";
  try {
    const suggestion: DataTableSchemaSuggestion = await dataTablesApi.generateSchema({
      credential_id: credentialId.value,
      model: modelName.value,
      prompt: prompt.value.trim(),
      existing_columns: props.mode === "extend" ? existingColumns.value : undefined,
    });
    columns.value = suggestion.columns;
    if (props.mode === "create") {
      name.value = suggestion.name;
      description.value = suggestion.description ?? "";
    }
    phase.value = "review";
  } catch {
    error.value = "Couldn't generate a schema. Try rephrasing your description.";
  } finally {
    generating.value = false;
  }
}

function addColumn(): void {
  columns.value.push({
    id: crypto.randomUUID(),
    name: "",
    type: "string",
    required: false,
    defaultValue: null,
    unique: false,
    order: columns.value.length,
  });
}

function removeColumn(id: string): void {
  columns.value = columns.value.filter((c) => c.id !== id);
}

async function handleSave(): Promise<void> {
  if (!canSave.value) return;
  saving.value = true;
  error.value = "";
  const normalized = columns.value.map((c, i) => ({
    ...c,
    name: c.name.trim(),
    defaultValue: c.defaultValue === "" ? null : c.defaultValue,
    order: i,
  }));
  try {
    if (props.mode === "create") {
      const table = await dataTablesApi.create({
        name: name.value.trim(),
        description: description.value.trim() || undefined,
        columns: normalized,
      });
      emit("created", table);
    } else if (props.existingTable) {
      const merged = [
        ...existingColumns.value,
        ...normalized.map((c, i) => ({ ...c, order: existingColumns.value.length + i })),
      ];
      const table = await dataTablesApi.update(props.existingTable.id, { columns: merged });
      emit("updated", table);
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : "Failed to save";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Dialog
    :open="true"
    :title="mode === 'create' ? 'Generate Table with AI' : 'Generate Columns with AI'"
    @close="emit('close')"
  >
    <div class="flex flex-col gap-4 p-4">
      <!-- ── INPUT PHASE ── -->
      <template v-if="phase === 'input'">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <Label>LLM Credential</Label>
            <div class="relative mt-1">
              <select
                v-model="credentialId"
                class="w-full appearance-none rounded border bg-background px-3 py-2 pr-8 text-sm"
              >
                <option
                  v-for="cred in credentials"
                  :key="cred.id"
                  :value="cred.id"
                >
                  {{ cred.name }}
                </option>
              </select>
              <ChevronDown class="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            </div>
          </div>
          <div>
            <Label>Model</Label>
            <div class="relative mt-1">
              <select
                v-model="modelName"
                class="w-full appearance-none rounded border bg-background px-3 py-2 pr-8 text-sm"
              >
                <option
                  v-for="m in models"
                  :key="m.id"
                  :value="m.id"
                >
                  {{ m.id }}
                </option>
              </select>
              <ChevronDown class="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            </div>
          </div>
        </div>

        <div>
          <Label>Describe your table, or paste JSON</Label>
          <Textarea
            v-model="prompt"
            placeholder="e.g. A table of books with title, author, page count and whether I've read it"
            class="mt-1"
            :rows="5"
          />
        </div>

        <p
          v-if="credentials.length === 0"
          class="text-sm text-muted-foreground"
        >
          No LLM credentials found. Add one in Settings to use AI generation.
        </p>

        <div
          v-if="error"
          class="text-sm text-red-500"
        >
          {{ error }}
        </div>

        <div class="flex justify-end">
          <Button
            :disabled="!canGenerate || generating"
            @click="handleGenerate"
          >
            <Sparkles class="mr-1 h-4 w-4" />
            {{ generating ? "Generating..." : "Generate" }}
          </Button>
        </div>
      </template>

      <!-- ── REVIEW PHASE ── -->
      <template v-else>
        <div
          v-if="mode === 'create'"
          class="flex flex-col gap-3"
        >
          <div>
            <Label>Name</Label>
            <Input
              v-model="name"
              placeholder="Table name"
              class="mt-1"
            />
          </div>
          <div>
            <Label>Description (optional)</Label>
            <Textarea
              v-model="description"
              class="mt-1"
              :rows="2"
            />
          </div>
        </div>

        <!-- existing columns (extend mode, read-only) -->
        <div v-if="mode === 'extend' && existingColumns.length > 0">
          <Label>Existing columns</Label>
          <div class="mt-1 flex flex-wrap gap-1">
            <span
              v-for="col in existingColumns"
              :key="col.id"
              class="rounded border bg-muted px-2 py-0.5 text-xs text-muted-foreground"
            >
              {{ col.name }} ({{ col.type }})
            </span>
          </div>
        </div>

        <div>
          <Label>{{ mode === "extend" ? "New columns" : "Columns" }}</Label>
          <div class="mt-1 flex flex-col gap-2">
            <div
              v-for="col in columns"
              :key="col.id"
              class="flex items-center gap-2 rounded border p-2"
            >
              <Input
                v-model="col.name"
                placeholder="name"
                class="flex-1"
              />
              <select
                v-model="col.type"
                class="rounded border bg-background px-2 py-2 text-sm"
              >
                <option
                  v-for="t in COLUMN_TYPES"
                  :key="t"
                  :value="t"
                >
                  {{ t }}
                </option>
              </select>
              <Input
                v-model="col.defaultValue as string"
                placeholder="default"
                class="w-24"
              />
              <label class="flex items-center gap-1 text-xs">
                <input
                  v-model="col.unique"
                  type="checkbox"
                >
                unique
              </label>
              <label class="flex items-center gap-1 text-xs">
                <input
                  v-model="col.required"
                  type="checkbox"
                >
                notEmpty
              </label>
              <button
                type="button"
                class="text-muted-foreground hover:text-red-500"
                @click="removeColumn(col.id)"
              >
                <Trash2 class="h-4 w-4" />
              </button>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            class="mt-2"
            @click="addColumn"
          >
            <Plus class="mr-1 h-4 w-4" />
            Add column
          </Button>
        </div>

        <div
          v-if="error"
          class="text-sm text-red-500"
        >
          {{ error }}
        </div>

        <div class="flex justify-between">
          <Button
            variant="outline"
            @click="phase = 'input'"
          >
            Back
          </Button>
          <Button
            :disabled="!canSave || saving"
            @click="handleSave"
          >
            {{ saving ? "Saving..." : mode === "create" ? "Create Table" : "Add Columns" }}
          </Button>
        </div>
      </template>
    </div>
  </Dialog>
</template>
```

- [ ] **Step 2: Verify Button supports the `variant="outline"` / `size="sm"` props used above**

Run: `grep -n "variant\|size" frontend/src/components/ui/Button.vue | head`
Expected: `Button.vue` declares `variant` (including `outline`) and `size` (including `sm`) props. If `outline` or `sm` are not valid values there, drop those props (plain `<Button>`), then re-run typecheck.

- [ ] **Step 3: Typecheck + lint**

Run: `cd frontend && bun run typecheck && bun run lint`
Expected: PASS. Fix any strict-mode issues (e.g. unused imports) inline.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DataTable/DataTableAISchemaDialog.vue
git commit -m "feat: add DataTableAISchemaDialog component"
```

---

## Task 5: Wire into `DataTablePanel.vue`

**Files:**
- Modify: `frontend/src/components/DataTable/DataTablePanel.vue`

- [ ] **Step 1: Import the dialog**

After the existing `import DataTableImportDialog from "./DataTableImportDialog.vue";` (line 37), add:

```ts
import DataTableAISchemaDialog from "./DataTableAISchemaDialog.vue";
```

Also ensure `Sparkles` is imported from `lucide-vue-next` in this file (add it to the existing lucide import if not already present).

- [ ] **Step 2: Add state refs**

Near the other dialog refs (`showImportDialog`, line 99), add:

```ts
const showAIDialog = ref(false);
const aiDialogMode = ref<"create" | "extend">("create");
```

- [ ] **Step 3: Add handlers**

Add these functions near the other column/table handlers (e.g. after `handleColumnDelete`, ~line 307):

```ts
function openAICreate() {
  aiDialogMode.value = "create";
  showAIDialog.value = true;
}

function openAIExtend() {
  aiDialogMode.value = "extend";
  showAIDialog.value = true;
}

async function handleAICreated(table: DataTable) {
  showAIDialog.value = false;
  await loadTables();
  openTable(table.id);
}

async function handleAIUpdated(table: DataTable) {
  showAIDialog.value = false;
  selectedTable.value = table;
}
```

Confirm `DataTable` is imported as a type in this file; if not, add it to the `@/types/dataTable` type import. Confirm `openTable`, `loadTables`, and `selectedTable` exist (they do — used elsewhere in this file).

- [ ] **Step 4: Add the "Generate with AI" button to the table-list header**

Next to the existing "New DataTable" trigger button (the header `<Button @click="showCreateDialog = true">` near line 669), add a sibling button:

```vue
<Button
  variant="outline"
  @click="openAICreate"
>
  <Sparkles class="mr-1 h-4 w-4" />
  Generate with AI
</Button>
```

(If `variant="outline"` is unsupported by `Button.vue`, omit it.)

- [ ] **Step 5: Add the "AI columns" button near "Add Column"**

Next to the existing Add Column button (the one calling `openAddColumn`, near line 840), add:

```vue
<Button
  variant="outline"
  size="sm"
  @click="openAIExtend"
>
  <Sparkles class="mr-1 h-4 w-4" />
  AI columns
</Button>
```

- [ ] **Step 6: Render the dialog**

After the existing `<DataTableImportDialog ... />` block (ends ~line 1207), add:

```vue
<!-- ════════ AI SCHEMA DIALOG ════════ -->
<DataTableAISchemaDialog
  v-if="showAIDialog"
  :mode="aiDialogMode"
  :existing-table="aiDialogMode === 'extend' ? selectedTable : null"
  @created="handleAICreated"
  @updated="handleAIUpdated"
  @close="showAIDialog = false"
/>
```

- [ ] **Step 7: Typecheck + lint**

Run: `cd frontend && bun run typecheck && bun run lint`
Expected: PASS. Fix any issues inline.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/DataTable/DataTablePanel.vue
git commit -m "feat: wire AI schema dialog into DataTable panel"
```

---

## Task 6: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full check suite**

Run: `cd /Users/mbakgun/Projects/heym/heymrun && SECRET_KEY=test-secret-key-for-tests-only-32-bytes ./check.sh`
Expected: frontend lint + typecheck PASS, backend ruff PASS, backend tests PASS (including `test_data_table_schema_generation.py`).

- [ ] **Step 2: Commit any formatting-only diffs**

```bash
git add -A
git commit -m "chore: formatting for DataTable AI schema feature" || echo "nothing to commit"
```

---

## Task 7: Documentation

**Files:** determined by the `heym-documentation` skill.

- [ ] **Step 1: Invoke the docs skill**

Use the `heym-documentation` skill to document the new DataTable AI schema generation feature: the "Generate with AI" flow for new tables, the "AI columns" flow for existing tables, the review/edit step, and the `POST /api/data-tables/generate-schema` endpoint (request/response shape, credential + model selection, append-only behavior for existing tables).

- [ ] **Step 2: Commit docs**

```bash
git add -A
git commit -m "docs: document DataTable AI schema generation"
```

---

## Self-Review Notes

- **Spec coverage:** Backend endpoint (Task 2) ✓; server-side normalization/dedupe/type-coercion (Task 2 helpers) ✓; 400/422 errors (Task 2 tests + endpoint) ✓; two-phase dialog with credential/model picker + ESC-via-Dialog (Task 4) ✓; full inline editing incl. add/delete (Task 4) ✓; create-mode name/description prefill (Task 4) ✓; extend-mode read-only existing columns + append-only merge (Task 4 + Task 5) ✓; types + api client (Task 3) ✓; two entry points wired (Task 5) ✓; backend tests, no frontend tests (Task 2, per AGENTS.md) ✓; docs (Task 7) ✓.
- **Type consistency:** `DataTableColumnDef` (backend) and `DataTableColumn` (frontend) field names match: `name, type, required, defaultValue, unique, order`. `generateSchema` payload/response match `DataTableSchemaSuggestion`/`DataTableSchemaSuggestionResponse`. Helper names `_normalize_generated_columns` / `_extract_schema_payload` / `_build_schema_system_prompt` / `_build_schema_user_prompt` and endpoint `generate_data_table_schema` are used identically in tests and implementation.
- **Risk noted inline:** potential circular import from importing `ai_assistant` helpers into `data_tables` is explicitly checked and mitigated in Task 2 Step 9.
```
