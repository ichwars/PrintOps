from sqlalchemy import inspect

from backend.app.models.stock_reservation import StockReservationAllocation


async def test_commerce_and_reservation_tables_are_registered(test_engine):
    async with test_engine.connect() as connection:
        tables = await connection.run_sync(lambda conn: set(inspect(conn).get_table_names()))

    assert {
        "offers",
        "customer_orders",
        "offer_acceptances",
        "stock_reservations",
        "stock_reservation_allocations",
        "stock_resource_locks",
    } <= tables


def test_reservation_allocations_have_exact_target_and_quantity_guards():
    names = {constraint.name for constraint in StockReservationAllocation.__table__.constraints}

    assert "ck_stock_allocation_exact_target" in names
    assert "ck_stock_allocation_quantities" in names
