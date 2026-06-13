from app.models.dashboard_schemas import WidgetDataResponse


async def compute_widget_data(db, widget, user, force: bool = False) -> WidgetDataResponse:
    raise NotImplementedError
