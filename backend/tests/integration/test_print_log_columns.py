import pytest
from httpx import AsyncClient


class TestPrintLogSorting:
    """#2636: the Print Log's column headers sort the whole log.

    Sorting is server-side because paging is: ordering the rows the browser
    happens to hold would answer "the most expensive print on this page",
    not "the most expensive print". These pin the ordering contract the
    headers depend on, including the two cases that differ per database
    backend or per query plan if left implicit.
    """

    @staticmethod
    async def _seed(db_session, printer_id: int, rows: list[dict]):
        from datetime import datetime

        from backend.app.models.print_log import PrintLogEntry

        created = []
        for i, row in enumerate(rows):
            entry = PrintLogEntry(
                printer_id=printer_id,
                status=row.get("status", "completed"),
                print_name=row.get("print_name", f"job-{i}"),
                started_at=datetime(2026, 1, 1 + i, 12, 0, 0),
                created_at=datetime(2026, 1, 1 + i, 12, 0, 0),
                filament_used_grams=row.get("grams"),
                cost=row.get("cost"),
                energy_kwh=row.get("kwh"),
            )
            db_session.add(entry)
            created.append(entry)
        await db_session.commit()
        return created

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sorts_by_filament_used_in_both_directions(
        self, async_client: AsyncClient, printer_factory, db_session
    ):
        printer = await printer_factory()
        await self._seed(
            db_session,
            printer.id,
            [{"grams": 5.0}, {"grams": 120.0}, {"grams": 30.0}],
        )

        asc = await async_client.get("/api/v1/print-log/?sort_by=filament_used&sort_dir=asc")
        assert asc.status_code == 200
        assert [e["filament_used_grams"] for e in asc.json()["items"]] == [5.0, 30.0, 120.0]

        desc = await async_client.get("/api/v1/print-log/?sort_by=filament_used&sort_dir=desc")
        assert [e["filament_used_grams"] for e in desc.json()["items"]] == [120.0, 30.0, 5.0]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_empty_values_sort_last_whichever_direction(
        self, async_client: AsyncClient, printer_factory, db_session
    ):
        """Cost is NULL until a spool is priced and energy until a smart plug
        reports, so these columns are half-empty for most people. Postgres
        sorts NULLs high and SQLite sorts them low, so without an explicit
        NULLS LAST the same click gives a different first page depending on
        which database the user deployed — and on one of them, a screenful
        of blanks."""
        printer = await printer_factory()
        await self._seed(
            db_session,
            printer.id,
            [{"cost": None}, {"cost": 2.5}, {"cost": None}, {"cost": 0.75}],
        )

        for direction, expected in (("asc", [0.75, 2.5]), ("desc", [2.5, 0.75])):
            resp = await async_client.get(f"/api/v1/print-log/?sort_by=cost&sort_dir={direction}")
            costs = [e["cost"] for e in resp.json()["items"]]
            assert costs[:2] == expected, (direction, costs)
            assert costs[2:] == [None, None], (direction, costs)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ties_are_broken_stably_across_pages(self, async_client: AsyncClient, printer_factory, db_session):
        """Sorting by a column where every row shares a value (status) leaves
        the order to the planner unless a tiebreaker is added — and an
        unstable order can show the same row on two pages while another never
        appears at all."""
        printer = await printer_factory()
        await self._seed(db_session, printer.id, [{"status": "completed"} for _ in range(6)])

        first = await async_client.get("/api/v1/print-log/?sort_by=status&sort_dir=asc&limit=3&offset=0")
        second = await async_client.get("/api/v1/print-log/?sort_by=status&sort_dir=asc&limit=3&offset=3")
        page_1 = [e["id"] for e in first.json()["items"]]
        page_2 = [e["id"] for e in second.json()["items"]]

        assert len(set(page_1) & set(page_2)) == 0, "a row appeared on both pages"
        assert len(set(page_1) | set(page_2)) == 6, "a row was never returned"
        # Repeating the same request must give the same page back.
        again = await async_client.get("/api/v1/print-log/?sort_by=status&sort_dir=asc&limit=3&offset=0")
        assert [e["id"] for e in again.json()["items"]] == page_1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unknown_sort_column_is_rejected(self, async_client: AsyncClient):
        """The client picks the sort key, so the column list is a whitelist —
        anything else would let a request order by any attribute it can name."""
        resp = await async_client.get("/api/v1/print-log/?sort_by=created_by_id")
        assert resp.status_code == 400
        resp = await async_client.get("/api/v1/print-log/?sort_by=1;DROP")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_direction_is_rejected(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/print-log/?sort_by=date&sort_dir=sideways")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_defaults_to_newest_first(self, async_client: AsyncClient, printer_factory, db_session):
        """No sort params — the pre-#2636 behaviour, which existing clients
        and the first page load both rely on."""
        printer = await printer_factory()
        await self._seed(db_session, printer.id, [{"print_name": "oldest"}, {"print_name": "newest"}])

        resp = await async_client.get("/api/v1/print-log/")
        assert [e["print_name"] for e in resp.json()["items"]] == ["newest", "oldest"]


@pytest.mark.asyncio
async def test_print_log_preserves_recorded_money_on_list_and_edit(async_client, db_session):
    from backend.app.models.print_log import PrintLogEntry

    entry = PrintLogEntry(status="completed", cost=0.42, energy_kwh=0.31, energy_cost=0.09)
    db_session.add(entry)
    await db_session.commit()
    for response in (
        await async_client.get("/api/v1/print-log/"),
        await async_client.patch(f"/api/v1/print-log/{entry.id}", json={"failure_reason": "other"}),
    ):
        assert response.status_code == 200
        row = response.json()["items"][0] if "items" in response.json() else response.json()
        assert row["cost"] == 0.42
        assert row["energy_kwh"] == 0.31
        assert row["energy_cost"] == 0.09
