import datetime
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.api import data_tables as dt_api
from app.db.models import DataTable, DataTableRow
from app.models.schemas import DataTableColumnDef, DataTableUpdate


class _User:
    def __init__(self):
        self.id = uuid.uuid4()


def _source_table(owner_id: uuid.UUID) -> DataTable:
    table = DataTable(
        name="Customers",
        description="People who buy",
        columns=[
            {"id": "c1", "name": "email", "type": "string", "order": 0},
            {"id": "c2", "name": "age", "type": "number", "order": 1},
        ],
        owner_id=owner_id,
    )
    table.id = uuid.uuid4()
    return table


def _wire_db(db):
    """Assign PKs on flush and timestamps on refresh, emulating PostgreSQL."""

    async def fake_flush():
        for call in db.add.call_args_list:
            obj = call.args[0]
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def fake_refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        now = datetime.datetime.now()
        obj.created_at = now
        obj.updated_at = now

    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=fake_flush)
    db.refresh = AsyncMock(side_effect=fake_refresh)


def _scalar(value):
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


def _scalars(values):
    res = MagicMock()
    scalars = MagicMock()
    scalars.__iter__.return_value = iter(values)
    scalars.all.return_value = values
    res.scalars.return_value = scalars
    return res


def _count(value: int):
    res = MagicMock()
    res.scalar.return_value = value
    return res


class TestCloneDataTable(unittest.IsolatedAsyncioTestCase):
    async def test_clone_copies_columns_and_all_rows(self):
        user = _User()
        source = _source_table(user.id)
        rows = [
            DataTableRow(table_id=source.id, data={"email": "a@x.com", "age": 30}),
            DataTableRow(table_id=source.id, data={"email": "b@x.com", "age": 25}),
        ]

        db = MagicMock()
        _wire_db(db)
        db.execute = AsyncMock(
            side_effect=[
                _scalar(source),  # _get_data_table_with_access owner lookup
                _scalar(None),  # name-collision check -> no existing
                _scalars(rows),  # source rows
            ]
        )

        resp = await dt_api.clone_data_table(table_id=source.id, current_user=user, db=db)

        self.assertEqual(resp.name, "Customers (Copy)")
        self.assertEqual(resp.description, "People who buy")
        self.assertEqual(resp.columns, source.columns)
        self.assertEqual(resp.owner_id, user.id)
        self.assertEqual(resp.row_count, 2)
        self.assertNotEqual(resp.id, source.id)

        # Two rows added with copied data, owned/authored by the cloning user.
        added_rows = [
            c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], DataTableRow)
        ]
        self.assertEqual(len(added_rows), 2)
        self.assertEqual({r.data["email"] for r in added_rows}, {"a@x.com", "b@x.com"})
        for r in added_rows:
            self.assertEqual(r.created_by, user.id)
            self.assertEqual(r.updated_by, user.id)

    async def test_clone_name_increments_on_collision(self):
        user = _User()
        source = _source_table(user.id)

        db = MagicMock()
        _wire_db(db)
        db.execute = AsyncMock(
            side_effect=[
                _scalar(source),  # access lookup
                _scalar(MagicMock()),  # "Customers (Copy)" exists
                _scalar(None),  # "Customers (Copy 2)" free
                _scalars([]),  # no rows
            ]
        )

        resp = await dt_api.clone_data_table(table_id=source.id, current_user=user, db=db)

        self.assertEqual(resp.name, "Customers (Copy 2)")
        self.assertEqual(resp.row_count, 0)

    async def test_clone_does_not_copy_shares(self):
        user = _User()
        source = _source_table(user.id)

        db = MagicMock()
        _wire_db(db)
        db.execute = AsyncMock(side_effect=[_scalar(source), _scalar(None), _scalars([])])

        await dt_api.clone_data_table(table_id=source.id, current_user=user, db=db)

        # Only the new DataTable is added (no rows, no DataTableShare objects).
        added_types = {type(c.args[0]).__name__ for c in db.add.call_args_list}
        self.assertEqual(added_types, {"DataTable"})

    async def test_clone_inaccessible_table_raises_404(self):
        user = _User()
        table_id = uuid.uuid4()

        db = MagicMock()
        _wire_db(db)
        empty_first = MagicMock()
        empty_first.first.return_value = None
        db.execute = AsyncMock(
            side_effect=[
                _scalar(None),  # owner lookup -> none
                MagicMock(one_or_none=MagicMock(return_value=None)),  # user share
                empty_first,  # team share
            ]
        )

        with self.assertRaises(HTTPException) as ctx:
            await dt_api.clone_data_table(table_id=table_id, current_user=user, db=db)
        self.assertEqual(ctx.exception.status_code, 404)


class TestUpdateDataTable(unittest.IsolatedAsyncioTestCase):
    async def test_update_columns_prunes_removed_column_values_from_rows(self):
        user = _User()
        table = _source_table(user.id)
        table.columns.append(
            {"id": "c3", "name": "name", "type": "string", "required": False, "order": 2}
        )
        rows = [
            DataTableRow(
                table_id=table.id,
                data={"email": "a@x.com", "age": 30, "name": "Ada", "stale": "x"},
            ),
            DataTableRow(
                table_id=table.id,
                data={"email": "b@x.com", "age": 25, "name": "Ben"},
            ),
        ]

        db = MagicMock()
        _wire_db(db)
        db.execute = AsyncMock(
            side_effect=[
                _scalar(table),  # table lookup
                _scalars(rows),  # row pruning
                _count(2),  # response row_count
            ]
        )

        response = await dt_api.update_data_table(
            table_id=table.id,
            data=DataTableUpdate(
                columns=[
                    DataTableColumnDef(name="email"),
                    DataTableColumnDef(name="name", order=1),
                ]
            ),
            current_user=user,
            db=db,
        )

        self.assertEqual(response.row_count, 2)
        self.assertEqual([col["name"] for col in response.columns], ["email", "name"])
        self.assertEqual(rows[0].data, {"email": "a@x.com", "name": "Ada"})
        self.assertEqual(rows[1].data, {"email": "b@x.com", "name": "Ben"})
        self.assertEqual(rows[0].updated_by, user.id)
        self.assertEqual(rows[1].updated_by, user.id)


if __name__ == "__main__":
    unittest.main()
