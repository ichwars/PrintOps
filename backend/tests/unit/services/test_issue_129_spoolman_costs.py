from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.spoolman_costs import resolve_print_log_cost
from backend.app.services.spoolman_tracking import _apply_spoolman_costs_to_archive, _spoolman_usage_cost


def _spool(*, price=None, filament_price=None, weight=1000):
    return {"price": price, "filament": {"price": filament_price, "weight": weight}}


@pytest.mark.parametrize(
    ("weight", "expected"),
    [(500, 4.0), (1000, 2.0)],
)
def test_spool_price_is_spread_over_net_filament_weight(weight, expected):
    assert _spoolman_usage_cost(_spool(price=20, weight=weight), 100) == pytest.approx(expected)


def test_spool_price_overrides_filament_price_and_zero_falls_back():
    assert _spoolman_usage_cost(_spool(price=40, filament_price=25), 100) == pytest.approx(4.0)
    assert _spoolman_usage_cost(_spool(price=0, filament_price=25), 100) == pytest.approx(2.5)


@pytest.mark.parametrize(
    "spool",
    [
        _spool(),
        _spool(filament_price=0),
        _spool(filament_price=-1),
        _spool(filament_price=True),
        _spool(filament_price=float("nan")),
        _spool(filament_price=float("inf")),
        _spool(filament_price=20, weight=None),
        _spool(filament_price=20, weight=0),
        _spool(filament_price=20, weight=-1),
        _spool(filament_price=20, weight=True),
        _spool(price=1e308, weight=1e-308),
        {"price": 20, "filament": "invalid"},
        None,
    ],
)
def test_invalid_spool_prices_or_weights_do_not_create_a_cost(spool):
    assert _spoolman_usage_cost(spool, 100) is None


@pytest.mark.parametrize("grams", [None, 0, -1, True, float("nan"), float("inf")])
def test_invalid_usage_weight_does_not_create_a_cost(grams):
    assert _spoolman_usage_cost(_spool(price=20), grams) is None


def _result(*, row=None, count=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    result.scalar.return_value = count
    return result


@pytest.mark.asyncio
async def test_first_run_stores_spoolman_actual_and_returns_run_cost():
    archive = SimpleNamespace(cost=2.5, filament_used_grams=150.0, extra_data={"keep": "value"})
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(row=archive), _result(count=0)])

    with patch("backend.app.api.routes.settings.get_setting", AsyncMock(return_value="20")):
        run_cost = await _apply_spoolman_costs_to_archive(db, 7, [(100.0, 4.0), (50.0, 3.0)])

    assert run_cost == pytest.approx(7.0)
    assert archive.cost == pytest.approx(7.0)
    assert archive.extra_data == {"keep": "value", "cost_source": "spoolman"}
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reprint_returns_its_cost_without_overwriting_first_run():
    archive = SimpleNamespace(
        cost=4.0,
        filament_used_grams=50.0,
        extra_data={"cost_source": "spoolman"},
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(row=archive), _result(count=1)])

    run_cost = await _apply_spoolman_costs_to_archive(db, 7, [(50.0, 3.0)])

    assert run_cost == pytest.approx(3.0)
    assert archive.cost == pytest.approx(4.0)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_default_rate_cannot_poison_partially_priced_total():
    archive = SimpleNamespace(cost=2.5, filament_used_grams=150.0, extra_data=None)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result(row=archive), _result(count=0)])

    with patch("backend.app.api.routes.settings.get_setting", AsyncMock(return_value="NaN")):
        run_cost = await _apply_spoolman_costs_to_archive(db, 7, [(100.0, 4.0)])

    assert run_cost == pytest.approx(4.0)
    assert archive.cost == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_aggregate_overflow_does_not_create_an_infinite_cost():
    archive = SimpleNamespace(cost=2.5, filament_used_grams=2.0, extra_data=None)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(row=archive))

    run_cost = await _apply_spoolman_costs_to_archive(db, 7, [(1.0, 1e308), (1.0, 1e308)])

    assert run_cost is None
    assert archive.cost == pytest.approx(2.5)
    db.commit.assert_not_awaited()


def test_multi_material_costs_are_summed_at_their_own_rates():
    pla = _spool(filament_price=20, weight=1000)
    pa = _spool(filament_price=60, weight=1000)
    total = _spoolman_usage_cost(pla, 100) + _spoolman_usage_cost(pa, 50)
    assert total == pytest.approx(5.0)


def test_completed_reprint_log_prefers_its_spoolman_actual_over_first_run_archive_cost():
    assert resolve_print_log_cost(3.0, [], "completed", 4.0) == pytest.approx(3.0)
    assert resolve_print_log_cost(0.0, [], "completed", 4.0) == pytest.approx(0.0)


def test_run_cost_fallbacks_preserve_internal_and_incomplete_behavior():
    assert resolve_print_log_cost(None, [{"cost": 1.25}, {"cost": 0.75}], "completed", 9.0) == pytest.approx(2.0)
    assert resolve_print_log_cost(None, [], "completed", 9.0) == pytest.approx(9.0)
    assert resolve_print_log_cost(None, [], "failed", 9.0) is None


def test_run_cost_fallbacks_reject_nonfinite_aggregates_and_archive_costs():
    overflow = [{"cost": 1e308}, {"cost": 1e308}]
    assert resolve_print_log_cost(None, overflow, "completed", 9.0) == pytest.approx(9.0)
    assert resolve_print_log_cost(None, [], "completed", float("inf")) is None
