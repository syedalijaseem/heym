import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Dashboard, DashboardWidget, User, Workflow
from app.db.session import get_db
from app.models.dashboard_schemas import (
    DashboardResponse,
    DashboardWidgetResponse,
    WidgetCreateRequest,
    WidgetDataResponse,
    WidgetUpdateRequest,
)
from app.services.dashboard_data import compute_widget_data

router = APIRouter()


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
