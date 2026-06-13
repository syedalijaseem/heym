import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ai_assistant import (
    WORKFLOW_BUILDER_TEMPERATURE,
    _extract_generated_workflow_config,
    get_credential_for_user,
    get_openai_client,
)
from app.api.deps import get_current_user
from app.db.models import CredentialType, Dashboard, DashboardWidget, User, Workflow
from app.db.session import get_db
from app.models.dashboard_schemas import (
    AiWidgetRequest,
    DashboardResponse,
    DashboardWidgetResponse,
    WidgetCreateRequest,
    WidgetDataResponse,
    WidgetUpdateRequest,
)
from app.services.dashboard_data import compute_widget_data
from app.services.encryption import decrypt_config
from app.services.llm_provider import is_reasoning_model
from app.services.workflow_dsl_prompt import build_assistant_prompt

router = APIRouter()

_AI_WIDGET_SUFFIX = (
    " The workflow MUST end with a single chartOutput node that produces the chart. "
    "Choose an appropriate chartType (pie, bar, line, table, or numeric) and set "
    "labelField/valueField (or series) on the chartOutput node so it renders the requested metric."
)


async def generate_widget_dsl(prompt: str, *, credential, model: str, user: User) -> dict:
    """Generate a widget workflow DSL (nodes + edges) ending in a chartOutput node."""
    config = decrypt_config(credential.encrypted_config)
    client, _ = get_openai_client(credential.type, config)
    system_prompt = build_assistant_prompt(None, [], getattr(user, "user_rules", None))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt + _AI_WIDGET_SUFFIX},
    ]
    kwargs: dict = {"model": model, "messages": messages, "stream": False}
    if not is_reasoning_model(model):
        kwargs["temperature"] = WORKFLOW_BUILDER_TEMPERATURE

    def _call() -> str:
        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0] if resp.choices else None
        return choice.message.content if choice else ""

    content = await asyncio.to_thread(_call)
    return _extract_generated_workflow_config(content or "", prompt)


async def _get_or_create_dashboard(db: AsyncSession, user: User) -> Dashboard:
    result = await db.execute(
        select(Dashboard).where(Dashboard.owner_id == user.id).order_by(Dashboard.created_at)
    )
    dashboard = result.scalars().first()
    if dashboard is None:
        dashboard = Dashboard(owner_id=user.id, name="Dashboard")
        db.add(dashboard)
        await db.commit()
        await db.refresh(dashboard)
    return dashboard


def _seed_widget_nodes(chart_type: str) -> tuple[list, list]:
    src_id = str(uuid.uuid4())
    chart_id = str(uuid.uuid4())
    nodes = [
        {
            "id": src_id,
            "type": "textInput",
            "position": {"x": 0, "y": 0},
            "data": {"label": "Data"},
        },
        {
            "id": chart_id,
            "type": "chartOutput",
            "position": {"x": 320, "y": 0},
            "data": {"label": "Chart", "chartType": chart_type},
        },
    ]
    edges = [{"id": str(uuid.uuid4()), "source": src_id, "target": chart_id}]
    return nodes, edges


def _widget_to_response(widget: DashboardWidget) -> DashboardWidgetResponse:
    return DashboardWidgetResponse(
        id=widget.id,
        workflow_id=widget.workflow_id,
        title=widget.title,
        chart_type=widget.chart_type,
        layout=widget.layout,
        cache_ttl_seconds=widget.cache_ttl_seconds,
        position=widget.position,
        updated_at=widget.updated_at,
    )


async def _load_widget(db: AsyncSession, widget_id: uuid.UUID, user: User) -> DashboardWidget:
    result = await db.execute(
        select(DashboardWidget)
        .join(Dashboard, DashboardWidget.dashboard_id == Dashboard.id)
        .where(DashboardWidget.id == widget_id, Dashboard.owner_id == user.id)
    )
    widget = result.scalar_one_or_none()
    if widget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
    return widget


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    dashboard = await _get_or_create_dashboard(db, current_user)
    result = await db.execute(
        select(DashboardWidget)
        .where(DashboardWidget.dashboard_id == dashboard.id)
        .order_by(DashboardWidget.position)
    )
    widgets = result.scalars().all()
    return DashboardResponse(
        id=dashboard.id,
        name=dashboard.name,
        widgets=[_widget_to_response(w) for w in widgets],
    )


@router.post(
    "/widgets", response_model=DashboardWidgetResponse, status_code=status.HTTP_201_CREATED
)
async def create_widget(
    body: WidgetCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardWidgetResponse:
    dashboard = await _get_or_create_dashboard(db, current_user)
    nodes, edges = _seed_widget_nodes(body.chart_type)
    workflow = Workflow(
        name=f"[widget] {body.title}",
        owner_id=current_user.id,
        kind="dashboard_widget",
        nodes=nodes,
        edges=edges,
    )
    db.add(workflow)
    await db.flush()
    widget = DashboardWidget(
        dashboard_id=dashboard.id,
        workflow_id=workflow.id,
        title=body.title,
        chart_type=body.chart_type,
        layout=body.layout.model_dump(),
        cache_ttl_seconds=body.cache_ttl_seconds,
    )
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return _widget_to_response(widget)


@router.patch("/widgets/{widget_id}", response_model=DashboardWidgetResponse)
async def update_widget(
    widget_id: uuid.UUID,
    body: WidgetUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardWidgetResponse:
    widget = await _load_widget(db, widget_id, current_user)
    if body.title is not None:
        widget.title = body.title
    if body.chart_type is not None:
        widget.chart_type = body.chart_type
    if body.layout is not None:
        widget.layout = body.layout.model_dump()
    if body.cache_ttl_seconds is not None:
        widget.cache_ttl_seconds = body.cache_ttl_seconds
    await db.commit()
    await db.refresh(widget)
    return _widget_to_response(widget)


@router.delete("/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_widget(
    widget_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    widget = await _load_widget(db, widget_id, current_user)
    workflow_id = widget.workflow_id
    await db.delete(widget)
    wf_result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = wf_result.scalar_one_or_none()
    if workflow is not None and workflow.kind == "dashboard_widget":
        await db.delete(workflow)
    await db.commit()


@router.get("/widgets/{widget_id}/data", response_model=WidgetDataResponse)
async def get_widget_data(
    widget_id: uuid.UUID,
    force: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WidgetDataResponse:
    widget = await _load_widget(db, widget_id, current_user)
    return await compute_widget_data(db, widget, current_user, force=force)


@router.post(
    "/widgets/ai-generate",
    response_model=DashboardWidgetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ai_generate_widget(
    body: AiWidgetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardWidgetResponse:
    credential = await get_credential_for_user(body.credential_id, current_user, db)
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    if credential.type not in (
        CredentialType.openai,
        CredentialType.google,
        CredentialType.custom,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential must be an LLM type (OpenAI, Google, or Custom)",
        )

    dashboard = await _get_or_create_dashboard(db, current_user)
    dsl = await generate_widget_dsl(
        body.prompt, credential=credential, model=body.model, user=current_user
    )
    nodes = dsl.get("nodes", [])
    edges = dsl.get("edges", [])
    chart_nodes = [n for n in nodes if n.get("type") == "chartOutput"]
    if not chart_nodes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="AI did not produce a chartOutput node",
        )
    chart_type = chart_nodes[-1].get("data", {}).get("chartType", "bar")
    workflow = Workflow(
        name="[widget] AI generated",
        owner_id=current_user.id,
        kind="dashboard_widget",
        nodes=nodes,
        edges=edges,
    )
    db.add(workflow)
    await db.flush()
    widget = DashboardWidget(
        dashboard_id=dashboard.id,
        workflow_id=workflow.id,
        title=body.prompt[:60],
        chart_type=chart_type,
        layout={"x": 0, "y": 0, "w": 4, "h": 4},
        cache_ttl_seconds=300,
    )
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return _widget_to_response(widget)
