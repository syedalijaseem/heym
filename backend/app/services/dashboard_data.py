import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DashboardWidget, ExecutionHistory, User, Workflow
from app.models.dashboard_schemas import WidgetDataResponse
from app.services.workflow_executor import execute_workflow

logger = logging.getLogger(__name__)

_CHART_PAYLOAD_TYPES = frozenset(
    ("pie", "bar", "line", "area", "table", "numeric", "gauge", "scatter", "proportion", "barGauge")
)


async def _record_widget_execution(db: AsyncSession, workflow: Workflow, result) -> None:
    """Record an execution-history row + analytics snapshot for a widget run.

    Mirrors the workflow execute endpoint so a widget that actually runs (cache miss)
    increases the history of both the widget and its underlying workflow.
    """
    from app.api.analytics import upsert_workflow_analytics_snapshot

    try:
        db.add(
            ExecutionHistory(
                workflow_id=workflow.id,
                inputs={},
                outputs=result.outputs,
                node_results=result.node_results,
                status=result.status,
                execution_time_ms=result.execution_time_ms,
                trigger_source="dashboard",
            )
        )
        await upsert_workflow_analytics_snapshot(
            db,
            workflow_id=workflow.id,
            owner_id=workflow.owner_id,
            workflow_name_snapshot=workflow.name,
            status=result.status,
            execution_time_ms=result.execution_time_ms,
        )
    except Exception:  # history is best-effort; never break widget rendering
        logger.debug("Failed to record widget execution history", exc_info=True)


def _version_token(workflow: Workflow) -> str:
    return workflow.updated_at.isoformat() if workflow.updated_at else ""


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _is_chart_payload(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") in _CHART_PAYLOAD_TYPES


def _unwrap_chart_payload(value: Any) -> dict | None:
    if _is_chart_payload(value):
        return value
    if not isinstance(value, dict):
        return None

    nested_payloads = [nested for nested in value.values() if _is_chart_payload(nested)]
    return nested_payloads[0] if len(nested_payloads) == 1 else None


def _extract_chart_payload(result: Any) -> dict | None:
    final_payload = _unwrap_chart_payload(getattr(result, "outputs", None))
    for nr in getattr(result, "node_results", []) or []:
        node_type = _field(nr, "node_type")
        if node_type == "chartOutput":
            return _unwrap_chart_payload(_field(nr, "output")) or final_payload
    return final_payload


async def compute_widget_data(
    db: AsyncSession, widget: DashboardWidget, user: User, force: bool = False
) -> WidgetDataResponse:
    wf_result = await db.execute(select(Workflow).where(Workflow.id == widget.workflow_id))
    workflow = wf_result.scalar_one_or_none()
    if workflow is None:
        return WidgetDataResponse(
            widget_id=widget.id,
            payload=None,
            cached=False,
            computed_at=None,
            error="Widget workflow not found",
        )

    version = _version_token(workflow)
    now = datetime.now(timezone.utc)
    fresh = (
        not force
        and widget.cached_payload is not None
        and widget.cached_at is not None
        and widget.cached_workflow_version == version
        and (now - widget.cached_at).total_seconds() < widget.cache_ttl_seconds
    )
    if fresh:
        return WidgetDataResponse(
            widget_id=widget.id,
            payload=widget.cached_payload,
            cached=True,
            computed_at=widget.cached_at,
        )

    try:
        result = await asyncio.to_thread(
            execute_workflow,
            workflow_id=workflow.id,
            nodes=workflow.nodes,
            edges=workflow.edges,
            inputs={},
            test_run=False,
            trace_user_id=user.id,
            actor_user_id=user.id,
        )
    except Exception as exc:  # surface execution errors to the widget, never 500 the dashboard
        return WidgetDataResponse(
            widget_id=widget.id, payload=None, cached=False, computed_at=None, error=str(exc)
        )

    payload = _extract_chart_payload(result)
    await _record_widget_execution(db, workflow, result)
    widget.cached_payload = payload
    widget.cached_at = now
    widget.cached_workflow_version = version
    await db.commit()
    return WidgetDataResponse(
        widget_id=widget.id,
        payload=payload,
        cached=False,
        computed_at=now,
        error=None if payload is not None else "Workflow produced no chartOutput",
    )
